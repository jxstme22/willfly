from pathlib import Path
import pytest

from willfly.adapters.robinhood_rpc import JsonRpcError, RpcLog
from willfly.ingest.backfill import BackfillCheckpointStore, BackfillError, backfill_range


def _log(block: int, index: int = 0) -> RpcLog:
    return RpcLog(
        block_number=block,
        block_hash="0x" + f"{block:064x}"[-64:],
        transaction_hash="0x" + f"{block:062x}"[-62:] + f"{index:02x}",
        log_index=index,
        payload={"address": "0x" + "11" * 20, "topics": [], "data": "0x"},
        block_timestamp=1_700_000_000 + block,
    )


class FakeBackfillClient:
    def check_chain(self):
        return 4663

    def __init__(self, logs: list[RpcLog], *, reject_ranges_over: int | None = None) -> None:
        self.logs_by_block = {log.block_number: log for log in logs}
        self.reject_ranges_over = reject_ranges_over
        self.calls: list[tuple[int, int]] = []

    def logs(self, *, address: str | list[str], from_block: int, to_block: int, max_range: int = 2000) -> list[RpcLog]:
        self.calls.append((from_block, to_block))
        if self.reject_ranges_over is not None and to_block - from_block + 1 > self.reject_ranges_over:
            raise JsonRpcError("temporary provider range limit")
        return [self.logs_by_block[block] for block in range(from_block, to_block + 1) if block in self.logs_by_block]


def test_backfill_adapts_page_size_and_emits_complete_ranges(tmp_path: Path):
    client = FakeBackfillClient([_log(block) for block in range(1, 6)], reject_ranges_over=2)
    with BackfillCheckpointStore(tmp_path / "metadata.sqlite3") as checkpoints:
        result = backfill_range(
            client,
            address="0x" + "11" * 20,
            start_block=1,
            target_block=5,
            page_size=4,
            checkpoint_store=checkpoints,
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        assert result.complete
        assert result.ranges == ((1, 2), (3, 4), (5, 5))
        assert result.page_sizes == (2, 2, 2)
        assert [event.block_number for event in result.events] == [1, 2, 3, 4, 5]
        assert checkpoints.get("robinhood_rpc_backfill").next_block == 6


def test_backfill_restart_resumes_after_last_checkpoint(tmp_path: Path):
    logs = [_log(block) for block in range(1, 6)]
    first_client = FakeBackfillClient(logs)
    callback_calls = 0

    def stop_on_second_page(page_events, from_block, to_block):
        nonlocal callback_calls
        callback_calls += 1
        if callback_calls == 2:
            raise RuntimeError("simulated interruption before checkpoint")

    with BackfillCheckpointStore(tmp_path / "metadata.sqlite3") as checkpoints:
        with pytest.raises(RuntimeError):
            backfill_range(
                first_client,
                address="0x" + "11" * 20,
                start_block=1,
                target_block=5,
                page_size=2,
                checkpoint_store=checkpoints,
                on_page=stop_on_second_page,
                clock=lambda: "2026-09-13T00:00:00Z",
            )
        checkpoint = checkpoints.get("robinhood_rpc_backfill")
        assert checkpoint is not None
        assert checkpoint.next_block == 3

        resumed = backfill_range(
            FakeBackfillClient(logs),
            address="0x" + "11" * 20,
            start_block=1,
            target_block=5,
            page_size=2,
            checkpoint_store=checkpoints,
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        uninterrupted = backfill_range(
            FakeBackfillClient(logs),
            address="0x" + "11" * 20,
            start_block=3,
            target_block=5,
            page_size=2,
            clock=lambda: "2026-09-13T00:00:00Z",
        )
        assert [event.logical_key for event in resumed.events] == [event.logical_key for event in uninterrupted.events]


def test_backfill_extends_a_completed_checkpoint_without_replaying_prior_pages(tmp_path: Path):
    logs = [_log(block) for block in range(1, 8)]
    with BackfillCheckpointStore(tmp_path / "metadata.sqlite3") as checkpoints:
        first = backfill_range(
            FakeBackfillClient(logs),
            address="0x" + "11" * 20,
            start_block=1,
            target_block=5,
            page_size=2,
            checkpoint_store=checkpoints,
        )
        assert first.complete
        second_client = FakeBackfillClient(logs)
        extended = backfill_range(
            second_client,
            address="0x" + "11" * 20,
            start_block=1,
            target_block=7,
            page_size=2,
            checkpoint_store=checkpoints,
        )
        assert extended.complete
        assert extended.ranges == ((6, 7),)
        assert second_client.calls == [(6, 7)]
        assert checkpoints.get("robinhood_rpc_backfill").target_block == 7


def test_backfill_surfaces_out_of_range_provider_rows(tmp_path: Path):
    class BadClient(FakeBackfillClient):
        def logs(self, *, address: str | list[str], from_block: int, to_block: int, max_range: int = 2000):
            return [_log(to_block + 1)]

    with pytest.raises(BackfillError, match="outside"):
        backfill_range(
            BadClient([]),
            address="0x" + "11" * 20,
            start_block=1,
            target_block=1,
            clock=lambda: "2026-09-13T00:00:00Z",
        )
