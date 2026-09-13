"""M1-03 ancestry evidence, quiet-block and restart regression coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from willfly.adapters.robinhood_rpc import JsonRpcError, ReadOnlyRpcClient, RpcLog
from willfly.domain import RawEvent
from willfly.ingest.canonicalize import canonicalize_events
from willfly.ingest.runner import capture_to_store, checkpoint_source, filter_identity
from willfly.storage import AncestryAnchor, BlockHeader, RawBatchStore


V4 = "0x8366a39cc670b4001a1121b8f6a443a643e40951"


def _hash(label: int) -> str:
    return "0x" + f"{label:064x}"


def _source_key(base: str = "capture") -> str:
    return checkpoint_source(base, 4663, _filter_hash())


def _filter_hash() -> str:
    return filter_identity(chain_id=4663, addresses=[V4], abi_hashes=(), event_families=())


def _anchor(
    height: int,
    block_hash: str,
    *,
    source: str | None = None,
    chain_id: int = 4663,
    config_identity: str | None = None,
    qualification: str = "independent_header_cross_check",
) -> AncestryAnchor:
    return AncestryAnchor(
        chain_id=chain_id,
        height=height,
        block_hash=block_hash,
        qualification=qualification,
        evidence=("fixture: cross-checked header",),
        config_identity=config_identity or _filter_hash(),
        source=source or _source_key(),
        recorded_at="2026-09-13T00:00:00Z",
    )


def _event(block: int, block_hash: str, parent_hash: str | None, index: int = 0) -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.headers",
            "source_schema_version": "rpc-log.v0.1",
            "block_number": block,
            "block_hash": block_hash,
            "parent_hash": parent_hash,
            "transaction_hash": _hash(10_000 + block + index),
            "log_index": index,
            "event_time": "2026-09-13T00:00:00Z",
            "received_time": "2026-09-13T00:00:01Z",
            "payload": {"topics": [], "data": "0x"},
            "ingestion_run": "header-test",
            "canonical_status": "provisional",
        }
    )


def test_restart_reconciles_multi_block_fork_through_quiet_headers(tmp_path: Path):
    root, a2, quiet_a3, a4, b2, quiet_b3, b4 = (_hash(number) for number in range(1, 8))
    source = "capture:4663:headerfixture"
    store_path = tmp_path / "store"
    with RawBatchStore(store_path) as store:
        first = store.publish(
            [_event(1, root, None), _event(4, a4, quiet_a3)],
            source=source,
            partition_date="2026-09-13",
        )
        store.acknowledge(first.batch_id, source=source, last_block_number=4, last_block_hash=a4)
        store.persist_headers(
            [
                BlockHeader(1, root, None),
                BlockHeader(2, a2, root),
                BlockHeader(3, quiet_a3, a2),
                BlockHeader(4, a4, quiet_a3),
            ]
        )
        store.save_ancestry_anchor(_anchor(1, root, source=source))
        initial = store.rebuild_canonical_projection(source=source, tip_hash=a4)
        assert initial.is_resolved
        assert store.get_canonical_checkpoint(source)["last_block_hash"] == a4

    # The process restarts and observes a replacement branch. Blocks 2 and 3
    # have no selected logs, so only stored headers can establish the fork.
    with RawBatchStore(store_path) as store:
        replacement = store.publish(
            [_event(4, b4, quiet_b3, index=1)], source=source, partition_date="2026-09-13"
        )
        store.acknowledge(replacement.batch_id, source=source, last_block_number=4, last_block_hash=b4)
        store.persist_headers(
            [
                BlockHeader(2, b2, root),
                BlockHeader(3, quiet_b3, b2),
                BlockHeader(4, b4, quiet_b3),
            ]
        )
        result = store.rebuild_canonical_projection(source=source, tip_hash=b4)
        checkpoint = store.get_canonical_checkpoint(source)
        states = {row["block_hash"]: row["canonical_status"] for row in store.list_canonical_projection(source)}
        assert result.is_resolved
        assert [header.block_hash for header in store.list_headers() if header.number == 3] == [quiet_a3, quiet_b3]
        assert checkpoint["state"] == "canonical"
        assert checkpoint["last_block_hash"] == b4
        assert states[a4] == "orphaned"
        assert states[b4] == "canonical"


def test_missing_parent_leaves_all_nonquarantined_evidence_unresolved(tmp_path: Path):
    source = "capture:4663:missingparent"
    tip = _hash(20)
    missing = _hash(19)
    with RawBatchStore(tmp_path / "store") as store:
        batch = store.publish([_event(20, tip, missing)], source=source, partition_date="2026-09-13")
        store.acknowledge(batch.batch_id, source=source, last_block_number=20, last_block_hash=tip)
        store.persist_headers([BlockHeader(20, tip, missing)])
        result = store.rebuild_canonical_projection(source=source, tip_hash=tip)
        checkpoint = store.get_canonical_checkpoint(source)
        projected = store.list_canonical_projection(source)
    assert result.is_resolved is False
    assert result.missing_parent_hashes == (missing,)
    assert checkpoint["state"] == "unresolved"
    assert checkpoint["last_block_hash"] is None
    assert [row["canonical_status"] for row in projected] == ["unresolved"]


class _ForkCaptureClient:
    def __init__(self, headers: dict[int, BlockHeader], logs: dict[int, list[RpcLog]]) -> None:
        self.headers = headers
        self.logs_by_block = logs

    def check_chain(self) -> int:
        return 4663

    def block_number(self) -> int:
        return max(self.headers)

    def block(self, block_number: int):
        header = self.headers[block_number]
        return {
            "number": hex(header.number),
            "hash": header.block_hash,
            "parentHash": header.parent_hash,
            "timestamp": hex(header.timestamp or 0),
        }

    def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
        return [log for number in range(from_block, to_block + 1) for log in self.logs_by_block.get(number, [])]

    def resolve_log_time(self, log: RpcLog, headers: dict) -> RpcLog:
        return log


def _log(block: int, block_hash: str) -> RpcLog:
    return RpcLog(
        block_number=block,
        block_hash=block_hash,
        transaction_hash=_hash(20_000 + block),
        log_index=0,
        payload={"address": V4, "topics": [], "data": "0x"},
        block_timestamp=1_700_000_000 + block,
    )


def test_capture_persists_no_log_tip_headers_and_repairs_checkpoint_after_restart(tmp_path: Path):
    root, a2, a3, b2, b3 = (_hash(number) for number in range(100, 105))
    old_headers = {
        1: BlockHeader(1, root, None, 1_700_000_001),
        2: BlockHeader(2, a2, root, 1_700_000_002),
        3: BlockHeader(3, a3, a2, 1_700_000_003),
    }
    new_headers = {
        1: BlockHeader(1, root, None, 1_700_000_001),
        2: BlockHeader(2, b2, root, 1_700_000_002),
        3: BlockHeader(3, b3, b2, 1_700_000_003),
    }
    store_path = tmp_path / "store"
    with RawBatchStore(store_path) as store:
        first = capture_to_store(
            _ForkCaptureClient(old_headers, {3: [_log(3, a3)]}),
            store,
            addresses=[V4],
            from_block=1,
            to_block=3,
            run_id="old-branch",
            anchor=_anchor(1, root),
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        assert first.header_evidence["header_count"] == 3
        assert first.header_evidence["header_gaps"] == []

    with RawBatchStore(store_path) as store:
        second = capture_to_store(
            _ForkCaptureClient(new_headers, {3: [_log(3, b3)]}),
            store,
            addresses=[V4],
            from_block=1,
            to_block=3,
            run_id="new-branch",
            anchor=_anchor(1, root),
            clock=lambda: "2026-09-13T00:00:01Z",
        )
        checkpoint = store.get_canonical_checkpoint(second.checkpoint_source)
        states = {row["block_hash"]: row["canonical_status"] for row in store.list_canonical_projection(second.checkpoint_source)}
    assert second.header_evidence["canonical_tip_hash"] == b3
    assert checkpoint["last_block_hash"] == b3
    assert states[a3] == "orphaned"
    assert states[b3] == "canonical"


def test_empty_capture_persists_a_header_only_tip_and_canonical_checkpoint(tmp_path: Path):
    root, quiet_tip = _hash(300), _hash(301)
    headers = {
        1: BlockHeader(1, root, None, 1_700_000_001),
        2: BlockHeader(2, quiet_tip, root, 1_700_000_002),
    }
    with RawBatchStore(tmp_path / "store") as store:
        manifest = capture_to_store(
            _ForkCaptureClient(headers, {}),
            store,
            addresses=[V4],
            from_block=1,
            to_block=2,
            run_id="quiet-tip",
            anchor=_anchor(1, root),
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        checkpoint = store.get_canonical_checkpoint(manifest.checkpoint_source)
        header_range = store.list_header_ranges(manifest.checkpoint_source)
    assert manifest.empty is True
    assert manifest.header_evidence["canonical_tip_hash"] == quiet_tip
    assert checkpoint["state"] == "canonical"
    assert checkpoint["last_block_hash"] == quiet_tip
    assert header_range[-1]["header_count"] == 2


def test_header_outage_is_retained_as_a_gap_and_leaves_projection_unresolved(tmp_path: Path):
    root, missing, tip = _hash(400), _hash(401), _hash(402)
    headers = {
        1: BlockHeader(1, root, None, 1_700_000_001),
        2: BlockHeader(2, missing, root, 1_700_000_002),
        3: BlockHeader(3, tip, missing, 1_700_000_003),
    }

    class OutageClient(_ForkCaptureClient):
        def block(self, block_number: int):
            if block_number == 2:
                raise TimeoutError("fixture provider outage")
            return super().block(block_number)

    with RawBatchStore(tmp_path / "store") as store:
        manifest = capture_to_store(
            OutageClient(headers, {}),
            store,
            addresses=[V4],
            from_block=1,
            to_block=3,
            run_id="header-outage",
            anchor=_anchor(1, root),
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        checkpoint = store.get_canonical_checkpoint(manifest.checkpoint_source)
        header_range = store.list_header_ranges(manifest.checkpoint_source)
    assert manifest.header_evidence["header_gaps"] == [2]
    assert "header[2] unavailable" in manifest.errors[0]
    assert checkpoint["state"] == "unresolved"
    assert header_range[-1]["missing_blocks"] == "[2]"


def test_zero_header_timestamp_and_header_hash_mismatch_fail_closed():
    block_hash = _hash(500)
    log = RpcLog(5, block_hash, _hash(501), 0, {}, None)

    zero_time = ReadOnlyRpcClient(
        "https://fixture.invalid",
        transport=lambda *_: {"result": {"hash": block_hash, "timestamp": "0x0"}},
    )
    with pytest.raises(JsonRpcError, match="timestamp unavailable"):
        zero_time.resolve_log_time(log, {})

    mismatched = ReadOnlyRpcClient(
        "https://fixture.invalid",
        transport=lambda *_: {"result": {"hash": _hash(502), "timestamp": "0x1"}},
    )
    with pytest.raises(JsonRpcError, match="fork-mismatched"):
        mismatched.resolve_log_time(log, {})


def test_bounded_window_without_anchor_stays_unresolved_not_orphaned(tmp_path: Path):
    """An arbitrary oldest stored header must not become a trusted root."""

    a2, a3 = _hash(600), _hash(601)
    events = [_event(2, a2, _hash(599)), _event(3, a3, a2, index=1)]
    result = canonicalize_events(events, tip_hash=a3, headers=[BlockHeader(2, a2, _hash(599)), BlockHeader(3, a3, a2)])
    assert result.anchor_state == "unavailable"
    assert result.is_resolved is False
    assert [event.canonical_status for event in result.unresolved_events] == ["provisional", "provisional"]
    assert result.orphaned_events == ()


def test_qualified_anchor_resolves_bounded_window(tmp_path: Path):
    from willfly.ingest.canonicalize import canonicalize_events

    root, a1, a2 = _hash(610), _hash(611), _hash(612)
    events = [_event(610, root, _hash(609)), _event(611, a1, root), _event(612, a2, a1, index=1)]
    result = canonicalize_events(
        events,
        tip_hash=a2,
        headers=[BlockHeader(610, root, _hash(609)), BlockHeader(611, a1, root), BlockHeader(612, a2, a1)],
        anchor=_anchor(611, a1),
    )
    assert result.anchor_state == "qualified"
    assert result.is_resolved is True
    # The anchor is the trusted root; block 610 lies below it and is not promoted.
    assert [event.block_hash for event in result.canonical_events] == [a1, a2]
    assert [event.block_hash for event in result.orphaned_events] == [root]


def test_anchor_chain_and_config_mismatch_invalidate():
    from willfly.ingest.canonicalize import canonicalize_events

    a1 = _hash(620)
    events = [_event(1, a1, _hash(619))]
    headers = [BlockHeader(1, a1, _hash(619))]
    wrong_chain = _anchor(1, a1, chain_id=1)
    chain_result = canonicalize_events(events, tip_hash=a1, headers=headers, anchor=wrong_chain, expected_chain_id=4663)
    assert chain_result.anchor_state == "config_mismatch"
    assert chain_result.is_resolved is False

    wrong_config = _anchor(1, a1, config_identity="other-config")
    config_result = canonicalize_events(
        events, tip_hash=a1, headers=headers, anchor=wrong_config, expected_config_identity=_filter_hash()
    )
    assert config_result.anchor_state == "config_mismatch"
    assert config_result.is_resolved is False


def test_anchor_height_mismatch_and_missing_anchor_header_fail_closed():
    from willfly.ingest.canonicalize import canonicalize_events

    a1, a2 = _hash(630), _hash(631)
    events = [_event(1, a1, None), _event(2, a2, a1, index=1)]
    headers = [BlockHeader(1, a1, None), BlockHeader(2, a2, a1)]

    height_mismatch = canonicalize_events(events, tip_hash=a2, headers=headers, anchor=_anchor(7, a1))
    assert height_mismatch.anchor_state == "mismatch"
    assert height_mismatch.is_resolved is False

    absent = canonicalize_events(events, tip_hash=a2, headers=headers, anchor=_anchor(1, _hash(999)))
    assert absent.anchor_state == "unavailable"
    assert absent.is_resolved is False


def test_nonconsecutive_parent_heights_degrade_explicitly():
    from willfly.ingest.canonicalize import canonicalize_events

    a1, jump = _hash(640), _hash(641)
    # Continuity is broken: an event claims height 5, but its parent header is height 3.
    events = [_event(5, jump, a1), _event(3, a1, _hash(639))]
    headers = [BlockHeader(3, a1, _hash(639)), BlockHeader(5, jump, a1)]
    result = canonicalize_events(events, tip_hash=jump, headers=headers, anchor=_anchor(3, a1))
    assert result.anchor_state == "nonconsecutive"
    assert result.is_resolved is False
    assert result.missing_parent_hashes == (a1,)
    assert [event.canonical_status for event in result.unresolved_events] == ["provisional", "provisional"]


def test_fork_crossing_below_the_anchor_boundary_invalidates():
    anchor_hash, fork10, fork11, tip = _hash(650), _hash(655), _hash(656), _hash(651)
    # The anchor qualifies block 650 at height 10, but the observed tip descends
    # through a different height-10 block (fork10). The walk reaches below the
    # trusted height without matching the anchor, so the boundary cannot gate it.
    events = [_event(12, tip, fork11), _event(11, fork11, fork10), _event(10, fork10, _hash(649))]
    headers = [
        BlockHeader(10, anchor_hash, _hash(649)),
        BlockHeader(10, fork10, _hash(649)),
        BlockHeader(11, fork11, fork10),
        BlockHeader(12, tip, fork11),
    ]
    result = canonicalize_events(events, tip_hash=tip, headers=headers, anchor=_anchor(10, anchor_hash))
    assert result.anchor_state == "boundary_crossed"
    assert result.is_resolved is False
    assert result.anchor_evidence


def test_store_refuses_conflicting_anchor_replacement(tmp_path: Path):
    root, other = _hash(660), _hash(661)
    with RawBatchStore(tmp_path / "store") as store:
        first = store.save_ancestry_anchor(_anchor(1, root))
        assert store.save_ancestry_anchor(_anchor(1, root)).to_dict() == first.to_dict()
        with pytest.raises(ValueError, match="conflicting ancestry anchor"):
            store.save_ancestry_anchor(_anchor(1, other))
        loaded = store.get_ancestry_anchor(first.source)
    assert loaded is not None and loaded.block_hash == root


def test_capture_auto_qualifies_genesis_anchor_and_resolves(tmp_path: Path):
    genesis = _hash(700)
    headers = {0: BlockHeader(0, genesis, None, 1_700_000_000), 1: BlockHeader(1, _hash(701), genesis, 1_700_000_001)}
    with RawBatchStore(tmp_path / "store") as store:
        manifest = capture_to_store(
            _ForkCaptureClient(headers, {}),
            store,
            addresses=[V4],
            from_block=0,
            to_block=1,
            run_id="genesis-window",
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        anchored = store.get_ancestry_anchor(manifest.checkpoint_source)
        checkpoint = store.get_canonical_checkpoint(manifest.checkpoint_source)
    assert anchored is not None
    assert anchored.qualification == "genesis"
    assert checkpoint["state"] == "canonical"

