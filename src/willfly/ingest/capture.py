"""Bounded polling capture for configured Robinhood Chain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient
from willfly.domain import RawEvent


Clock = Callable[[], str]


@dataclass(frozen=True)
class CaptureResult:
    chain_id: int
    from_block: int
    to_block: int
    received_at: str
    events: tuple[RawEvent, ...]
    parent_links: tuple[tuple[str, str | None], ...] = ()


def capture_once(
    client: ReadOnlyRpcClient,
    *,
    addresses: list[str],
    from_block: int,
    run_id: str,
    clock: Clock | None = None,
    to_block: int | None = None,
) -> CaptureResult:
    """Read one bounded block range and materialize raw events.

    The current head is read after chain identity validation. If no blocks are
    available after ``from_block``, the result is an empty, explicit checkpoint
    range rather than a fabricated event. ``to_block`` further bounds the read
    so CLI ``--to-block`` is honored; the default preserves the legacy
    head-bounded behavior.
    """

    if not addresses:
        raise ValueError("at least one contract address is required")
    if from_block < 0:
        raise ValueError("from_block must be non-negative")
    if to_block is not None and to_block < from_block:
        raise ValueError("block range is invalid")
    now = clock or (lambda: datetime.now(timezone.utc).isoformat())
    chain_id = client.check_chain()
    head = client.block_number()
    if head < from_block:
        return CaptureResult(chain_id, from_block, head, now(), ())
    head = min(head, from_block + 1999)
    if to_block is not None:
        head = min(head, to_block)
    logs = client.logs(address=addresses, from_block=from_block, to_block=head)
    received_at = now()
    headers = {}
    logs = [client.resolve_log_time(log, headers) for log in logs]
    # Resolve parent hashes through the validated headers already fetched for
    # time resolution; quiet blocks between log blocks stay outside this window
    # and are the ancestry fetcher's responsibility.
    parents: dict[str, str | None] = {}
    for block_hash, header in headers.items():
        if isinstance(header, dict):
            parent = header.get("parentHash")
            parents[block_hash] = parent if isinstance(parent, str) else None
    events = tuple(
        RawEvent.from_dict(
            {
                "chain_id": chain_id,
                "source": "robinhood_rpc",
                "source_schema_version": "rpc-log.v0.1",
                "block_number": log.block_number,
                "block_hash": log.block_hash,
                "parent_hash": parents.get(log.block_hash),
                "transaction_hash": log.transaction_hash,
                "log_index": log.log_index,
                "event_time": _block_time(log.block_timestamp, received_at),
                "received_time": received_at,
                "payload": log.payload,
                "ingestion_run": run_id,
                "canonical_status": "provisional",
            }
        )
        for log in logs
    )
    parent_links = tuple(sorted(parents.items()))
    return CaptureResult(chain_id, from_block, head, received_at, events, parent_links)


def _block_time(block_timestamp: int | None, fallback: str) -> str:
    if block_timestamp is None:
        raise ValueError("missing block timestamp; fetch verified header before capture")
    return datetime.fromtimestamp(block_timestamp, timezone.utc).isoformat()
