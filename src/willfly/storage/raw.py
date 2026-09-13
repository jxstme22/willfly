"""Append-only compressed raw batches and transactional checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping
from uuid import uuid4

from willfly.domain import RawEvent


class BatchCorruptionError(RuntimeError):
    """Raised when a stored batch cannot be verified or decoded."""


@dataclass(frozen=True)
class StoredBatch:
    batch_id: str
    source: str
    path: Path
    sha256: str
    event_count: int
    byte_count: int
    acknowledged: bool


class RawBatchStore:
    """Own raw batch publication and one metadata writer.

    A batch becomes visible only after its compressed file is atomically renamed
    and its metadata row is committed. Checkpoint acknowledgement is a separate
    transaction, so a process interruption cannot make an uncheckpointed batch
    look acknowledged.
    """

    def __init__(self, root: Path, metadata_path: Path | None = None) -> None:
        self.root = Path(root)
        self.raw_root = self.root / "raw"
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = metadata_path or self.root / "metadata.sqlite3"
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.metadata_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RawBatchStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                event_count INTEGER NOT NULL CHECK (event_count > 0),
                byte_count INTEGER NOT NULL CHECK (byte_count > 0),
                created_at TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                source TEXT PRIMARY KEY,
                last_block_number INTEGER,
                last_block_hash TEXT,
                batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                updated_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    @staticmethod
    def _event_dict(event: RawEvent | Mapping[str, object]) -> dict[str, object]:
        if isinstance(event, RawEvent):
            return event.to_dict()
        return RawEvent.from_dict(event).to_dict()

    @staticmethod
    def _canonical_json(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def publish(self, events: Iterable[RawEvent | Mapping[str, object]], *, source: str, partition_date: str) -> StoredBatch:
        """Atomically publish a non-empty, validated batch.

        ``partition_date`` is supplied by the caller from source event context;
        it is intentionally not derived from wall-clock arrival time.
        """

        if not source or source in {".", ".."} or "/" in source or "\\" in source:
            raise ValueError("source must be a simple partition name")
        if len(partition_date) != 10 or partition_date[4] != "-" or partition_date[7] != "-":
            raise ValueError("partition_date must be YYYY-MM-DD")
        datetime.strptime(partition_date, "%Y-%m-%d")
        records = [self._event_dict(event) for event in events]
        if not records:
            raise ValueError("cannot publish an empty batch")
        payload = b"".join(self._canonical_json(record) + b"\n" for record in records)
        batch_id = hashlib.sha256(payload).hexdigest()[:20]
        existing = self._connection.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if existing is not None:
            if existing["source"] != source:
                raise ValueError("batch already belongs to another source partition")
            self.read(batch_id)  # Do not overwrite or silently repair corrupt acknowledged evidence.
            return self._row_to_batch(existing)
        relative_dir = Path(source) / f"date={partition_date}"
        output_dir = self.raw_root / relative_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / f"batch-{batch_id}.jsonl.gz"
        temp_path = output_dir / f".batch-{batch_id}.{uuid4().hex}.tmp"
        with temp_path.open("wb") as raw_handle:
            with gzip.GzipFile(filename="", fileobj=raw_handle, mode="wb", mtime=0) as compressed:
                compressed.write(payload)
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
        os.replace(temp_path, final_path)
        digest = hashlib.sha256(final_path.read_bytes()).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            self._connection.execute(
                "INSERT INTO batches(batch_id, source, path, sha256, event_count, byte_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (batch_id, source, str(final_path.relative_to(self.root)), digest, len(records), final_path.stat().st_size, created_at),
            )
            self._connection.commit()
        except sqlite3.IntegrityError:
            self._connection.rollback()
            row = self._connection.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if row is None:
                raise
            return self._row_to_batch(row)
        return StoredBatch(batch_id, source, final_path, digest, len(records), final_path.stat().st_size, False)

    def acknowledge(self, batch_id: str, *, source: str, last_block_number: int | None, last_block_hash: str | None) -> None:
        """Commit a checkpoint and acknowledgement in one SQLite transaction."""

        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            row = self._connection.execute("SELECT source FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown batch: {batch_id}")
            if row["source"] != source:
                raise ValueError("checkpoint source does not match batch source")
            self._connection.execute("UPDATE batches SET acknowledged = 1 WHERE batch_id = ?", (batch_id,))
            self._connection.execute(
                """
                INSERT INTO checkpoints(source, last_block_number, last_block_hash, batch_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_block_number = excluded.last_block_number,
                    last_block_hash = excluded.last_block_hash,
                    batch_id = excluded.batch_id,
                    updated_at = excluded.updated_at
                """,
                (source, last_block_number, last_block_hash, batch_id, now),
            )

    def get_checkpoint(self, source: str) -> sqlite3.Row | None:
        return self._connection.execute("SELECT * FROM checkpoints WHERE source = ?", (source,)).fetchone()

    def list_batches(self, *, source: str | None = None) -> list[StoredBatch]:
        if source is None:
            rows = self._connection.execute("SELECT * FROM batches ORDER BY created_at, batch_id").fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM batches WHERE source = ? ORDER BY created_at, batch_id", (source,)).fetchall()
        return [self._row_to_batch(row) for row in rows]

    def read(self, batch_id: str) -> list[RawEvent]:
        row = self._connection.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown batch: {batch_id}")
        path = self.root / row["path"]
        if not path.is_file():
            raise BatchCorruptionError(f"missing batch file: {path}")
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != row["sha256"]:
            raise BatchCorruptionError(f"hash mismatch for batch {batch_id}")
        try:
            with gzip.open(path, "rb") as handle:
                lines = handle.read().splitlines()
            events = [RawEvent.from_dict(json.loads(line)) for line in lines]
        except (OSError, EOFError, json.JSONDecodeError, ValueError) as exc:
            raise BatchCorruptionError(f"cannot decode batch {batch_id}") from exc
        if len(events) != row["event_count"]:
            raise BatchCorruptionError(f"event count mismatch for batch {batch_id}")
        return events

    def verify(self) -> list[str]:
        """Return corrupt batch IDs; valid batches are intentionally quiet."""

        corrupt: list[str] = []
        for batch in self.list_batches():
            try:
                self.read(batch.batch_id)
            except BatchCorruptionError:
                corrupt.append(batch.batch_id)
        return corrupt

    def _row_to_batch(self, row: sqlite3.Row) -> StoredBatch:
        return StoredBatch(
            batch_id=row["batch_id"],
            source=row["source"],
            path=self.root / row["path"],
            sha256=row["sha256"],
            event_count=row["event_count"],
            byte_count=row["byte_count"],
            acknowledged=bool(row["acknowledged"]),
        )
