from willfly.domain import RawEvent
from willfly.ingest.quality import assess_quality
from willfly.ingest.supervisor import RetryPolicy, run_with_retries


def _event(block: int, event_time: str, received_time: str, status: str = "canonical") -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.quality",
            "source_schema_version": "rpc-log.v0.1",
            "block_number": block,
            "block_hash": "0x" + f"{block:064x}"[-64:],
            "parent_hash": None,
            "transaction_hash": "0x" + f"{block:064x}"[-64:],
            "log_index": 0,
            "event_time": event_time,
            "received_time": received_time,
            "payload": {},
            "ingestion_run": "quality-test",
            "canonical_status": status,
        }
    )


def test_quality_reports_delay_lag_duplicates_and_unresolved_gaps():
    first = _event(10, "2026-09-13T00:00:00Z", "2026-09-13T00:00:02Z")
    second = _event(11, "2026-09-13T00:00:01Z", "2026-09-13T00:00:05Z", status="quarantined")
    report = assess_quality(
        [first, second, first],
        latest_head=15,
        expected_ranges=[(10, 15)],
        covered_ranges=[(10, 11)],
        retry_count=2,
        storage_bytes=123,
        source_state="healthy",
    )
    assert report.state == "degraded"
    assert report.event_count == 3
    assert report.unique_event_count == 2
    assert report.duplicate_count == 1
    assert report.quarantine_count == 1
    assert report.average_arrival_delay_seconds == 8 / 3
    assert report.p95_arrival_delay_seconds == 4.0
    assert report.block_lag == 4
    assert report.gap_ranges == ((12, 15),)


def test_quality_is_healthy_after_complete_coverage():
    event = _event(10, "2026-09-13T00:00:00Z", "2026-09-13T00:00:01Z")
    report = assess_quality(
        [event], expected_ranges=[(10, 10)], covered_ranges=[(10, 10)], source_state="healthy"
    )
    assert report.state == "healthy"
    assert report.gap_ranges == ()


def test_unknown_or_stale_source_cannot_report_healthy_even_with_full_event_coverage():
    event = _event(10, "2026-09-13T00:00:00Z", "2026-09-13T00:00:01Z")
    for source_state in ("unknown", "stale"):
        report = assess_quality(
            [event],
            expected_ranges=[(10, 10)],
            covered_ranges=[(10, 10)],
            source_state=source_state,
        )
        assert report.state == source_state
    unresolved = assess_quality(
        [event],
        expected_ranges=[(10, 10)],
        covered_ranges=[(10, 10)],
        source_state="healthy",
        missing_parent_hashes=("0x" + "11" * 32,),
    )
    assert unresolved.state == "degraded"


def test_supervisor_recovers_disconnect_and_redacts_failure():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("api_key=secret-value tx=0x" + "ab" * 32)
        return "reconnected"

    result = run_with_retries(operation, policy=RetryPolicy(max_attempts=3, backoff_seconds=0), sleeper=lambda _: None)
    assert result.state == "healthy"
    assert result.attempts == 3
    assert result.value == "reconnected"

    failed = run_with_retries(
        lambda: (_ for _ in ()).throw(OSError("authorization: Bearer secret-value")),
        policy=RetryPolicy(max_attempts=1, backoff_seconds=0),
    )
    assert failed.state == "degraded"
    assert "secret-value" not in failed.error
    assert "[REDACTED]" in failed.error
