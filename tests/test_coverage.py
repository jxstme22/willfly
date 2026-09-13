from willfly.evaluation.coverage import audit_coverage
from willfly.domain import RawEvent


def make_raw_event(*, block_number: int, log_index: int, canonical_status: str = "canonical") -> RawEvent:
    block_hash = f"0x{block_number:064x}"
    transaction_hash = f"0x{block_number + 1000:064x}"
    timestamp = "2026-01-01T00:00:00+00:00"
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "coverage-test",
            "source_schema_version": "test.v0.1",
            "block_number": block_number,
            "block_hash": block_hash,
            "parent_hash": None,
            "transaction_hash": transaction_hash,
            "log_index": log_index,
            "event_time": timestamp,
            "received_time": timestamp,
            "payload": {"topic": "0x"},
            "ingestion_run": "coverage-test",
            "canonical_status": canonical_status,
        }
    )


def test_coverage_reports_recall_duplicates_and_quarantine_without_false_green() -> None:
    first = make_raw_event(block_number=10, log_index=0)
    second = make_raw_event(block_number=11, log_index=0)
    quarantined = make_raw_event(block_number=12, log_index=0, canonical_status="quarantined")

    report = audit_coverage(
        [first, second],
        [first, first],
        provider_independent=False,
        quarantined=[quarantined],
    )

    assert report.expected_count == 2
    assert report.observed_count == 2
    assert report.matched_count == 1
    assert report.recall == 0.5
    assert report.missing_keys == (second.logical_key,)
    assert report.duplicate_keys == (first.logical_key,)
    assert report.quarantined_count == 1
    assert report.state == "degraded"
    assert "provider_independence_unverified" in report.notes


def test_independent_complete_coverage_passes() -> None:
    records = [make_raw_event(block_number=20, log_index=0), make_raw_event(block_number=21, log_index=0)]

    report = audit_coverage(records, records, provider_independent=True)

    assert report.state == "pass"
    assert report.recall == 1.0
    assert report.missing_keys == ()
    assert report.duplicate_keys == ()
