import json

from willfly.cli import _load_signal_store, main
from willfly.evaluation.promotion import PredictionPoint
from willfly.shadow.config import freeze_shadow_config
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


def test_operator_check_is_offline_and_shadow_freeze_is_explicit(tmp_path, capsys):
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    shadow = tmp_path / "shadow.json"
    shadow.write_text(
        json.dumps(
            {
                "status": "pending",
                "model_id": "ordinary-baseline-v0.1",
                "feature_version": "observatory.features.v0.1",
                "source_config": str(source),
                "lp_enabled": False,
                "start_time": None,
                "config_hash": None,
            }
        ),
        encoding="utf-8",
    )
    assert main(["shadow-freeze", "--config", str(shadow), "--start-time", "2026-01-01T00:00:00Z"]) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert frozen["status"] == "frozen"
    assert frozen["signing"] is False and frozen["broadcast"] is False
    assert main(["operator-check", "--config", str(source), "--shadow-config", str(shadow)]) == 1
    degraded = json.loads(capsys.readouterr().out)
    assert degraded["status"] == "degraded"
    assert degraded["network_probe"] == "not_run"


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


def test_shadow_run_consumes_controlled_file_and_resumes(tmp_path, capsys):
    source_config = tmp_path / "source.json"
    source_config.write_text("{}", encoding="utf-8")
    config_path = tmp_path / "shadow.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "status": "pending",
                "model_id": "ordinary-baseline-v0.1",
                "feature_version": "observatory.features.v0.1",
                "source_config": str(source_config),
                "max_simultaneous_positions": 1,
                "lp_enabled": False,
                "decision_interval_seconds": 15,
                "start_time": None,
                "config_hash": None,
            }
        ),
        encoding="utf-8",
    )
    freeze_shadow_config(config_path, start_time="2026-01-01T00:00:00Z")
    input_path = tmp_path / "observations.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "willfly.shadow-input.v0.1",
                "observations": [
                    {
                        "observation": {
                            "observation_id": "cli-1",
                            "asset": "TOKEN",
                            "received_at": "2026-01-01T00:00:01Z",
                            "quality_state": "healthy",
                            "source_refs": ["controlled:1"],
                        },
                        "prediction": {
                            "model_id": "ordinary-baseline-v0.1",
                            "expected_return_bps": 150,
                            "uncertainty_bps": 20,
                            "as_of_time": "2026-01-01T00:00:01Z",
                        },
                        "decision_time": "2026-01-01T00:00:02Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_db = tmp_path / "shadow.sqlite"
    command = [
        "shadow-run",
        "--config",
        str(config_path),
        "--state-db",
        str(state_db),
        "--input",
        str(input_path),
        "--fixed-entry-atomic",
        "50",
        "--initial-cash-atomic",
        "100",
    ]
    assert main(command) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "completed"
    assert first["source"] == "controlled_file"
    assert first["processed_count"] == 1
    assert first["signing"] is False and first["broadcast"] is False
    assert main(command) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["processed_count"] == 0
    assert second["duplicate_count"] == 1


def test_watcher_cli_records_zero_trade_tick_and_restart_status(tmp_path, capsys):
    state_db = tmp_path / "watcher.sqlite3"
    feedback_dir = tmp_path / "feedback"
    first = [
        "watcher-tick",
        "--state-db",
        str(state_db),
        "--feedback-dir",
        str(feedback_dir),
        "--observed-at",
        "2026-01-01T00:00:00Z",
    ]
    assert main(first) == 0
    tick = json.loads(capsys.readouterr().out)
    assert tick["recorded"] is True
    assert tick["status"] == "waiting"
    assert tick["snapshot"]["personal_trade_count"] == 0
    assert tick["snapshot"]["waiting_reason"] == "no_mature_labels"
    assert tick["signing"] is False and tick["broadcast"] is False

    assert main(
        [
            "watcher-tick",
            "--state-db",
            str(state_db),
            "--feedback-dir",
            str(feedback_dir),
            "--observed-at",
            "2026-01-01T00:01:00Z",
        ]
    ) == 0
    later = json.loads(capsys.readouterr().out)
    assert later["status"] == "degraded"
    assert later["snapshot"]["outage_seconds_since_previous_tick"] == 60

    assert main(["watcher-status", "--state-db", str(state_db)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["started"] is True
    assert status["snapshot"]["status"] == "degraded"
    assert status["personal_trade_trigger_required"] is False


def test_signal_snapshot_loader_accepts_typed_empty_read_only_bundle(tmp_path):
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "willfly.signal-snapshot.v0.1",
                "as_of_time": "2026-01-01T00:00:00Z",
                "predictions": [],
                "proposals": [],
                "market_readiness": {"spot": "research_only", "lp": "research_only"},
                "training_state": {"status": "waiting", "reason": "no_mature_labels"},
            }
        ),
        encoding="utf-8",
    )
    loaded = _load_signal_store(path)
    assert loaded["predictions"] == ()
    assert loaded["proposals"] == ()
    assert loaded["training_state"]["status"] == "waiting"
    assert loaded["manual_actions"] == ()
    assert loaded["action_links"] == ()


def test_model_evaluate_records_comparison_without_promoting(tmp_path, capsys):
    points = []
    for model_version, predicted in (("candidate-v2", 1.0), ("active-v1", 3.0)):
        points.append(
            PredictionPoint(
                f"forward-{model_version}",
                model_version,
                "spot",
                "forward-1",
                "forward",
                "2026-01-01T00:00:00Z",
                predicted,
                1,
                ("market:1",),
            ).to_dict()
        )
        points.append(
            PredictionPoint(
                f"final-{model_version}",
                model_version,
                "spot",
                "final",
                "final_test",
                "2026-01-01T01:00:00Z",
                predicted,
                1,
                ("market:final",),
            ).to_dict()
        )
    points_path = tmp_path / "points.json"
    points_path.write_text(
        json.dumps({"schema_version": "willfly.prediction-points.v0.1", "points": points}), encoding="utf-8"
    )
    registry = tmp_path / "models.sqlite3"
    command = [
        "model-evaluate",
        "--points",
        str(points_path),
        "--candidate-version",
        "candidate-v2",
        "--active-version",
        "active-v1",
        "--evaluated-at",
        "2026-01-01T02:00:00Z",
        "--dataset-hash",
        "dataset-1",
        "--minimum-forward-windows",
        "1",
        "--minimum-points-per-window",
        "1",
        "--registry",
        str(registry),
        "--record",
    ]
    assert main(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "qualified"
    assert result["recorded"] is True
    assert len(result["report"]["active_forward_scores"]) == 1
    assert result["report"]["active_final_test_scores"][0]["mae_bps"] == 2.0

    assert main(["model-status", "--registry", str(registry), "--initial-active-version", "active-v1"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"]["active_version"] == "active-v1"
    assert status["state"]["consumed_final_test_count"] == 1


def test_feedback_cli_imports_empty_bundle_and_reports_waiting(tmp_path, capsys):
    bundle = tmp_path / "feedback.json"
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "willfly.feedback-bundle.v0.1",
                "predictions": [],
                "outcomes": [],
            }
        ),
        encoding="utf-8",
    )
    feedback_dir = tmp_path / "feedback-store"
    assert main(
        [
            "feedback-import",
            "--bundle",
            str(bundle),
            "--feedback-dir",
            str(feedback_dir),
            "--as-of-time",
            "2026-01-01T00:00:00Z",
        ]
    ) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["status"] == "waiting"
    assert imported["predictions"]["inserted"] == 0
    assert imported["dataset"]["eligible_count"] == 0
    assert imported["signing"] is False and imported["broadcast"] is False

    assert main(
        [
            "feedback-status",
            "--feedback-dir",
            str(feedback_dir),
            "--as-of-time",
            "2026-01-01T00:00:00Z",
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["prediction_count"] == 0
    assert status["queue_state_counts"] == {}


def test_wallet_cli_imports_empty_public_bundle_and_reports_missing_activity(tmp_path, capsys):
    bundle = tmp_path / "wallet.json"
    bundle.write_text(
        json.dumps({"schema_version": "willfly.wallet-activity-bundle.v0.1", "activities": []}),
        encoding="utf-8",
    )
    wallet_dir = tmp_path / "wallet-store"
    assert main(["wallet-import", "--bundle", str(bundle), "--wallet-dir", str(wallet_dir)]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["status"] == "recorded"
    assert imported["activity_count"] == 0
    assert imported["signing"] is False and imported["broadcast"] is False

    assert main(
        [
            "wallet-status",
            "--wallet-dir",
            str(wallet_dir),
            "--wallet",
            "0x" + "1" * 40,
            "--as-of-time",
            "2026-01-01T00:00:00Z",
            "--arrival-cutoff",
            "2026-01-01T00:00:00Z",
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "degraded"
    assert status["activity_count"] == 0
    assert "no_wallet_activity_at_cutoff" in status["observation"]["missingness"]
