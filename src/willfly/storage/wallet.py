"""Durable, idempotent storage for public-wallet observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from willfly.domain.wallets import WalletActivity, WalletObservation, build_wallet_observation


@dataclass(frozen=True)
class WalletWriteResult:
    inserted: int
    duplicates: int
    revised: int


@dataclass(frozen=True)
class WalletCursor:
    wallet: str
    source: str
    filter_identity: str
    last_block_number: int | None
    last_block_hash: str | None
    state: str
    reason: str | None


class WalletObservationStore:
    """SQLite store with current activity plus immutable payload revisions.

    The store is intentionally separate from the raw event table: wallet
    activity is a derived view that may be reclassified during fork repair,
    while raw batches remain lossless and append-only.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "wallet-observations.sqlite3"
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def __enter__(self) -> "WalletObservationStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS wallet_activities (
                activity_id TEXT PRIMARY KEY,
                wallet TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                event_time TEXT NOT NULL,
                received_time TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS wallet_activities_wallet_idx
                ON wallet_activities(wallet, event_time, received_time, activity_id);
            CREATE TABLE IF NOT EXISTS wallet_activity_revisions (
                revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE(activity_id, payload_sha256)
            );
            CREATE TABLE IF NOT EXISTS wallet_cursors (
                wallet TEXT NOT NULL,
                source TEXT NOT NULL,
                filter_identity TEXT NOT NULL,
                last_block_number INTEGER,
                last_block_hash TEXT,
                state TEXT NOT NULL,
                reason TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(wallet, source)
            );
            """
        )
        self._connection.commit()

    @staticmethod
    def _payload(activity: WalletActivity) -> tuple[str, str]:
        encoded = json.dumps(activity.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def record(self, activities: Iterable[WalletActivity]) -> WalletWriteResult:
        """Insert activities idempotently and retain changed payload revisions."""

        records = tuple(activities)
        inserted = duplicates = revised = 0
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            for activity in records:
                if not isinstance(activity, WalletActivity):
                    raise TypeError("wallet store accepts WalletActivity records")
                payload_json, payload_hash = self._payload(activity)
                existing = self._connection.execute(
                    "SELECT payload_json, payload_sha256 FROM wallet_activities WHERE activity_id = ?",
                    (activity.activity_id,),
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        """
                        INSERT INTO wallet_activities(
                            activity_id, wallet, payload_json, payload_sha256,
                            event_time, received_time, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            activity.activity_id,
                            activity.wallet,
                            payload_json,
                            payload_hash,
                            activity.event_time,
                            activity.received_time,
                            now,
                        ),
                    )
                    inserted += 1
                    continue
                if existing["payload_sha256"] == payload_hash:
                    duplicates += 1
                    continue
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO wallet_activity_revisions(
                        activity_id, payload_json, payload_sha256, recorded_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (activity.activity_id, existing["payload_json"], existing["payload_sha256"], now),
                )
                self._connection.execute(
                    """
                    UPDATE wallet_activities
                    SET wallet = ?, payload_json = ?, payload_sha256 = ?,
                        event_time = ?, received_time = ?, updated_at = ?
                    WHERE activity_id = ?
                    """,
                    (
                        activity.wallet,
                        payload_json,
                        payload_hash,
                        activity.event_time,
                        activity.received_time,
                        now,
                        activity.activity_id,
                    ),
                )
                revised += 1
        return WalletWriteResult(inserted, duplicates, revised)

    def list_activities(self, *, wallet: str | None = None) -> tuple[WalletActivity, ...]:
        if wallet is None:
            rows = self._connection.execute(
                "SELECT payload_json FROM wallet_activities ORDER BY event_time, received_time, activity_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT payload_json FROM wallet_activities WHERE lower(wallet) = lower(?) ORDER BY event_time, received_time, activity_id",
                (wallet,),
            ).fetchall()
        return tuple(WalletActivity.from_dict(json.loads(row["payload_json"])) for row in rows)

    def list_revisions(self, activity_id: str) -> tuple[WalletActivity, ...]:
        rows = self._connection.execute(
            "SELECT payload_json FROM wallet_activity_revisions WHERE activity_id = ? ORDER BY revision_id",
            (activity_id,),
        ).fetchall()
        return tuple(WalletActivity.from_dict(json.loads(row["payload_json"])) for row in rows)

    def save_cursor(
        self,
        *,
        wallet: str,
        source: str,
        filter_identity: str,
        last_block_number: int | None,
        last_block_hash: str | None,
    ) -> WalletCursor:
        """Advance a cursor only when its filter and lineage remain stable."""

        if not wallet or not source or not filter_identity:
            raise ValueError("wallet, source and filter_identity are required")
        if last_block_number is not None and (not isinstance(last_block_number, int) or last_block_number < 0):
            raise ValueError("last_block_number must be non-negative")
        if last_block_hash is not None and (len(last_block_hash) != 66 or not last_block_hash.startswith("0x")):
            raise ValueError("last_block_hash must be a 32-byte hex value")
        existing = self._connection.execute(
            "SELECT * FROM wallet_cursors WHERE wallet = ? AND source = ?", (wallet, source)
        ).fetchone()
        state = "healthy"
        reason: str | None = None
        if existing is not None:
            if existing["filter_identity"] != filter_identity:
                state, reason = "needs_repair", "cursor_filter_identity_changed"
            elif (
                existing["last_block_number"] is not None
                and last_block_number is not None
                and last_block_number < existing["last_block_number"]
            ):
                state, reason = "needs_repair", "cursor_moved_back_without_repair"
            elif (
                existing["last_block_number"] == last_block_number
                and existing["last_block_hash"] not in {None, last_block_hash}
            ):
                state, reason = "needs_repair", "cursor_lineage_changed"
        if existing is not None and state == "needs_repair":
            cursor = WalletCursor(wallet, source, existing["filter_identity"], existing["last_block_number"], existing["last_block_hash"], state, reason)
            with self._connection:
                self._connection.execute(
                    "UPDATE wallet_cursors SET state = ?, reason = ?, updated_at = ? WHERE wallet = ? AND source = ?",
                    (state, reason, datetime.now(timezone.utc).isoformat(), wallet, source),
                )
            return cursor
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO wallet_cursors(
                    wallet, source, filter_identity, last_block_number,
                    last_block_hash, state, reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(wallet, source) DO UPDATE SET
                    filter_identity = excluded.filter_identity,
                    last_block_number = excluded.last_block_number,
                    last_block_hash = excluded.last_block_hash,
                    state = excluded.state,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (wallet, source, filter_identity, last_block_number, last_block_hash, state, reason, datetime.now(timezone.utc).isoformat()),
            )
        return WalletCursor(wallet, source, filter_identity, last_block_number, last_block_hash, state, reason)

    def get_cursor(self, *, wallet: str, source: str) -> WalletCursor | None:
        row = self._connection.execute(
            "SELECT * FROM wallet_cursors WHERE wallet = ? AND source = ?", (wallet, source)
        ).fetchone()
        if row is None:
            return None
        return WalletCursor(
            row["wallet"],
            row["source"],
            row["filter_identity"],
            row["last_block_number"],
            row["last_block_hash"],
            row["state"],
            row["reason"],
        )

    def observation(self, *, wallet: str, as_of_time: str, arrival_cutoff: str) -> WalletObservation:
        return build_wallet_observation(
            self.list_activities(wallet=wallet),
            wallet=wallet,
            as_of_time=as_of_time,
            arrival_cutoff=arrival_cutoff,
        )


__all__ = ["WalletCursor", "WalletObservationStore", "WalletWriteResult"]
