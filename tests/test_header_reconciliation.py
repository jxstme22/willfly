"""M1-03 ancestry evidence, quiet-block and restart regression coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from willfly.adapters.robinhood_rpc import JsonRpcError, ReadOnlyRpcClient, RpcLog
from willfly.domain import RawEvent
from willfly.ingest.runner import capture_to_store
from willfly.storage import BlockHeader, RawBatchStore


V4 = "0x8366a39cc670b4001a1121b8f6a443a643e40951"


def _hash(label: int) -> str:
    return "0x" + f"{label:064x}"


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
