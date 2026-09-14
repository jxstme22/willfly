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
from willfly.ingest.backfill import BackfillCheckpoint, BackfillCheckpointStore, BackfillError, backfill_range
from willfly.ingest.capture import capture_once
from willfly.ingest.canonicalize import assess_ancestry_anchor
from willfly.ingest.supervisor import redact_endpoint, redact_error
from willfly.storage.raw import AncestryAnchor, BlockHeader, RawBatchStore, anchor_evidence_record

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
        data["provider_endpoint"] = redact_endpoint(self.provider_endpoint)
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


def _reconcile_if_tipped(
    store: RawBatchStore,
    *,
    source: str,
    fresh_headers: Sequence[BlockHeader],
    tip_block: int,
    chain_id: int,
    config_identity: str,
) -> tuple[str | None, str]:
    tips = {header.block_hash.lower(): header for header in fresh_headers if header.number == tip_block}
    if len(tips) != 1:
        return None, "unavailable"
    tip = next(iter(tips.values()))
    result = store.rebuild_canonical_projection(
        source=source,
        tip_hash=tip.block_hash,
        chain_id=chain_id,
        config_identity=config_identity,
    )
    return tip.block_hash, result.anchor_state


def _stored_lineage_hash(store: RawBatchStore, source: str, block_number: int) -> str | None:
    """Find the last accepted hash for one covered block without choosing a fork."""

    canonical = store.get_canonical_checkpoint(source)
    if (
        canonical is not None
        and canonical["state"] == "canonical"
        and canonical["last_block_number"] == block_number
        and canonical["last_block_hash"]
    ):
        return canonical["last_block_hash"]
    empty_ack = store.get_empty_range_ack(source)
    if empty_ack is not None and empty_ack["last_block_number"] == block_number:
        return empty_ack["last_block_hash"]
    raw_checkpoint = store.get_checkpoint(source)
    if raw_checkpoint is not None and raw_checkpoint["last_block_number"] == block_number:
        return raw_checkpoint["last_block_hash"]
    for evidence in reversed(store.list_header_ranges(source)):
        if evidence["range_end"] == block_number and evidence["tip_hash"]:
            return evidence["tip_hash"]
    return None


def _checkpoint_domains(store: RawBatchStore, source: str) -> dict[str, Any]:
    """Expose raw, header and canonical checkpoint identities separately."""

    raw = store.get_checkpoint(source)
    empty = store.get_empty_range_ack(source)
    canonical = store.get_canonical_checkpoint(source)
    header_ranges = store.list_header_ranges(source)
    latest_header = header_ranges[-1] if header_ranges else None

    def checkpoint(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "last_block_number": row["last_block_number"],
            "last_block_hash": row["last_block_hash"],
            "updated_at": row["updated_at"],
        }

    return {
        "raw_acknowledgement": checkpoint(raw),
        "empty_range_acknowledgement": checkpoint(empty),
        "header_coverage": None
        if latest_header is None
        else {
            "range_start": latest_header["range_start"],
            "range_end": latest_header["range_end"],
            "tip_hash": latest_header["tip_hash"],
            "header_count": latest_header["header_count"],
            "missing_blocks": json.loads(latest_header["missing_blocks"]),
            "range_count": len(header_ranges),
        },
        "canonical_projection": None
        if canonical is None
        else {
            "state": canonical["state"],
            "tip_hash": canonical["tip_hash"],
            "last_block_number": canonical["last_block_number"],
            "last_block_hash": canonical["last_block_hash"],
            "anchor_state": canonical["anchor_state"],
            "missing_parent_hashes": json.loads(canonical["missing_parent_hashes"]),
            "updated_at": canonical["updated_at"],
        },
    }


def _raw_acknowledgement_replaces_prior(
    store: RawBatchStore, source: str, block_number: int, block_hash: str | None
) -> bool:
    """Allow the runner's explicit fork-replay path to replace raw cursor identity."""

    prior = store.get_checkpoint(source)
    if prior is None or prior["last_block_number"] is None:
        return False
    if block_number < prior["last_block_number"]:
        return True
    return (
        block_number == prior["last_block_number"]
        and block_hash is not None
        and prior["last_block_hash"] is not None
        and block_hash.lower() != prior["last_block_hash"].lower()
    )


