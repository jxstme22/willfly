"""M1-02 durable capture/backfill integration tests with fixture transports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient, RpcLog
from willfly.ingest.backfill import BackfillCheckpointStore, BackfillError, backfill_range
from willfly.ingest.runner import backfill_to_store, capture_to_store, filter_identity
from willfly.storage.raw import RawBatchStore

V4 = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
TX = "0x4444444444444444444444444444444444444444444444444444444444444444"


def _log(block: int, index: int = 0, timestamp: int | None = 1700000000) -> RpcLog:
    return RpcLog(
        block_number=block,
        block_hash="0x" + f"{block:064x}"[-64:],
        transaction_hash="0x" + f"{block:062x}"[-62:] + f"{index:02x}",
        log_index=index,
        payload={"address": V4, "topics": ["0x" + "11" * 32], "data": "0x"},
        block_timestamp=timestamp,
    )


class FixtureCaptureClient:
    """Minimal read-only fixture client for capture tests."""

    def __init__(self, head: int, logs_by_block: dict[int, list[RpcLog]]) -> None:
        self._head = head
        self._logs = logs_by_block
        self.calls: list[str] = []

    def check_chain(self) -> int:
        self.calls.append("eth_chainId")
        return 4663

    def block_number(self) -> int:
        self.calls.append("eth_blockNumber")
        return self._head

    def block(self, block_number: int):
        self.calls.append("eth_getBlockByNumber")
        return {"hash": "0x" + f"{block_number:064x}"[-64:], "number": hex(block_number)}

    def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
        self.calls.append("eth_getLogs")
        if to_block - from_block > max_range:
            raise ValueError("range exceeds bound")
        out: list[RpcLog] = []
        for block in range(from_block, to_block + 1):
            out.extend(self._logs.get(block, []))
        return out

    def resolve_log_time(self, log: RpcLog, headers: dict) -> RpcLog:
        self.calls.append("eth_getBlockByNumber")
        if log.block_timestamp is not None:
            return log
        from dataclasses import replace

        return replace(log, block_timestamp=1700000000 + log.block_number)

    def request(self, method: str, params: list[Any] | None = None) -> Any:
        if method == "eth_sendRawTransaction":
            raise PermissionError(f"read-only client rejected method: {method}")
        raise AssertionError(method)


class FixtureBackfillClient:
    def __init__(self, logs: list[RpcLog]) -> None:
        self.logs_by_block = {log.block_number: log for log in logs}
        self.calls: list[tuple[int, int]] = []

    def check_chain(self):
        return 4663

    def logs(self, *, address, from_block: int, to_block: int, max_range: int = 2000):
        self.calls.append((from_block, to_block))
        return [
            self.logs_by_block[block] for block in range(from_block, to_block + 1) if block in self.logs_by_block
        ]

    def resolve_log_time(self, log, headers):
        return log

    def block(self, block_number: int):
        return {"hash": "0x" + f"{block_number:064x}"[-64:], "number": hex(block_number)}


def test_capture_writes_records_and_filter_bound_evidence(tmp_path: Path):
    logs = {10: [_log(10)], 11: [_log(11)]}
    client = FixtureCaptureClient(head=11, logs_by_block=logs)
    with RawBatchStore(tmp_path / "store") as store:
        manifest = capture_to_store(
            client,
            store,
            addresses=[V4],
            from_block=10,
            to_block=11,
            run_id="capture-test-1",
            config_path="configs/sources/robinhood-chain-v0.1.json",
            config_hash="cfghash",
            abi_hashes=["abihash"],
            event_families=["Swap"],
            provider_endpoint="https://fixture.invalid",
            clock=lambda: "2026-09-13T00:00:01+00:00",
        )
    assert manifest.event_count == 2
    assert manifest.acknowledged_range == (10, 11)
    assert len(manifest.batches) == 1
    assert manifest.filter_hash == filter_identity(
        chain_id=4663, addresses=[V4], abi_hashes=["abihash"], event_families=["Swap"]
    )
    assert manifest.checkpoint_source.startswith("capture:4663:")
    with RawBatchStore(tmp_path / "store") as reopened:
        assert len(reopened.read(manifest.batches[0])) == 2
        assert reopened.get_checkpoint(manifest.checkpoint_source) is not None
        run_file = tmp_path / "store" / "runs" / "capture-test-1.json"
        assert run_file.is_file()
    assert "eth_sendRawTransaction" not in client.calls


def test_capture_empty_range_acknowledges_with_header_evidence(tmp_path: Path):
    client = FixtureCaptureClient(head=20, logs_by_block={})
    with RawBatchStore(tmp_path / "store") as store:
        manifest = capture_to_store(
            client,
            store,
            addresses=[V4],
            from_block=15,
            to_block=16,
            run_id="capture-empty-1",
            clock=lambda: "2026-09-13T00:00:01+00:00",
        )
    assert manifest.empty is True
    assert manifest.event_count == 0
    assert manifest.batches == ()
    assert manifest.acknowledged_range == (15, 16)
    with RawBatchStore(tmp_path / "store") as reopened:
        assert reopened.get_empty_range_ack(manifest.checkpoint_source) is not None


def test_backfill_resumes_after_crash_without_loss(tmp_path: Path):
    logs = [_log(block) for block in range(1, 6)]
    calls = {"count": 0}

    class CrashyClient(FixtureBackfillClient):
        def logs(self, *, address, from_block, to_block, max_range=2000):
            # Crash on the second page request to simulate interruption before commit.
            if len(self.calls) == 1:
                self.calls.append((from_block, to_block))
                raise RuntimeError("simulated crash before publication")
            return super().logs(address=address, from_block=from_block, to_block=to_block, max_range=max_range)

    store_path = tmp_path / "store"
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            with pytest.raises(RuntimeError, match="simulated crash"):
                backfill_to_store(
                    CrashyClient(logs),
                    store,
                    addresses=[V4],
                    start_block=1,
                    target_block=5,
                    run_id="backfill-crash",
                    page_size=2,
                    checkpoint_store=checkpoints,
                    clock=lambda: "2026-09-13T00:00:00Z",
                )
    # Resume with a healthy client; no acknowledged loss.
    with RawBatchStore(store_path) as store:
        with BackfillCheckpointStore(checkpoint_path) as checkpoints:
            manifest = backfill_to_store(
                FixtureBackfillClient(logs),
                store,
                addresses=[V4],
                start_block=1,
                target_block=5,
                run_id="backfill-resume",
                page_size=2,
                checkpoint_store=checkpoints,
                clock=lambda: "2026-09-13T00:00:00Z",
            )
    assert manifest.acknowledged_range == (1, 5)
    # The resumed run streams only its remaining pages; the first page from the
    # crashed run is already durable. No acknowledged loss means the store holds all five.
    assert manifest.event_count == 3
    with RawBatchStore(store_path) as store:
        seen_blocks = sorted(event.block_number for batch in store.list_batches() for event in store.read(batch.batch_id))
        assert seen_blocks == [1, 2, 3, 4, 5]


def test_changed_filters_cannot_inherit_cursors(tmp_path: Path):
    logs = [_log(block) for block in range(1, 4)]
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    other_address = "0x" + "22" * 20
    with BackfillCheckpointStore(checkpoint_path) as checkpoints:
        first = backfill_range(
            FixtureBackfillClient(logs),
            address=V4,
            start_block=1,
            target_block=3,
            source="backfill:4663:filterA",
            run_id="run-a",
            page_size=2,
            checkpoint_store=checkpoints,
            clock=lambda: "2026-09-13T00:00:00Z",
            expected_filter_hash="filterA",
        )
        assert first.complete
        # Same source key but different filter hash must fail closed.
        with pytest.raises(BackfillError, match="filter"):
            backfill_range(
                FixtureBackfillClient(logs),
                address=other_address,
                start_block=1,
                target_block=3,
                source="backfill:4663:filterA",
                run_id="run-b",
                page_size=2,
                checkpoint_store=checkpoints,
                clock=lambda: "2026-09-13T00:00:00Z",
                expected_filter_hash="filterB",
            )
    # Runner-level: different addresses produce different checkpoint sources.
    with RawBatchStore(tmp_path / "store") as store:
        with BackfillCheckpointStore(tmp_path / "checkpoints2.sqlite3") as checkpoints:
            manifest_a = backfill_to_store(
                FixtureBackfillClient(logs),
                store,
                addresses=[V4],
                start_block=1,
                target_block=3,
                run_id="runner-a",
                checkpoint_store=checkpoints,
                clock=lambda: "2026-09-13T00:00:00Z",
            )
            manifest_b = backfill_to_store(
                FixtureBackfillClient(logs),
                store,
                addresses=[other_address],
                start_block=1,
                target_block=3,
                run_id="runner-b",
                checkpoint_store=checkpoints,
                clock=lambda: "2026-09-13T00:00:00Z",
            )
    assert manifest_a.checkpoint_source != manifest_b.checkpoint_source
    assert manifest_a.filter_hash != manifest_b.filter_hash


def test_backfill_streams_without_retaining_history(tmp_path: Path):
    logs = [_log(block) for block in range(1, 101)]
    with BackfillCheckpointStore(tmp_path / "checkpoints.sqlite3") as checkpoints:
        result = backfill_range(
            FixtureBackfillClient(logs),
            address=V4,
            start_block=1,
            target_block=100,
            source="stream-test",
            run_id="stream",
            page_size=10,
            checkpoint_store=checkpoints,
            clock=lambda: "2026-09-13T00:00:00Z",
            retain_events=False,
        )
    assert result.events == ()
    assert result.ranges[0] == (1, 10)
    assert result.ranges[-1] == (91, 100)
    assert result.complete
    # Runner streaming writes batches while returning only counts.
    with RawBatchStore(tmp_path / "store") as store:
        with BackfillCheckpointStore(tmp_path / "checkpoints2.sqlite3") as checkpoints:
            manifest = backfill_to_store(
                FixtureBackfillClient(logs),
                store,
                addresses=[V4],
                start_block=1,
                target_block=100,
                run_id="stream-runner",
                page_size=25,
                checkpoint_store=checkpoints,
                clock=lambda: "2026-09-13T00:00:00Z",
            )
    assert manifest.event_count == 100
    assert len(manifest.batches) == 4


def test_overlapping_backfill_with_different_range_fails_closed(tmp_path: Path):
    logs = [_log(block) for block in range(1, 6)]
    with BackfillCheckpointStore(tmp_path / "checkpoints.sqlite3") as checkpoints:
        backfill_range(
            FixtureBackfillClient(logs),
            address=V4,
            start_block=1,
            target_block=5,
            source="overlap",
            run_id="first",
            page_size=5,
            checkpoint_store=checkpoints,
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        with pytest.raises(BackfillError, match="range"):
            backfill_range(
                FixtureBackfillClient(logs),
                address=V4,
                start_block=2,
                target_block=6,
                source="overlap",
                run_id="second",
                page_size=5,
                checkpoint_store=checkpoints,
                clock=lambda: "2026-09-13T00:00:00Z",
            )


def test_read_only_client_rejects_signing():
    client = ReadOnlyRpcClient("https://fixture.invalid", transport=lambda m, p: {"result": "0x1"})
    with pytest.raises(PermissionError):
        client.request("eth_sendRawTransaction", ["0xdead"])
    with pytest.raises(PermissionError):
        client.request("eth_sendTransaction", [{}])
