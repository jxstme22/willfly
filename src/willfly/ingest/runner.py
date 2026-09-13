"""Durable bounded capture/backfill orchestration for M1-02.

This module wires validated RPC reads to atomic raw-batch persistence with
filter-bound checkpoints. It never signs or broadcasts; it only uses the
read-only client surface.

Contracts:
- Filter identity binds chain, addresses, ABI hashes and event families. A
  changed filter cannot inherit a prior cursor.
- Non-empty pages are published before acknowledgement. Empty ranges are
  acknowledged with header evidence and no batch.
- Pages stream without retaining full history when ``retain_events`` is False.
- Run manifests record run ID, chain/filter/ABI/config hashes, operator
  start/stop, provider identity, attempted and acknowledged ranges, header
  evidence, errors and retained batches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient
from willfly.domain import RawEvent
from willfly.ingest.backfill import BackfillCheckpointStore, BackfillError, backfill_range
from willfly.ingest.capture import capture_once
from willfly.ingest.supervisor import redact_error
from willfly.storage.raw import BlockHeader, RawBatchStore

Clock = Callable[[], str]


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def filter_identity(
    *,
    chain_id: int,
    addresses: Sequence[str],
    abi_hashes: Sequence[str] = (),
    event_families: Sequence[str] = (),
) -> str:
    """Return a stable filter hash binding chain, addresses, ABIs and families."""
    normalized = {
        "chain_id": chain_id,
        "addresses": sorted(addr.lower() for addr in addresses),
        "abi_hashes": sorted(abi_hashes),
        "event_families": sorted(event_families),
    }
    return hashlib.sha256(canonical_json(normalized)).hexdigest()


def short_hash(full_hash: str, length: int = 16) -> str:
    return full_hash[:length]


def checkpoint_source(base: str, chain_id: int, filter_hash: str) -> str:
    return f"{base}:{chain_id}:{short_hash(filter_hash)}"


def config_hash_for_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def partition_date_for_events(events: Sequence[RawEvent], fallback: str) -> str:
    if events:
        # Use the earliest event_time date as source-event context, not wall-clock.
        dates = sorted(event.event_time[:10] for event in events)
        candidate = dates[0]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
        except ValueError:
            pass
    try:
        datetime.strptime(fallback[:10], "%Y-%m-%d")
        return fallback[:10]
    except ValueError as exc:
        raise ValueError("partition_date fallback must be YYYY-MM-DD") from exc


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    command: str
    chain_id: int
    filter_hash: str
    checkpoint_source: str
    config_path: str
    config_hash: str
    abi_hashes: tuple[str, ...]
    addresses: tuple[str, ...]
    attempted_range: tuple[int, int]
    acknowledged_range: tuple[int, int] | None
    batches: tuple[str, ...]
    event_count: int
    empty: bool
    provider_endpoint: str
    operator_started_at: str
    operator_finished_at: str
    header_evidence: Mapping[str, Any]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["batches"] = list(self.batches)
        data["abi_hashes"] = list(self.abi_hashes)
        data["addresses"] = list(self.addresses)
        data["attempted_range"] = list(self.attempted_range)
        data["acknowledged_range"] = list(self.acknowledged_range) if self.acknowledged_range else None
        data["errors"] = list(self.errors)
        return data


def _run_id(prefix: str, payload: Any) -> str:
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _header_from_rpc(value: object, expected_number: int) -> BlockHeader:
    """Normalize a provider header without inventing absent timestamp metadata."""

    if not isinstance(value, Mapping):
        raise ValueError("header response is not an object")
    number_value = value.get("number")
    if isinstance(number_value, str) and number_value.startswith("0x"):
        number = int(number_value, 16)
    elif isinstance(number_value, int):
        number = number_value
    else:
        raise ValueError("header has no valid number")
    if number != expected_number:
        raise ValueError("header number does not match requested block")
    block_hash = value.get("hash")
    if not isinstance(block_hash, str):
        raise ValueError("header has no hash")
    parent_present = "parentHash" in value
    parent_hash = value.get("parentHash")
    if parent_hash is not None and not isinstance(parent_hash, str):
        raise ValueError("header parent hash is invalid")
    timestamp_value = value.get("timestamp")
    if timestamp_value is None:
        timestamp = None
    elif isinstance(timestamp_value, str) and timestamp_value.startswith("0x"):
        timestamp = int(timestamp_value, 16) or None
    elif isinstance(timestamp_value, int):
        timestamp = timestamp_value or None
    else:
        raise ValueError("header timestamp is invalid")
    # Genesis has no parent even though EVM RPC often returns a zero hash.
    if number == 0 and parent_hash == "0x" + "00" * 32:
        parent_hash = None
    return BlockHeader(number, block_hash, parent_hash, timestamp, parent_present or number == 0)


def _capture_headers(
    client: ReadOnlyRpcClient, *, from_block: int, to_block: int
) -> tuple[tuple[BlockHeader, ...], tuple[int, ...], tuple[str, ...]]:
    """Fetch every requested header so silent blocks remain ancestry evidence."""

    headers: list[BlockHeader] = []
    missing: list[int] = []
    errors: list[str] = []
    for block_number in range(from_block, to_block + 1):
        try:
            headers.append(_header_from_rpc(client.block(block_number), block_number))
        except Exception as exc:  # Header gaps are retained and make the source non-healthy.
            missing.append(block_number)
            errors.append(f"header[{block_number}] unavailable: {redact_error(exc)}")
    return tuple(headers), tuple(missing), tuple(errors)


def _rebind_header_context(events: Sequence[RawEvent], headers: Sequence[BlockHeader]) -> tuple[RawEvent, ...]:
    by_hash = {header.block_hash.lower(): header for header in headers}
    rebound: list[RawEvent] = []
    for event in events:
        header = by_hash.get((event.block_hash or "").lower())
        rebound.append(replace(event, parent_hash=header.parent_hash) if header is not None else event)
    return tuple(rebound)


def _reconcile_if_tipped(store: RawBatchStore, *, source: str, headers: Sequence[BlockHeader], tip_block: int) -> str | None:
    tip = next((header for header in headers if header.number == tip_block), None)
    if tip is None:
        return None
    store.rebuild_canonical_projection(source=source, tip_hash=tip.block_hash)
    return tip.block_hash


def capture_to_store(
    client: ReadOnlyRpcClient,
    store: RawBatchStore,
    *,
    addresses: list[str],
    from_block: int,
    to_block: int,
    run_id: str,
    base_source: str = "capture",
    config_path: str = "",
    config_hash: str = "",
    abi_hashes: Sequence[str] = (),
    event_families: Sequence[str] = (),
    provider_endpoint: str = "",
    clock: Clock | None = None,
) -> RunManifest:
    """Execute one bounded capture and persist it durably."""
    if not addresses:
        raise ValueError("at least one contract address is required")
    if from_block < 0 or to_block < from_block:
        raise ValueError("block range is invalid")
    now = clock or (lambda: datetime.now(timezone.utc).isoformat())
    started = now()
    chain_id = client.check_chain()
    filt_hash = filter_identity(
        chain_id=chain_id, addresses=addresses, abi_hashes=abi_hashes, event_families=event_families
    )
    source_key = checkpoint_source(base_source, chain_id, filt_hash)
    result = capture_once(
        client, addresses=addresses, from_block=from_block, to_block=to_block, run_id=run_id, clock=clock
    )
    headers, header_gaps, header_errors = _capture_headers(client, from_block=from_block, to_block=result.to_block)
    store.persist_headers(headers)
    store.record_header_range(
        source=source_key,
        range_start=from_block,
        range_end=result.to_block,
        run_id=run_id,
        headers=headers,
        missing_blocks=header_gaps,
    )
    durable_events = _rebind_header_context(result.events, headers)
    attempted = (from_block, to_block)
    acknowledged: tuple[int, int] | None = None
    batches: list[str] = []
    header_evidence: dict[str, Any] = {
        "head_at_capture": result.to_block,
        "chain_id": result.chain_id,
        "header_count": len(headers),
        "header_gaps": list(header_gaps),
    }
    if durable_events:
        partition = partition_date_for_events(list(durable_events), result.received_at)
        batch = store.publish(list(durable_events), source=source_key, partition_date=partition)
        # Acknowledge only after durable publication.
        last = max(event.block_number for event in durable_events if event.block_number is not None)
        last_hash = next(
            (event.block_hash for event in reversed(durable_events) if event.block_hash), None
        )
        store.acknowledge(
            batch.batch_id, source=source_key, last_block_number=last, last_block_hash=last_hash
        )
        batches.append(batch.batch_id)
        acknowledged = (from_block, result.to_block)
        header_evidence["last_block_number"] = last
        header_evidence["last_block_hash"] = last_hash
        header_evidence["batch_id"] = batch.batch_id
        event_count = len(durable_events)
        empty = False
    else:
        # Empty range: record header evidence without fabricating events.
        tip = next((header for header in headers if header.number == result.to_block), None)
        if tip is not None:
            header_evidence["empty_range_head_hash"] = tip.block_hash
            header_evidence["empty_range_head_number"] = tip.number
        store.acknowledge_empty_range(
            source=source_key,
            last_block_number=result.to_block,
            last_block_hash=header_evidence.get("empty_range_head_hash"),
            run_id=run_id,
        )
        acknowledged = (from_block, result.to_block)
        event_count = 0
        empty = True
    tip_hash = _reconcile_if_tipped(store, source=source_key, headers=headers, tip_block=result.to_block)
    header_evidence["canonical_tip_hash"] = tip_hash
    finished = now()
    manifest = RunManifest(
        run_id=run_id,
        command="capture",
        chain_id=chain_id,
        filter_hash=filt_hash,
        checkpoint_source=source_key,
        config_path=config_path,
        config_hash=config_hash,
        abi_hashes=tuple(abi_hashes),
        addresses=tuple(addresses),
        attempted_range=attempted,
        acknowledged_range=acknowledged,
        batches=tuple(batches),
        event_count=event_count,
        empty=empty,
        provider_endpoint=provider_endpoint,
        operator_started_at=started,
        operator_finished_at=finished,
        header_evidence=header_evidence,
        errors=header_errors,
    )
    _write_manifest(store.root, manifest)
    return manifest


def backfill_to_store(
    client: ReadOnlyRpcClient,
    store: RawBatchStore,
    *,
    addresses: list[str] | str,
    start_block: int,
    target_block: int,
    run_id: str,
    base_source: str = "backfill",
    config_path: str = "",
    config_hash: str = "",
    abi_hashes: Sequence[str] = (),
    event_families: Sequence[str] = (),
    provider_endpoint: str = "",
    page_size: int = 2000,
    checkpoint_store: BackfillCheckpointStore | None = None,
    clock: Clock | None = None,
) -> RunManifest:
    """Stream a bounded backfill to durable batches without retaining history."""
    if isinstance(addresses, str):
        address_list = [addresses]
    else:
        address_list = list(addresses)
    if not address_list:
        raise ValueError("at least one contract address is required")
    if start_block < 0 or target_block < start_block:
        raise ValueError("backfill range is invalid")
    now = clock or (lambda: datetime.now(timezone.utc).isoformat())
    started = now()
    chain_id = client.check_chain()
    filt_hash = filter_identity(
        chain_id=chain_id, addresses=address_list, abi_hashes=abi_hashes, event_families=event_families
    )
    source_key = checkpoint_source(base_source, chain_id, filt_hash)
    batch_ids: list[str] = []
    covered: list[tuple[int, int]] = []
    total_events = 0
    all_headers: list[BlockHeader] = []
    header_gaps: list[int] = []
    header_errors: list[str] = []

    def on_page(page_events: tuple[RawEvent, ...], page_from: int, page_to: int) -> None:
        nonlocal total_events
        covered.append((page_from, page_to))
        headers, gaps, errors = _capture_headers(client, from_block=page_from, to_block=page_to)
        store.persist_headers(headers)
        store.record_header_range(
            source=source_key,
            range_start=page_from,
            range_end=page_to,
            run_id=run_id,
            headers=headers,
            missing_blocks=gaps,
        )
        all_headers.extend(headers)
        header_gaps.extend(gaps)
        header_errors.extend(errors)
        if not page_events:
            head = next((header for header in headers if header.number == page_to), None)
            store.acknowledge_empty_range(
                source=source_key,
                last_block_number=page_to,
                last_block_hash=head.block_hash if head is not None else None,
                run_id=run_id,
            )
            return
        rebound = _rebind_header_context(page_events, headers)
        partition = partition_date_for_events(list(rebound), now())
        # Rebind each page's ingestion_run to the durable run_id without mutating event time.
        rebound = tuple(
            RawEvent.from_dict({**event.to_dict(), "ingestion_run": run_id})
            for event in rebound
        )
        batch = store.publish(list(rebound), source=source_key, partition_date=partition)
        # Checkpoint acknowledgement for raw batches happens via BackfillCheckpointStore
        # after on_page returns; raw-store checkpoint tracks the latest batch.
        last = max(event.block_number for event in rebound if event.block_number is not None)
        last_hash = next(
            (event.block_hash for event in reversed(rebound) if event.block_hash), None
        )
        store.acknowledge(
            batch.batch_id, source=source_key, last_block_number=last, last_block_hash=last_hash
        )
        batch_ids.append(batch.batch_id)
        total_events += len(rebound)

    # Use filter-bound checkpoint source so changed filters cannot inherit cursors.
    # BackfillCheckpointStore gains an optional filter_hash binding; fall back to
    # source-key comparison for stores without the new column.
    result = backfill_range(
        client,
        address=address_list if len(address_list) > 1 else address_list[0],
        start_block=start_block,
        target_block=target_block,
        source=source_key,
        run_id=run_id,
        page_size=min(page_size, 2000),
        checkpoint_store=checkpoint_store,
        on_page=on_page,
        clock=clock,
        retain_events=False,
        expected_filter_hash=filt_hash,
    )
    canonical_tip = _reconcile_if_tipped(store, source=source_key, headers=all_headers, tip_block=target_block)
    header_evidence = {
        "chain_id": chain_id,
        "covered_ranges": [list(r) for r in covered or result.ranges],
        "header_count": len(all_headers),
        "header_gaps": sorted(set(header_gaps)),
        "canonical_tip_hash": canonical_tip,
    }
    acknowledged = (start_block, result.next_block - 1) if result.next_block > start_block else None
    empty = total_events == 0
    finished = now()
    manifest = RunManifest(
        run_id=run_id,
        command="backfill",
        chain_id=chain_id,
        filter_hash=filt_hash,
        checkpoint_source=source_key,
        config_path=config_path,
        config_hash=config_hash,
        abi_hashes=tuple(abi_hashes),
        addresses=tuple(address_list),
        attempted_range=(start_block, target_block),
        acknowledged_range=acknowledged,
        batches=tuple(batch_ids),
        event_count=total_events,
        empty=empty,
        provider_endpoint=provider_endpoint,
        operator_started_at=started,
        operator_finished_at=finished,
        header_evidence=header_evidence,
        errors=tuple(header_errors),
    )
    _write_manifest(store.root, manifest)
    return manifest


def _write_manifest(root: Path, manifest: RunManifest) -> Path:
    runs_dir = Path(root) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{manifest.run_id}.json"
    tmp_path = runs_dir / f".{manifest.run_id}.{hashlib.sha256(canonical_json(manifest.to_dict())).hexdigest()[:8]}.tmp"
    tmp_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path
