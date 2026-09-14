"""Resumable, bounded historical log backfill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Callable, Iterable, Mapping

from willfly.adapters.robinhood_rpc import JsonRpcError, ReadOnlyRpcClient, RpcLog
from willfly.domain import RawEvent


Clock = Callable[[], str]
PageCallback = Callable[[tuple[RawEvent, ...], int, int], None]


class BackfillError(RuntimeError):
    """Raised when a historical page cannot be accepted safely."""


@dataclass(frozen=True)
class BackfillCheckpoint:
    source: str
    start_block: int
    target_block: int
    next_block: int
    page_size: int
    updated_at: str
    filter_hash: str | None = None


@dataclass(frozen=True)
class BackfillResult:
    source: str
    start_block: int
    target_block: int
    next_block: int
    events: tuple[RawEvent, ...]
    ranges: tuple[tuple[int, int], ...]
    page_sizes: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return self.next_block > self.target_block


class BackfillCheckpointStore:
    """Small SQLite store for progress independent of raw batch acknowledgement."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS backfill_checkpoints (
                source TEXT PRIMARY KEY,
                start_block INTEGER NOT NULL,
                target_block INTEGER NOT NULL,
                next_block INTEGER NOT NULL,
                page_size INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                filter_hash TEXT
            )
            """
        )
        # Migrate legacy stores created before filter binding.
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(backfill_checkpoints)").fetchall()}
        if "filter_hash" not in columns:
            self.connection.execute("ALTER TABLE backfill_checkpoints ADD COLUMN filter_hash TEXT")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "BackfillCheckpointStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def get(self, source: str) -> BackfillCheckpoint | None:
        row = self.connection.execute(
            "SELECT source, start_block, target_block, next_block, page_size, updated_at, filter_hash FROM backfill_checkpoints WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None:
            return None
        # Legacy rows predate filter binding; filter_hash may be NULL.
        values = tuple(row)
        if len(values) == 6:
            values = (*values, None)
        return BackfillCheckpoint(*values)

    def save(self, checkpoint: BackfillCheckpoint) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO backfill_checkpoints(source, start_block, target_block, next_block, page_size, updated_at, filter_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    start_block = excluded.start_block,
                    target_block = excluded.target_block,
                    next_block = excluded.next_block,
                    page_size = excluded.page_size,
                    updated_at = excluded.updated_at,
                    filter_hash = excluded.filter_hash
                """,
                (
                    checkpoint.source,
                    checkpoint.start_block,
                    checkpoint.target_block,
                    checkpoint.next_block,
                    checkpoint.page_size,
                    checkpoint.updated_at,
                    checkpoint.filter_hash,
                ),
            )


