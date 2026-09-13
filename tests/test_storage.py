from pathlib import Path

import pytest

from willfly.domain import RawEvent
from willfly.storage import BatchCorruptionError, RawBatchStore


def _event(block_number: int = 100) -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.rpc",
            "source_schema_version": "fixture.v0.1",
            "block_number": block_number,
            "block_hash": "0x2222222222222222222222222222222222222222222222222222222222222222",
            "parent_hash": "0x3333333333333333333333333333333333333333333333333333333333333333",
            "transaction_hash": "0x4444444444444444444444444444444444444444444444444444444444444444",
            "log_index": 0,
            "event_time": "2026-09-13T00:00:00Z",
            "received_time": "2026-09-13T00:00:01Z",
            "payload": {"event": "Swap", "amount_atomic": "90071992547409930000000000000000000001"},
            "ingestion_run": "storage-test",
            "canonical_status": "canonical",
        }
    )


def test_publish_read_and_acknowledge_are_idempotent(tmp_path: Path):
    with RawBatchStore(tmp_path) as store:
        batch = store.publish([_event()], source="fixture-rpc", partition_date="2026-09-13")
        assert batch.path.name.endswith(".jsonl.gz")
        assert store.read(batch.batch_id)[0].payload["amount_atomic"] == "90071992547409930000000000000000000001"
        assert store.get_checkpoint("fixture-rpc") is None
        store.acknowledge(batch.batch_id, source="fixture-rpc", last_block_number=100, last_block_hash=_event().block_hash)
        store.acknowledge(batch.batch_id, source="fixture-rpc", last_block_number=100, last_block_hash=_event().block_hash)
        assert store.list_batches()[0].acknowledged is True
        assert store.get_checkpoint("fixture-rpc")["last_block_number"] == 100


def test_unacknowledged_batch_survives_restart(tmp_path: Path):
    with RawBatchStore(tmp_path) as store:
        batch = store.publish([_event()], source="fixture-rpc", partition_date="2026-09-13")
        assert store.read(batch.batch_id)
    with RawBatchStore(tmp_path) as restarted:
        assert restarted.list_batches()[0].acknowledged is False
        assert restarted.read(batch.batch_id)[0].block_number == 100
        assert restarted.get_checkpoint("fixture-rpc") is None


def test_truncated_batch_is_detected_and_last_checkpoint_remains(tmp_path: Path):
    with RawBatchStore(tmp_path) as store:
        first = store.publish([_event()], source="fixture-rpc", partition_date="2026-09-13")
        store.acknowledge(first.batch_id, source="fixture-rpc", last_block_number=100, last_block_hash=_event().block_hash)
        second = store.publish([_event(101)], source="fixture-rpc", partition_date="2026-09-13")
        second.path.write_bytes(second.path.read_bytes()[:-8])
        with pytest.raises(BatchCorruptionError):
            store.read(second.batch_id)
        assert store.verify() == [second.batch_id]
        assert store.get_checkpoint("fixture-rpc")["last_block_number"] == 100


def test_publish_rejects_empty_and_unsafe_partition_names(tmp_path: Path):
    with RawBatchStore(tmp_path) as store:
        with pytest.raises(ValueError):
            store.publish([], source="fixture-rpc", partition_date="2026-09-13")
        with pytest.raises(ValueError):
            store.publish([_event()], source="../outside", partition_date="2026-09-13")