def _lineage_probe(
    client: ReadOnlyRpcClient,
    store: RawBatchStore,
    *,
    source: str,
    checkpoint: BackfillCheckpoint,
    start_block: int,
    target_block: int,
) -> tuple[tuple[BlockHeader, ...], tuple[int, ...], tuple[str, ...], str | None]:
    """Read the current tip and cursor boundary before inheriting a cursor."""

    probe_blocks = {target_block}
    cursor = max(start_block, checkpoint.next_block)
    if cursor > start_block:
        probe_blocks.add(cursor - 1)
    headers: list[BlockHeader] = []
    missing: list[int] = []
    errors: list[str] = []
    for block_number in sorted(probe_blocks):
        observed, gaps, read_errors = _capture_headers(
            client, from_block=block_number, to_block=block_number
        )
        headers.extend(observed)
        missing.extend(gaps)
        errors.extend(read_errors)
    by_number = {header.number: header for header in headers}
    if missing or target_block not in by_number:
        errors.append("lineage probe unavailable; accepted coverage cannot be inherited")
        return tuple(headers), tuple(sorted(set(missing))), tuple(errors), None
    divergences: list[str] = []
    for block_number in sorted(probe_blocks):
        expected = _stored_lineage_hash(store, source, block_number)
        observed = by_number.get(block_number)
        if expected is not None and observed is not None and expected.lower() != observed.block_hash.lower():
            divergences.append(
                f"block {block_number} changed from {expected} to {observed.block_hash}"
            )
    return tuple(headers), tuple(sorted(set(missing))), tuple(errors), "; ".join(divergences) or None


def _validate_anchor_source(
    anchor: AncestryAnchor, source_key: str, *, chain_id: int, config_identity: str
) -> None:
    """Refuse to bind an anchor to another source, chain or config namespace."""

    if anchor.source != source_key:
        raise ValueError("anchor source does not match the capture namespace")
    if anchor.chain_id != chain_id:
        raise ValueError("anchor chain does not match the active source chain")
    if anchor.config_identity != config_identity:
        raise ValueError("anchor configuration identity does not match the active capture configuration")
    if anchor.qualification == "operator_declared_unverified":
        raise ValueError("unverified anchor declarations cannot be used for capture")


def _validate_anchor_candidate(
    anchor: AncestryAnchor,
    *,
    store: RawBatchStore,
    source_key: str,
    chain_id: int,
    config_identity: str,
    headers: Sequence[BlockHeader],
) -> None:
    """Require a qualified anchor before it can change durable trust state."""

    _validate_anchor_source(anchor, source_key, chain_id=chain_id, config_identity=config_identity)
    state, evidence = assess_ancestry_anchor(
        anchor,
        (*store.list_headers(), *headers),
        expected_chain_id=chain_id,
        expected_config_identity=config_identity,
    )
    if state != "qualified":
        detail = "; ".join(evidence) if evidence else "no qualifying evidence"
        raise ValueError(f"anchor rejected ({state}): {detail}")