def backfill_range(
    client: ReadOnlyRpcClient,
    *,
    address: str | list[str],
    start_block: int,
    target_block: int,
    source: str = "robinhood_rpc_backfill",
    run_id: str = "backfill",
    page_size: int = 2000,
    checkpoint_store: BackfillCheckpointStore | None = None,
    on_page: PageCallback | None = None,
    clock: Clock | None = None,
    retain_events: bool = True,
    expected_filter_hash: str | None = None,
) -> BackfillResult:
    """Fetch a range with adaptive pages and checkpoint after accepted pages.

    When ``retain_events`` is False, pages stream through ``on_page`` without
    accumulating full history in memory; the returned ``events`` tuple is empty
    while ``ranges`` still records durable progress. When
    ``expected_filter_hash`` is set, a stored checkpoint with a different
    filter hash cannot be inherited. Header persistence and parent rebinding
    are handled by the runner's ``on_page`` callback via ``RawBatchStore``.
    """

    if start_block < 0 or target_block < start_block:
        raise ValueError("backfill range is invalid")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if client.check_chain() != 4663:
        raise BackfillError("backfill requires Robinhood chain 4663")
    now = clock or (lambda: datetime.now(timezone.utc).isoformat())
    checkpoint = checkpoint_store.get(source) if checkpoint_store is not None else None
    if checkpoint is not None and checkpoint.start_block != start_block:
        raise BackfillError("checkpoint range does not match requested backfill")
    if checkpoint is not None and checkpoint.target_block != target_block:
        can_extend = checkpoint.target_block < target_block and checkpoint.next_block > checkpoint.target_block
        if not can_extend:
            raise BackfillError("checkpoint range does not match requested backfill")
        checkpoint = BackfillCheckpoint(
            checkpoint.source,
            checkpoint.start_block,
            target_block,
            checkpoint.next_block,
            checkpoint.page_size,
            checkpoint.updated_at,
            checkpoint.filter_hash,
        )
        if checkpoint_store is not None:
            checkpoint_store.save(checkpoint)
    if checkpoint is not None and expected_filter_hash is not None:
        if checkpoint.filter_hash != expected_filter_hash:
            raise BackfillError("checkpoint filter does not match requested backfill")
    cursor = checkpoint.next_block if checkpoint is not None else start_block
    current_page_size = min(page_size, 2000)
    events: list[RawEvent] = []
    ranges: list[tuple[int, int]] = []
    page_sizes: list[int] = []

    while cursor <= target_block:
        clear_cache = getattr(client, "clear_block_cache", None)
        if callable(clear_cache):
            clear_cache()
        end_block = min(cursor + current_page_size - 1, target_block)
        try:
            logs = client.logs(address=address, from_block=cursor, to_block=end_block, max_range=current_page_size)
        except (JsonRpcError, ValueError):
            if current_page_size == 1:
                raise
            current_page_size = max(1, current_page_size // 2)
            continue
        _validate_page(logs, cursor, end_block)
        received_at = now()
        missing_blocks = sorted({log.block_number for log in logs if log.block_timestamp is None})
        prefetch_blocks = getattr(client, "prefetch_blocks", None)
        headers = {}
        if missing_blocks and callable(prefetch_blocks):
            prefetched = prefetch_blocks(missing_blocks)
            headers = {
                header["hash"]: header
                for header in prefetched.values()
                if isinstance(header, Mapping) and isinstance(header.get("hash"), str)
            }
        resolved_logs = [client.resolve_log_time(log, headers) if log.block_timestamp is None else log for log in logs]
        page_events = tuple(_raw_event(log, run_id=run_id, source=source, received_at=received_at) for log in resolved_logs)
        if on_page is not None:
            on_page(page_events, cursor, end_block)
        if retain_events:
            events.extend(page_events)
        ranges.append((cursor, end_block))
        page_sizes.append(current_page_size)
        cursor = end_block + 1
        if checkpoint_store is not None:
            checkpoint_store.save(
                BackfillCheckpoint(source, start_block, target_block, cursor, current_page_size, now(), expected_filter_hash)
            )
        if callable(clear_cache):
            clear_cache()
    return BackfillResult(source, start_block, target_block, cursor, tuple(events), tuple(ranges), tuple(page_sizes))


def _validate_page(logs: Iterable[RpcLog], start_block: int, end_block: int) -> None:
    seen: set[tuple[int, str, str, int]] = set()
    for log in logs:
        if not start_block <= log.block_number <= end_block:
            raise BackfillError("provider returned a log outside the requested page")
        key = (4663, log.block_hash, log.transaction_hash, log.log_index)
        if key in seen:
            raise BackfillError("provider returned a duplicate logical log in one page")
        seen.add(key)


def _raw_event(log: RpcLog, *, run_id: str, source: str, received_at: str) -> RawEvent:
    if log.block_timestamp is None:
        raise BackfillError("missing block timestamp; verified header required")
    parent_hash: str | None = None
    event_time = (
        datetime.fromtimestamp(log.block_timestamp, timezone.utc).isoformat()
        if log.block_timestamp is not None
        else received_at
    )
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": source,
            "source_schema_version": "rpc-log.v0.1",
            "block_number": log.block_number,
            "block_hash": log.block_hash,
            "parent_hash": parent_hash,
            "transaction_hash": log.transaction_hash,
            "log_index": log.log_index,
            "event_time": event_time,
            "received_time": received_at,
            "payload": dict(log.payload),
            "ingestion_run": run_id,
            "canonical_status": "provisional",
        }
    )
