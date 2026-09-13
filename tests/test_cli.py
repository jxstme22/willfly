import json

from willfly.cli import main
from willfly.storage import RawBatchStore


def test_fixture_check_passes(capsys):
    assert main(["fixture-check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["origin"] == "synthetic"
    assert result["failed"] == 0


def test_doctor_reports_open_launch_gate(capsys):
    assert main(["doctor"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert result["checks"]["selected_launch_source_gate_open"] is True


def test_strict_doctor_fails_while_launch_gate_is_open(capsys):
    assert main(["doctor", "--strict"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"


def test_capture_and_backfill_dry_run_return_read_only_plans(capsys):
    assert main(["capture", "--from-block", "10", "--to-block", "12", "--dry-run"]) == 3
    capture = json.loads(capsys.readouterr().out)
    assert capture["run_id"].startswith("capture-")
    assert capture["operating_mode"] == "read_only"
    assert capture["status"] == "plan_only" and capture["executed"] is False
    assert main(["backfill", "--from-block", "10", "--to-block", "12", "--dry-run"]) == 3
    backfill = json.loads(capsys.readouterr().out)
    assert backfill["run_id"].startswith("backfill-")


def test_shadow_command_stops_at_unfrozen_config(capsys):
    assert main(["shadow"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "blocked"
    assert result["reason"] == "shadow_config_not_frozen"
    assert result["hypothetical_only"] is True
    assert result["broadcast"] is False


def test_audit_command_reports_degraded_non_independent_data(tmp_path, capsys):
    record = {
        "chain_id": 4663,
        "source": "cli-test",
        "source_schema_version": "test.v0.1",
        "block_number": 1,
        "block_hash": "0x" + "11" * 32,
        "parent_hash": None,
        "transaction_hash": "0x" + "22" * 32,
        "log_index": 0,
        "event_time": "2026-01-01T00:00:00Z",
        "received_time": "2026-01-01T00:00:01Z",
        "payload": {},
        "ingestion_run": "cli-test",
        "canonical_status": "canonical",
    }
    expected = tmp_path / "expected.json"
    observed = tmp_path / "observed.json"
    expected.write_text(json.dumps([record]))
    observed.write_text(json.dumps([]))
    assert main(["audit", "--expected", str(expected), "--observed", str(observed)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["report"]["state"] == "degraded"


def test_materialize_persists_a_read_only_observatory_projection(tmp_path, capsys):
    token = "0x" + "11" * 20
    payload = {
        "launches": [
            {
                "chain_id": 4663,
                "token": token,
                "launch_contract": None,
                "launch_contract_version": None,
                "creation_evidence": ["launch:1"],
                "creator": None,
                "created_at": None,
                "first_seen_at": "2026-09-13T00:00:00Z",
                "origin_confidence": "observed",
                "linked_pool_ids": [],
                "lifecycle_state": "graduated",
            }
        ],
        "pools": [],
        "raw_events": [],
        "trades": [],
        "lifecycle_revisions": [
            {"token": token, "lifecycle_state": "non_graduate", "observed_at": "2026-09-13T00:00:01Z", "raw_references": ["lifecycle:1"]}
        ],
    }
    input_path = tmp_path / "projection-input.json"
    store_path = tmp_path / "store"
    input_path.write_text(json.dumps(payload))
    assert main([
        "materialize", "--input", str(input_path), "--as-of-time", "2026-09-13T00:05:00Z",
        "--store-dir", str(store_path), "--source", "cli-projection",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "materialized"
    with RawBatchStore(store_path) as store:
        saved = store.load_snapshot(result["snapshot_id"])
    assert saved["discovery"]["launches"][0]["lifecycle_state"] == "non_graduate"