def _qualify_genesis_anchor(
    store: RawBatchStore,
    *,
    source: str,
    chain_id: int,
    config_identity: str,
    headers: Sequence[BlockHeader],
    run_id: str,
    clock: Clock | None,
) -> AncestryAnchor | None:
    """Auto-qualify a genesis anchor only when block 0 is present in the window.

    A window that does not begin at genesis has no chain-verifiable root here, so
    this returns the existing anchor (if any) without inventing one from an
    arbitrary oldest header.
    """

    existing = store.get_ancestry_anchor(source)
    if existing is not None:
        return existing
    genesis = next((header for header in headers if header.number == 0), None)
    if genesis is None or genesis.parent_hash is not None or not genesis.parent_known:
        return None
    now = (clock or (lambda: datetime.now(timezone.utc).isoformat()))()
    anchor = AncestryAnchor(
        chain_id=chain_id,
        height=0,
        block_hash=genesis.block_hash,
        qualification="genesis",
        evidence=(
            anchor_evidence_record(
                "genesis_header",
                chain_id=chain_id,
                config_identity=config_identity,
                height=0,
                block_hash=genesis.block_hash,
                parent_hash=None,
                run_id=run_id,
            ),
        ),
        config_identity=config_identity,
        source=source,
        recorded_at=now,
    )
    state, _ = assess_ancestry_anchor(
        anchor,
        headers,
        expected_chain_id=chain_id,
        expected_config_identity=config_identity,
    )
    if state != "qualified":
        return None
    store.save_ancestry_anchor(anchor)
    return anchor


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
    anchor: AncestryAnchor | None = None,
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
    config_identity = config_hash or filt_hash
    preflight_headers: tuple[BlockHeader, ...] = ()
    if anchor is not None:
        _validate_anchor_source(anchor, source_key, chain_id=chain_id, config_identity=config_identity)
        # Validate the candidate against header evidence before capture can
        # publish a batch or persist an ancestry anchor. A bounded operator
        # anchor is allowed to come from an earlier store header or this range.
        preflight_headers, _, _ = _capture_headers(
            client, from_block=anchor.height, to_block=anchor.height
        )
        _validate_anchor_candidate(
            anchor,
            store=store,
            source_key=source_key,
            chain_id=chain_id,
            config_identity=config_identity,
            headers=preflight_headers,
        )
    result = capture_once(
        client, addresses=addresses, from_block=from_block, to_block=to_block, run_id=run_id, clock=clock
    )
    headers, header_gaps, header_errors = _capture_headers(client, from_block=from_block, to_block=result.to_block)
    store.persist_headers(headers)
    if anchor is not None:
        _validate_anchor_candidate(
            anchor,
            store=store,
            source_key=source_key,
            chain_id=chain_id,
            config_identity=config_identity,
            headers=(*preflight_headers, *headers),
        )
        store.save_ancestry_anchor(anchor)
    _qualify_genesis_anchor(
        store,
        source=source_key,
        chain_id=chain_id,
        config_identity=config_identity,
        headers=headers,
        run_id=run_id,
        clock=clock,
    )
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
            batch.batch_id,
            source=source_key,
            last_block_number=last,
            last_block_hash=last_hash,
            allow_reorg=_raw_acknowledgement_replaces_prior(store, source_key, last, last_hash),
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
    tip_hash, anchor_state = _reconcile_if_tipped(
        store,
        source=source_key,
        fresh_headers=headers,
        tip_block=result.to_block,
        chain_id=chain_id,
        config_identity=config_identity,
    )
    header_evidence["canonical_tip_hash"] = tip_hash
    header_evidence["ancestry_anchor_state"] = anchor_state
    canonical_checkpoint = store.get_canonical_checkpoint(source_key)
    header_evidence.update(
        {
            "delivery_state": "delivered",
            "header_coverage_state": "complete" if not header_gaps else "incomplete",
            "raw_acknowledgement_state": "acknowledged" if acknowledged is not None else "not_acknowledged",
            "canonical_projection_state": None
            if canonical_checkpoint is None
            else canonical_checkpoint["state"],
            "checkpoint_domains": _checkpoint_domains(store, source_key),
        }
    )
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
        provider_endpoint=redact_endpoint(provider_endpoint),
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
    anchor: AncestryAnchor | None = None,
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
    config_identity = config_hash or filt_hash
    preflight_headers: tuple[BlockHeader, ...] = ()
    if anchor is not None:
        _validate_anchor_source(anchor, source_key, chain_id=chain_id, config_identity=config_identity)
        existing_hashes = {header.block_hash.lower() for header in store.list_headers()}
        if anchor.block_hash.lower() not in existing_hashes:
            # Do the bounded header read before backfill publication so a bad
            # candidate cannot poison the namespace or strand its cursor.
            preflight_headers, _, _ = _capture_headers(
                client, from_block=anchor.height, to_block=anchor.height
            )
        _validate_anchor_candidate(
            anchor,
            store=store,
            source_key=source_key,
            chain_id=chain_id,
            config_identity=config_identity,
            headers=preflight_headers,
        )
        if preflight_headers:
            store.persist_headers(preflight_headers)
        store.save_ancestry_anchor(anchor)
    checkpoint = checkpoint_store.get(source_key) if checkpoint_store is not None else None
    lineage_headers: tuple[BlockHeader, ...] = ()
    lineage_gaps: tuple[int, ...] = ()
    lineage_errors: tuple[str, ...] = ()
    lineage_divergence: str | None = None
    lineage_repair = False
    lineage_unavailable = False
    if checkpoint is not None:
        lineage_headers, lineage_gaps, lineage_errors, lineage_divergence = _lineage_probe(
            client,
            store,
            source=source_key,
            checkpoint=checkpoint,
            start_block=start_block,
            target_block=target_block,
        )
        if lineage_headers:
            store.persist_headers(lineage_headers)
            for header in lineage_headers:
                store.record_header_range(
                    source=source_key,
                    range_start=header.number,
                    range_end=header.number,
                    run_id=f"{run_id}:lineage:{header.number}",
                    headers=[header],
                )
        if lineage_errors or target_block not in {header.number for header in lineage_headers}:
            lineage_unavailable = True
            current_tip = next(
                (header.block_hash for header in lineage_headers if header.number == target_block),
                None,
            )
            store.mark_canonical_needs_repair(
                source=source_key,
                tip_hash=current_tip,
                reason="current source lineage is unavailable; accepted coverage requires repair",
            )
        elif lineage_divergence is not None:
            lineage_repair = True
            current_tip = next(
                header.block_hash for header in lineage_headers if header.number == target_block
            )
            store.mark_canonical_needs_repair(
                source=source_key,
                tip_hash=current_tip,
                reason=f"source lineage changed; bounded replay required ({lineage_divergence})",
            )
            # Reset only the filter-bound cursor. Raw batches and fork headers
            # remain append-only, and a crash during replay can resume from the
            # last page acknowledged after this reset.
            if checkpoint_store is not None:
                checkpoint_store.save(
                    BackfillCheckpoint(
                        source_key,
                        start_block,
                        target_block,
                        start_block,
                        min(page_size, 2000),
                        now(),
                        filt_hash,
                    )
                )
    batch_ids: list[str] = []
    covered: list[tuple[int, int]] = []
    total_events = 0
    fresh_headers: list[BlockHeader] = []
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
        fresh_headers.extend(headers)
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
            batch.batch_id,
            source=source_key,
            last_block_number=last,
            last_block_hash=last_hash,
            allow_reorg=_raw_acknowledgement_replaces_prior(store, source_key, last, last_hash),
        )
        batch_ids.append(batch.batch_id)
        total_events += len(rebound)

    # Use filter-bound checkpoint source so changed filters cannot inherit cursors.
    # BackfillCheckpointStore gains an optional filter_hash binding; fall back to
    # source-key comparison for stores without the new column.
    result = None
    if not lineage_unavailable:
        try:
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
        except Exception:
            if lineage_repair:
                store.mark_canonical_needs_repair(
                    source=source_key,
                    tip_hash=next(
                        (header.block_hash for header in lineage_headers if header.number == target_block),
                        None,
                    ),
                    reason="bounded lineage replay failed; coverage remains incomplete",
                )
            raise
    if not lineage_unavailable and not any(header.number == target_block for header in fresh_headers):
        # A completed/no-op resume still revalidates the current tip. Never
        # select an older stored fork merely because no page was fetched.
        tip_headers = tuple(header for header in lineage_headers if header.number == target_block)
        if not tip_headers:
            tip_headers, tip_gaps, tip_errors = _capture_headers(
                client, from_block=target_block, to_block=target_block
            )
        else:
            tip_gaps, tip_errors = (), ()
        fresh_headers.extend(tip_headers)
        header_gaps.extend(tip_gaps)
        header_errors.extend(tip_errors)
        if tip_headers:
            store.persist_headers(tip_headers)
            store.record_header_range(
                source=source_key,
                range_start=target_block,
                range_end=target_block,
                run_id=f"{run_id}:tip",
                headers=tip_headers,
                missing_blocks=tip_gaps,
            )
    _qualify_genesis_anchor(
        store,
        source=source_key,
        chain_id=chain_id,
        config_identity=config_identity,
        headers=store.list_headers(),
        run_id=run_id,
        clock=clock,
    )
    header_gaps.extend(lineage_gaps)
    header_errors.extend(lineage_errors)
    if lineage_unavailable:
        fresh_headers.extend(lineage_headers)
        canonical_tip, anchor_state = None, "unavailable"
        coverage_state = "needs_repair"
    else:
        canonical_tip, anchor_state = _reconcile_if_tipped(
            store,
            source=source_key,
            fresh_headers=fresh_headers,
            tip_block=target_block,
            chain_id=chain_id,
            config_identity=config_identity,
        )
        coverage_state = "repaired" if lineage_repair else "complete"
    acknowledged = (
        (start_block, result.next_block - 1)
        if result is not None and result.next_block > start_block and not lineage_unavailable
        else None
    )
    header_evidence = {
        "chain_id": chain_id,
        "covered_ranges": [list(r) for r in covered or (result.ranges if result is not None else ())],
        "header_count": len(fresh_headers),
        "header_gaps": sorted(set(header_gaps)),
        "canonical_tip_hash": canonical_tip,
        "ancestry_anchor_state": anchor_state,
        "coverage_state": coverage_state,
        "delivery_state": "delivered" if result is not None else "not_delivered",
        "header_coverage_state": "complete" if not header_gaps else "incomplete",
        "raw_acknowledgement_state": "acknowledged" if acknowledged is not None else "not_acknowledged",
        "canonical_projection_state": store.get_canonical_checkpoint(source_key)["state"]
        if store.get_canonical_checkpoint(source_key) is not None
        else None,
        "checkpoint_domains": _checkpoint_domains(store, source_key),
    }
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
        provider_endpoint=redact_endpoint(provider_endpoint),
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
