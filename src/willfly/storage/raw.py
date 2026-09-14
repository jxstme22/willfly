"""Append-only compressed raw batches and transactional checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
class BlockHeader:
    """Immutable chain-header evidence retained independently of selected logs.

    A block can be important to canonicality even when none of the configured
    contracts emitted a log in it.  ``timestamp`` is intentionally optional:
    a provider's zero/missing timestamp is evidence of missing metadata, not a
    reason to invent an instant.
    """

    number: int
    block_hash: str
    parent_hash: str | None
    timestamp: int | None = None
    parent_known: bool = True

    def __post_init__(self) -> None:
        if self.number < 0:
            raise ValueError("block header number must be non-negative")
        _validate_hash(self.block_hash, "block header hash")
        if self.parent_hash is not None:
            _validate_hash(self.parent_hash, "block header parent hash")
        if self.timestamp is not None and self.timestamp < 0:
            raise ValueError("block header timestamp must be non-negative")
        if not isinstance(self.parent_known, bool):
            raise ValueError("block header parent_known must be boolean")


#: Anchor declarations understood by the storage contract. Only ``genesis`` and
#: ``independent_header_cross_check`` can qualify a projection. The explicit
#: unverified value is retained so imported operator declarations are visible,
#: but it can never certify canonical history.
ANCHOR_QUALIFICATIONS = (
    "genesis",
    "independent_header_cross_check",
    "operator_declared_unverified",
)
#: Anchor states that must invalidate or degrade a projection explicitly.
UNSATISFIED_ANCHOR_STATES = (
    "unavailable",
    "mismatch",
    "boundary_crossed",
    "nonconsecutive",
    "config_mismatch",
    "unqualified",
    "unverified",
    "unsupported",
    "unknown",
)

ANCHOR_EVIDENCE_PREFIX = "willfly.anchor-evidence.v1:"


def anchor_evidence_record(kind: str, **fields: object) -> str:
    """Serialize one reviewable, structured anchor evidence record.

    The record is intentionally an identity/invariant check, not a claim of
    finality. An independent header record must identify its provider and the
    matching height/hash; the canonicalizer still verifies it against the
    locally supplied header and active source configuration.
    """

    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("anchor evidence kind must be non-empty text")
    payload = {"schema_version": "1", "kind": kind, **fields}
    return ANCHOR_EVIDENCE_PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":"))


def parse_anchor_evidence(value: str) -> dict[str, object]:
    """Parse one structured anchor evidence record without coercion."""

    if not isinstance(value, str) or not value.startswith(ANCHOR_EVIDENCE_PREFIX):
        raise ValueError("anchor evidence must use the structured v1 format")
    try:
        payload = json.loads(value[len(ANCHOR_EVIDENCE_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise ValueError("anchor evidence is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("anchor evidence must contain an object")
    if payload.get("schema_version") != "1" or not isinstance(payload.get("kind"), str):
        raise ValueError("anchor evidence schema is unsupported")
    return payload


@dataclass(frozen=True)
class AncestryAnchor:
    """A declared, source-verified starting boundary for bounded ancestry.

    The oldest stored header in a bounded live window is not a trusted root. An
    anchor records exactly which block at which height the operator is willing to
    trust as the start of canonical history, together with the evidence that
    justifies that trust and the configuration identity it applies to.
    """

    chain_id: int
    height: int
    block_hash: str
    qualification: str
    evidence: tuple[str, ...]
    config_identity: str
    source: str
    recorded_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, int) or isinstance(self.chain_id, bool) or self.chain_id <= 0:
            raise ValueError("anchor chain_id must be a positive integer")
        if not isinstance(self.height, int) or isinstance(self.height, bool) or self.height < 0:
            raise ValueError("anchor height must be a non-negative integer")
        _validate_hash(self.block_hash, "anchor block hash")
        if self.qualification not in ANCHOR_QUALIFICATIONS:
            raise ValueError("unsupported anchor qualification")
        if not isinstance(self.evidence, tuple) or not self.evidence or not all(
            isinstance(item, str) and bool(item) for item in self.evidence
        ):
            raise ValueError("anchor requires non-empty qualification evidence")
        if not isinstance(self.config_identity, str) or not self.config_identity:
            raise ValueError("anchor requires a configuration identity")
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("anchor requires a source identity")
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise ValueError("anchor recorded_at must be non-empty text")
        parsed = datetime.fromisoformat(self.recorded_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("anchor recorded_at must include a timezone")

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "height": self.height,
            "block_hash": self.block_hash,
            "qualification": self.qualification,
            "evidence": list(self.evidence),
            "config_identity": self.config_identity,
            "source": self.source,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "AncestryAnchor":
        if not isinstance(data, Mapping):
            raise ValueError("anchor must be a JSON object")
        required = {
            "chain_id",
            "height",
            "block_hash",
            "qualification",
            "evidence",
            "config_identity",
            "source",
            "recorded_at",
        }
        if set(data) != required:
            missing = sorted(required - set(data))
            extra = sorted(set(data) - required)
            details = []
            if missing:
                details.append(f"missing fields: {', '.join(missing)}")
            if extra:
                details.append(f"unknown fields: {', '.join(extra)}")
            raise ValueError("invalid anchor fields (" + "; ".join(details) + ")")
        chain_id = data["chain_id"]
        height = data["height"]
        if not isinstance(chain_id, int) or isinstance(chain_id, bool):
            raise ValueError("anchor chain_id must be an integer")
        if not isinstance(height, int) or isinstance(height, bool):
            raise ValueError("anchor height must be an integer")
        text_fields = ("block_hash", "qualification", "config_identity", "source", "recorded_at")
        if any(not isinstance(data[field], str) for field in text_fields):
            raise ValueError("anchor text fields must remain strings")
        evidence = data["evidence"]
        if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
            raise ValueError("anchor evidence must be a list of strings")
        return cls(
            chain_id=chain_id,
            height=height,
            block_hash=data["block_hash"],
            qualification=data["qualification"],
            evidence=tuple(evidence),
            config_identity=data["config_identity"],
            source=data["source"],
            recorded_at=data["recorded_at"],
        )


@dataclass(frozen=True)
class StoredBatch:
    batch_id: str
    source: str
    path: Path
    sha256: str
    event_count: int
    byte_count: int
    acknowledged: bool


@dataclass(frozen=True)
class StoredSnapshot:
    snapshot_id: str
    source: str
    snapshot_type: str
    as_of_time: str
    replaces_snapshot_id: str | None


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
            CREATE TABLE IF NOT EXISTS empty_range_acks (
                source TEXT PRIMARY KEY,
                last_block_number INTEGER,
                last_block_hash TEXT,
                run_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS block_headers (
                block_hash TEXT PRIMARY KEY,
                block_number INTEGER NOT NULL,
                parent_hash TEXT,
                parent_known INTEGER NOT NULL DEFAULT 1,
                block_timestamp INTEGER,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS block_headers_number_idx ON block_headers(block_number, block_hash);
            CREATE TABLE IF NOT EXISTS header_range_evidence (
                source TEXT NOT NULL,
                range_start INTEGER NOT NULL,
                range_end INTEGER NOT NULL,
                run_id TEXT NOT NULL,
                header_count INTEGER NOT NULL,
                missing_blocks TEXT NOT NULL,
                tip_hash TEXT,
                observed_at TEXT NOT NULL,
                PRIMARY KEY(source, range_start, range_end, run_id)
            );
            CREATE TABLE IF NOT EXISTS canonical_event_projections (
                source TEXT NOT NULL,
                event_key TEXT NOT NULL,
                block_number INTEGER,
                block_hash TEXT,
                canonical_status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(source, event_key)
            );
            CREATE TABLE IF NOT EXISTS canonical_checkpoints (
                source TEXT PRIMARY KEY,
                tip_hash TEXT,
                last_block_number INTEGER,
                last_block_hash TEXT,
                state TEXT NOT NULL,
                missing_parent_hashes TEXT NOT NULL,
                anchor_state TEXT NOT NULL DEFAULT 'unavailable',
                repair_reason TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observatory_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                snapshot_type TEXT NOT NULL,
                as_of_time TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                replaces_snapshot_id TEXT REFERENCES observatory_snapshots(snapshot_id),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS observatory_snapshots_source_idx
                ON observatory_snapshots(source, snapshot_type, as_of_time, created_at);
            CREATE TABLE IF NOT EXISTS ancestry_anchors (
                source TEXT PRIMARY KEY,
                chain_id INTEGER NOT NULL,
                height INTEGER NOT NULL,
                block_hash TEXT NOT NULL,
                qualification TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                config_identity TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ancestry_anchor_supersessions (
                superseded_source TEXT PRIMARY KEY,
                successor_source TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        header_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(block_headers)").fetchall()}
        if "parent_known" not in header_columns:
            self._connection.execute("ALTER TABLE block_headers ADD COLUMN parent_known INTEGER NOT NULL DEFAULT 1")
        checkpoint_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(canonical_checkpoints)").fetchall()}
        if "anchor_state" not in checkpoint_columns:
            self._connection.execute(
                "ALTER TABLE canonical_checkpoints ADD COLUMN anchor_state TEXT NOT NULL DEFAULT 'unavailable'"
            )
        if "repair_reason" not in checkpoint_columns:
            self._connection.execute(
                "ALTER TABLE canonical_checkpoints ADD COLUMN repair_reason TEXT NOT NULL DEFAULT ''"
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

    def acknowledge(
        self,
        batch_id: str,
        *,
        source: str,
        last_block_number: int | None,
        last_block_hash: str | None,
        allow_reorg: bool = False,
    ) -> None:
        """Commit a checkpoint and acknowledgement in one SQLite transaction.

        Normal callers must advance the raw cursor monotonically.  The bounded
        canonical-ingest runner may explicitly acknowledge a replacement hash
        while retaining both provisional batches for fork reconciliation.
        """

        if last_block_number is not None and (not isinstance(last_block_number, int) or last_block_number < 0):
            raise ValueError("checkpoint block number must be a non-negative integer")
        if last_block_hash is not None:
            _validate_hash(last_block_hash, "checkpoint block hash")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            row = self._connection.execute("SELECT source FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown batch: {batch_id}")
            if row["source"] != source:
                raise ValueError("checkpoint source does not match batch source")
            prior = self._connection.execute(
                "SELECT last_block_number, last_block_hash FROM checkpoints WHERE source = ?", (source,)
            ).fetchone()
            if not allow_reorg and prior is not None and prior["last_block_number"] is not None and last_block_number is not None:
                if last_block_number < prior["last_block_number"]:
                    raise ValueError("raw checkpoint acknowledgement moved backwards")
                if (
                    last_block_number == prior["last_block_number"]
                    and prior["last_block_hash"] is not None
                    and last_block_hash is not None
                    and prior["last_block_hash"].lower() != last_block_hash.lower()
                ):
                    raise ValueError("raw checkpoint hash changed at an acknowledged height")
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

    def acknowledge_empty_range(
        self, *, source: str, last_block_number: int | None, last_block_hash: str | None, run_id: str
    ) -> None:
        """Acknowledge a zero-event range with header evidence and no batch.

        Empty ranges are evidence, not gaps. The checkpoint records the covered
        head block and its hash (when available) so a restart does not rescan
        silently and an outage remains visible as a missing acknowledgement.
        """

        if not source or source in {".", ".."} or "/" in source or "\\" in source and ":" not in source:
            # Filter-bound sources contain colons (e.g. capture:4663:abc123); only
            # reject path traversal and bare dot names.
            if source in {".", ".."} or "/" in source or "\\" in source:
                raise ValueError("source must be a simple partition name or filter-bound key")
        if not run_id:
            raise ValueError("run_id is required for empty-range acknowledgement")
        if last_block_number is not None and (not isinstance(last_block_number, int) or last_block_number < 0):
            raise ValueError("empty-range block number must be a non-negative integer")
        if last_block_hash is not None:
            _validate_hash(last_block_hash, "empty-range block hash")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            prior = self._connection.execute(
                "SELECT last_block_number, last_block_hash FROM empty_range_acks WHERE source = ?", (source,)
            ).fetchone()
            if prior is not None and prior["last_block_number"] is not None and last_block_number is not None:
                if last_block_number < prior["last_block_number"]:
                    raise ValueError("empty-range acknowledgement moved backwards")
                if (
                    last_block_number == prior["last_block_number"]
                    and prior["last_block_hash"] is not None
                    and last_block_hash is not None
                    and prior["last_block_hash"].lower() != last_block_hash.lower()
                ):
                    raise ValueError("empty-range hash changed at an acknowledged height")
            self._connection.execute(
                """
                INSERT INTO empty_range_acks(source, last_block_number, last_block_hash, run_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_block_number = excluded.last_block_number,
                    last_block_hash = excluded.last_block_hash,
                    run_id = excluded.run_id,
                    updated_at = excluded.updated_at
                """,
                (source, last_block_number, last_block_hash, run_id, now),
            )

    def get_empty_range_ack(self, source: str) -> sqlite3.Row | None:
        return self._connection.execute("SELECT * FROM empty_range_acks WHERE source = ?", (source,)).fetchone()

    def persist_headers(self, headers: Iterable[BlockHeader]) -> tuple[BlockHeader, ...]:
        """Store immutable header evidence, upgrading only previously unknown fields.

        A hash may be observed repeatedly, including through a restarted
        process. Conflicting known parent hashes or timestamps are refused so a
        faulty provider cannot silently rewrite ancestry evidence.
        """

        records = tuple(headers)
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            for header in records:
                if not isinstance(header, BlockHeader):
                    raise TypeError("headers must be BlockHeader instances")
                existing = self._connection.execute(
                    "SELECT block_number, parent_hash, parent_known, block_timestamp FROM block_headers WHERE block_hash = ?",
                    (header.block_hash,),
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        """
                        INSERT INTO block_headers(block_hash, block_number, parent_hash, parent_known, block_timestamp, first_seen_at, last_seen_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (header.block_hash, header.number, header.parent_hash, int(header.parent_known), header.timestamp, now, now),
                    )
                    continue
                if existing["block_number"] != header.number:
                    raise ValueError(f"conflicting block number for header {header.block_hash}")
                known_parent = existing["parent_hash"]
                known_parent_known = bool(existing["parent_known"])
                known_timestamp = existing["block_timestamp"]
                if known_parent_known and header.parent_known and known_parent != header.parent_hash:
                    raise ValueError(f"conflicting parent hash for header {header.block_hash}")
                if known_timestamp is not None and header.timestamp is not None and known_timestamp != header.timestamp:
                    raise ValueError(f"conflicting timestamp for header {header.block_hash}")
                self._connection.execute(
                    """
                    UPDATE block_headers
                    SET parent_hash = CASE WHEN parent_known = 0 AND ? THEN ? ELSE parent_hash END,
                        parent_known = CASE WHEN parent_known = 1 OR ? = 0 THEN parent_known ELSE 1 END,
                        block_timestamp = COALESCE(block_timestamp, ?),
                        last_seen_at = ?
                    WHERE block_hash = ?
                    """,
                    (int(header.parent_known), header.parent_hash, int(header.parent_known), header.timestamp, now, header.block_hash),
                )
        return records

    def list_headers(self) -> list[BlockHeader]:
        rows = self._connection.execute(
            "SELECT block_number, block_hash, parent_hash, parent_known, block_timestamp FROM block_headers ORDER BY block_number, block_hash"
        ).fetchall()
        return [BlockHeader(row["block_number"], row["block_hash"], row["parent_hash"], row["block_timestamp"], bool(row["parent_known"])) for row in rows]

    def get_header(self, block_hash: str) -> BlockHeader | None:
        row = self._connection.execute(
            "SELECT block_number, block_hash, parent_hash, parent_known, block_timestamp FROM block_headers WHERE block_hash = ?",
            (block_hash,),
        ).fetchone()
        if row is None:
            return None
        return BlockHeader(row["block_number"], row["block_hash"], row["parent_hash"], row["block_timestamp"], bool(row["parent_known"]))

    def save_ancestry_anchor(self, anchor: AncestryAnchor) -> AncestryAnchor:
        """Persist one source's declared ancestry anchor.

        Re-recording an identical anchor is idempotent. A conflicting anchor for
        the same source (different height/hash/chain/qualification/config) is
        refused rather than silently replacing trusted lineage evidence.
        """

        if not isinstance(anchor, AncestryAnchor):
            raise TypeError("anchor must be an AncestryAnchor")
        if anchor.qualification == "operator_declared_unverified":
            raise ValueError("unverified anchor declarations cannot be persisted as trusted state")
        existing = self.get_ancestry_anchor(anchor.source)
        if existing is not None:
            if existing.to_dict() != anchor.to_dict():
                raise ValueError("conflicting ancestry anchor already stored for this source")
            return existing
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO ancestry_anchors(source, chain_id, height, block_hash, qualification, evidence_json, config_identity, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anchor.source,
                    anchor.chain_id,
                    anchor.height,
                    anchor.block_hash,
                    anchor.qualification,
                    json.dumps(list(anchor.evidence)),
                    anchor.config_identity,
                    anchor.recorded_at,
                ),
            )
        return anchor

    def save_requalified_ancestry_anchor(
        self, anchor: AncestryAnchor, *, supersedes_source: str, reason: str
    ) -> AncestryAnchor:
        """Persist a new qualified namespace linked to an older anchor.

        A boundary-crossing fork cannot rewrite the old source. Requalification
        creates a new source namespace and an immutable supersession link so
        historical projections remain inspectable and the operator's recovery
        decision is auditable.
        """

        if not isinstance(anchor, AncestryAnchor):
            raise TypeError("anchor must be an AncestryAnchor")
        if anchor.qualification == "operator_declared_unverified":
            raise ValueError("unverified anchor declarations cannot be persisted as trusted state")
        if not isinstance(supersedes_source, str) or not supersedes_source or supersedes_source == anchor.source:
            raise ValueError("superseded source must differ from successor source")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("supersession reason is required")
        if self.get_ancestry_anchor(supersedes_source) is None:
            raise KeyError(f"unknown superseded anchor source: {supersedes_source}")
        existing = self.get_ancestry_anchor(anchor.source)
        if existing is not None:
            link = self.get_anchor_supersession(supersedes_source)
            if existing.to_dict() == anchor.to_dict() and link is not None and link["successor_source"] == anchor.source:
                return existing
            raise ValueError("conflicting ancestry anchor already stored for successor source")
        existing_link = self.get_anchor_supersession(supersedes_source)
        if existing_link is not None:
            raise ValueError("superseded source already has a requalification")
        successor_link = self._connection.execute(
            "SELECT superseded_source FROM ancestry_anchor_supersessions WHERE successor_source = ?",
            (anchor.source,),
        ).fetchone()
        if successor_link is not None:
            raise ValueError("successor source is already a requalified namespace")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO ancestry_anchors(source, chain_id, height, block_hash, qualification, evidence_json, config_identity, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anchor.source,
                    anchor.chain_id,
                    anchor.height,
                    anchor.block_hash,
                    anchor.qualification,
                    json.dumps(list(anchor.evidence)),
                    anchor.config_identity,
                    anchor.recorded_at,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO ancestry_anchor_supersessions(superseded_source, successor_source, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (supersedes_source, anchor.source, reason.strip(), now),
            )
        return anchor

    def get_anchor_supersession(self, superseded_source: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM ancestry_anchor_supersessions WHERE superseded_source = ?",
            (superseded_source,),
        ).fetchone()

    def list_anchor_supersessions(self) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM ancestry_anchor_supersessions ORDER BY created_at, superseded_source"
        ).fetchall()

    def get_ancestry_anchor(self, source: str) -> AncestryAnchor | None:
        row = self._connection.execute("SELECT * FROM ancestry_anchors WHERE source = ?", (source,)).fetchone()
        if row is None:
            return None
        evidence = json.loads(row["evidence_json"])
        return AncestryAnchor.from_dict(
            {
                "chain_id": row["chain_id"],
                "height": row["height"],
                "block_hash": row["block_hash"],
                "qualification": row["qualification"],
                "evidence": evidence,
                "config_identity": row["config_identity"],
                "source": row["source"],
                "recorded_at": row["recorded_at"],
            }
        )

    def list_ancestry_anchors(self) -> list[AncestryAnchor]:
        rows = self._connection.execute("SELECT source FROM ancestry_anchors ORDER BY source").fetchall()
        return [anchor for row in rows if (anchor := self.get_ancestry_anchor(row["source"])) is not None]

    def record_header_range(
        self,
        *,
        source: str,
        range_start: int,
        range_end: int,
        run_id: str,
        headers: Iterable[BlockHeader],
        missing_blocks: Iterable[int] = (),
    ) -> None:
        """Retain both complete header coverage and explicit acquisition gaps."""

        if range_start < 0 or range_end < range_start:
            raise ValueError("header range is invalid")
        if not run_id:
            raise ValueError("run_id is required for header evidence")
        records = tuple(headers)
        missing = tuple(sorted(set(missing_blocks)))
        if any(block < range_start or block > range_end for block in missing):
            raise ValueError("missing header block lies outside recorded range")
        tip = next((header.block_hash for header in records if header.number == range_end), None)
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO header_range_evidence(source, range_start, range_end, run_id, header_count, missing_blocks, tip_hash, observed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, range_start, range_end, run_id) DO UPDATE SET
                    header_count = excluded.header_count,
                    missing_blocks = excluded.missing_blocks,
                    tip_hash = excluded.tip_hash,
                    observed_at = excluded.observed_at
                """,
                (source, range_start, range_end, run_id, len(records), json.dumps(missing), tip, now),
            )

    def list_header_ranges(self, source: str) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM header_range_evidence WHERE source = ? ORDER BY observed_at, range_start, range_end",
            (source,),
        ).fetchall()

    def events_for_source(self, source: str) -> tuple[RawEvent, ...]:
        return tuple(event for batch in self.list_batches(source=source) for event in self.read(batch.batch_id))

    def canonical_events_for_source(self, source: str) -> tuple[RawEvent, ...]:
        """Return only events covered by a resolved canonical projection.

        Raw batches retain their original provisional status forever.  The
        derived projection is the authority after fork reconciliation, so a
        downstream causal dataset must not consume a raw batch directly or
        silently treat an unresolved window as canonical history.
        """

        checkpoint = self.get_canonical_checkpoint(source)
        if checkpoint is None or checkpoint["state"] != "canonical":
            return ()
        statuses = {
            row["event_key"]: row["canonical_status"]
            for row in self.list_canonical_projection(source)
            if row["canonical_status"] == "canonical"
        }
        if not statuses:
            return ()
        return tuple(
            replace(event, canonical_status="canonical")
            for event in self.events_for_source(source)
            if _event_key(event) in statuses
        )

    def rebuild_canonical_projection(
        self,
        *,
        source: str,
        tip_hash: str,
        confirmations: int = 0,
        chain_id: int | None = None,
        config_identity: str | None = None,
    ):
        """Atomically replace a source's derived fork projection from raw evidence.

        Raw batches remain append-only. The derived rows and canonical
        checkpoint change together, so a restart never observes a half-applied
        fork repair. A persisted, source-verified ancestry anchor is used when
        available so a bounded window can resolve without fetching to genesis.
        """

        # Import lazily to keep storage independent at module import time.
        from willfly.ingest.canonicalize import canonicalize_events

        anchor = self.get_ancestry_anchor(source)
        result = canonicalize_events(
            self.events_for_source(source),
            tip_hash=tip_hash,
            headers=self.list_headers(),
            confirmations=confirmations,
            anchor=anchor,
            expected_chain_id=chain_id,
            expected_config_identity=config_identity,
        )
        states = [
            *((event, "canonical") for event in result.canonical_events),
            *((event, "orphaned") for event in result.orphaned_events),
            *((event, "quarantined") for event in result.quarantined_events),
            *((event, "unresolved") for event in result.unresolved_events),
        ]
        tip = self.get_header(tip_hash)
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute("DELETE FROM canonical_event_projections WHERE source = ?", (source,))
            self._connection.executemany(
                """
                INSERT INTO canonical_event_projections(source, event_key, block_number, block_hash, canonical_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        source,
                        _event_key(event),
                        event.block_number,
                        event.block_hash,
                        status,
                        now,
                    )
                    for event, status in states
                ],
            )
            resolved = result.is_resolved and tip is not None
            self._connection.execute(
                """
                INSERT INTO canonical_checkpoints(source, tip_hash, last_block_number, last_block_hash, state, missing_parent_hashes, anchor_state, repair_reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)
                ON CONFLICT(source) DO UPDATE SET
                    tip_hash = excluded.tip_hash,
                    last_block_number = excluded.last_block_number,
                    last_block_hash = excluded.last_block_hash,
                    state = excluded.state,
                    missing_parent_hashes = excluded.missing_parent_hashes,
                    anchor_state = excluded.anchor_state,
                    repair_reason = excluded.repair_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    source,
                    tip_hash,
                    tip.number if resolved else None,
                    tip.block_hash if resolved else None,
                    "canonical" if resolved else "unresolved",
                    json.dumps(result.missing_parent_hashes),
                    result.anchor_state,
                    now,
                ),
            )
        return result

    def get_canonical_checkpoint(self, source: str) -> sqlite3.Row | None:
        return self._connection.execute("SELECT * FROM canonical_checkpoints WHERE source = ?", (source,)).fetchone()

    def mark_canonical_needs_repair(self, *, source: str, tip_hash: str | None, reason: str) -> None:
        """Invalidate the derived projection until bounded lineage replay succeeds."""

        if not source:
            raise ValueError("canonical repair source is required")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("canonical repair reason is required")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute("DELETE FROM canonical_event_projections WHERE source = ?", (source,))
            self._connection.execute(
                """
                INSERT INTO canonical_checkpoints(
                    source, tip_hash, last_block_number, last_block_hash, state,
                    missing_parent_hashes, anchor_state, repair_reason, updated_at
                ) VALUES (?, ?, NULL, NULL, 'needs_repair', '[]', 'unavailable', ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    tip_hash = excluded.tip_hash,
                    last_block_number = NULL,
                    last_block_hash = NULL,
                    state = 'needs_repair',
                    missing_parent_hashes = '[]',
                    anchor_state = 'unavailable',
                    repair_reason = excluded.repair_reason,
                    updated_at = excluded.updated_at
                """,
                (source, tip_hash, reason.strip(), now),
            )

    def list_canonical_projection(self, source: str) -> list[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM canonical_event_projections WHERE source = ? ORDER BY block_number, event_key",
            (source,),
        ).fetchall()

    def save_snapshot(
        self,
        snapshot: Mapping[str, object] | object,
        *,
        source: str,
        snapshot_type: str = "observatory_projection",
        replaces_snapshot_id: str | None = None,
    ) -> StoredSnapshot:
        """Persist a typed immutable projection bundle in the raw-store database."""

        if not source or source in {".", ".."} or "/" in source or "\\" in source:
            raise ValueError("snapshot source must be a simple key")
        if not snapshot_type or not snapshot_type.replace("_", "").replace("-", "").isalnum():
            raise ValueError("snapshot_type must be a simple identifier")
        if hasattr(snapshot, "to_dict"):
            payload = snapshot.to_dict()  # type: ignore[union-attr]
        elif isinstance(snapshot, Mapping):
            payload = dict(snapshot)
        else:
            raise TypeError("snapshot must be a mapping or provide to_dict")
        if not isinstance(payload, Mapping):
            raise TypeError("snapshot serialization must be an object")
        as_of_time = payload.get("as_of_time")
        if not isinstance(as_of_time, str):
            raise ValueError("snapshot must include as_of_time")
        parsed_as_of = datetime.fromisoformat(as_of_time.replace("Z", "+00:00"))
        if parsed_as_of.tzinfo is None:
            raise ValueError("snapshot as_of_time must include a timezone")
        payload_json = self._canonical_json(payload).decode("utf-8")
        snapshot_id = hashlib.sha256(
            self._canonical_json({"source": source, "snapshot_type": snapshot_type, "payload": payload})
        ).hexdigest()[:24]
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            if replaces_snapshot_id is not None:
                prior = self._connection.execute(
                    "SELECT source, snapshot_type FROM observatory_snapshots WHERE snapshot_id = ?", (replaces_snapshot_id,)
                ).fetchone()
                if prior is None:
                    raise KeyError(f"unknown prior snapshot: {replaces_snapshot_id}")
                if prior["source"] != source or prior["snapshot_type"] != snapshot_type:
                    raise ValueError("replacement snapshot must share source and type")
            existing = self._connection.execute(
                "SELECT * FROM observatory_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != payload_json or existing["source"] != source:
                    raise ValueError("snapshot hash collision or conflicting snapshot evidence")
                return self._row_to_snapshot(existing)
            self._connection.execute(
                """
                INSERT INTO observatory_snapshots(snapshot_id, source, snapshot_type, as_of_time, payload_json, replaces_snapshot_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, source, snapshot_type, as_of_time, payload_json, replaces_snapshot_id, now),
            )
        return StoredSnapshot(snapshot_id, source, snapshot_type, as_of_time, replaces_snapshot_id)

    def load_snapshot(self, snapshot_id: str) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT payload_json FROM observatory_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown snapshot: {snapshot_id}")
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            raise ValueError("stored snapshot payload is not an object")
        return payload

    def list_snapshots(self, *, source: str | None = None, snapshot_type: str | None = None) -> list[StoredSnapshot]:
        clauses: list[str] = []
        params: list[str] = []
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if snapshot_type is not None:
            clauses.append("snapshot_type = ?")
            params.append(snapshot_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._connection.execute(
            "SELECT * FROM observatory_snapshots" + where + " ORDER BY as_of_time, created_at, snapshot_id", params
        ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

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

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> StoredSnapshot:
        return StoredSnapshot(
            snapshot_id=row["snapshot_id"],
            source=row["source"],
            snapshot_type=row["snapshot_type"],
            as_of_time=row["as_of_time"],
            replaces_snapshot_id=row["replaces_snapshot_id"],
        )


def _validate_hash(value: str, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 66 or not value.startswith("0x"):
        raise ValueError(f"{field_name} must be a 32-byte hex value")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a 32-byte hex value") from exc


def _event_key(event: RawEvent) -> str:
    return json.dumps(event.logical_key, separators=(",", ":"), ensure_ascii=False)
