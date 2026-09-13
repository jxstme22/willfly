import pytest

from willfly.domain import RawEvent
from willfly.ingest.canonicalize import CanonicalizationError, canonicalize_events


def _event(number: int, block_hash: str, parent_hash: str | None, index: int, status: str = "provisional") -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.chain",
            "source_schema_version": "rpc-log.v0.1",
            "block_number": number,
            "block_hash": block_hash,
            "parent_hash": parent_hash,
            "transaction_hash": "0x" + f"{number:062x}"[-62:] + f"{index:02x}",
            "log_index": index,
            "event_time": "2026-09-13T00:00:00Z",
            "received_time": "2026-09-13T00:00:01Z",
            "payload": {"topics": [], "data": "0x"},
            "ingestion_run": "canonicalize-test",
            "canonical_status": status,
        }
    )


def test_multi_block_fork_promotes_tip_chain_and_retains_orphans():
    a1 = "0x" + "a1" * 32
    a2 = "0x" + "a2" * 32
    a3 = "0x" + "a3" * 32
    b2 = "0x" + "b2" * 32
    b3 = "0x" + "b3" * 32
    events = [
        _event(100, a1, None, 0),
        _event(101, a2, a1, 0),
        _event(102, a3, a2, 0),
        _event(101, b2, a1, 1),
        _event(102, b3, b2, 1),
    ]
    result = canonicalize_events(events, tip_hash=b3, confirmations=1)
    assert [event.block_hash for event in result.canonical_events] == [a1, b2, b3]
    assert [event.block_hash for event in result.orphaned_events] == [a2, a3]
    assert [event.canonical_status for event in result.orphaned_events] == ["orphaned", "orphaned"]
    assert [event.block_hash for event in result.confirmed_events] == [a1, b2]
    assert [event.block_hash for event in result.provisional_events] == [b3]
    assert result.missing_parent_hashes == ()


def test_missing_parent_and_quarantine_are_explicit():
    tip = "0x" + "cc" * 32
    missing = "0x" + "dd" * 32
    quarantined = _event(9, "0x" + "ee" * 32, None, 0, status="quarantined")
    result = canonicalize_events(
        [_event(10, tip, missing, 0), quarantined], tip_hash=tip
    )
    assert result.missing_parent_hashes == (missing,)
    assert len(result.canonical_events) == 1
    assert result.quarantined_events == (quarantined,)


def test_unknown_tip_and_parent_cycles_fail_closed():
    block = "0x" + "11" * 32
    with pytest.raises(CanonicalizationError, match="tip hash"):
        canonicalize_events([_event(1, block, None, 0)], tip_hash="0x" + "22" * 32)
    with pytest.raises(CanonicalizationError, match="cycle"):
        canonicalize_events([_event(1, block, block, 0)], tip_hash=block)
