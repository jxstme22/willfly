import json

from willfly.evaluation.shadow import audit_shadow_window, reconcile_shadow
from willfly.policies.prediction import Prediction
from willfly.replay.execution import PoolQuote
from willfly.shadow.config import freeze_shadow_config
from willfly.shadow.health import assess_shadow_health
from willfly.shadow.runner import ShadowCheckpointStore, ShadowInput, ShadowObservation, ShadowRunner


def test_shadow_config_freeze_records_hash_before_observation(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"status": "pending", "config_hash": None, "start_time": None}), encoding="utf-8")
    frozen = freeze_shadow_config(config_path, start_time="2026-01-01T00:00:00Z")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["config_hash"] == frozen.config_hash
    assert payload["start_time"] == frozen.start_time


def test_shadow_runner_is_hypothetical_idempotent_and_shared_cash(tmp_path):
    store = ShadowCheckpointStore(str(tmp_path / "shadow.sqlite"))
    runner = ShadowRunner(store, fixed_entry_atomic=50, max_positions=1, initial_cash_atomic=100)
    observation = ShadowObservation("obs-1", "TOKEN", "2026-01-01T00:00:00Z", "healthy", source_refs=("raw:1",))
    prediction = Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:00Z")
    first = runner.step(observation, prediction, decision_time="2026-01-01T00:00:05Z")
    second = runner.step(observation, prediction, decision_time="2026-01-01T00:00:05Z")
    assert first.decision.action == "enter"
    assert first.decision.hypothetical is True
    assert first.decision.execution_state == "not_submitted"
    assert second.duplicate is True
    assert len(store.decisions()) == 1
    blocked = runner.step(
        ShadowObservation("obs-2", "OTHER", "2026-01-01T00:00:06Z", "healthy"),
        prediction,
        decision_time="2026-01-01T00:00:07Z",
    )
    assert blocked.decision.action == "watch"
    assert "max_concurrent_positions" in blocked.decision.reason
    try:
        runner.step(
            ShadowObservation("future", "FUTURE", "2026-01-01T00:00:00Z", "healthy"),
            Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:01Z"),
            decision_time="2026-01-01T00:00:02Z",
        )
    except ValueError as exc:
        assert "as_of_time" in str(exc)
    else:
        raise AssertionError("future prediction was accepted")
    exited = runner.step(
        ShadowObservation("obs-3", "TOKEN", "2026-01-01T00:00:08Z", "healthy"),
        Prediction("ordinary-v1", -200, 10, "2026-01-01T00:00:08Z"),
        decision_time="2026-01-01T00:00:09Z",
    )
    assert exited.decision.action == "hold"
    assert exited.decision.reason == "exit_requires_modeled_execution_and_reconciliation"
    reopened = runner.step(
        ShadowObservation("obs-4", "OTHER", "2026-01-01T00:00:10Z", "healthy"),
        prediction,
        decision_time="2026-01-01T00:00:11Z",
    )
    assert reopened.decision.action == "watch"
    store.close()
    restarted_store = ShadowCheckpointStore(str(tmp_path / "shadow.sqlite"))
    restarted_runner = ShadowRunner(restarted_store, fixed_entry_atomic=50, max_positions=1, initial_cash_atomic=100)
    restarted = restarted_runner.step(observation, prediction, decision_time="2026-01-01T00:00:05Z")
    assert restarted.duplicate is True
    assert restarted_store.checkpoint_value("last_received_at") == "2026-01-01T00:00:10Z"
    restarted_store.close()


def test_shadow_health_and_window_gates_remain_explicit():
    health = assess_shadow_health(
        quality_state="degraded",
        contradictory=False,
        now="2026-01-01T00:01:00Z",
        latest_arrival="2026-01-01T00:00:00Z",
        existing_position=True,
    )
    assert health.can_enter is False
    assert health.management_action == "hold_and_reconcile_existing_position"
    stale_exit = ShadowCheckpointStore()
    stale_runner = ShadowRunner(stale_exit, fixed_entry_atomic=1, max_positions=1, initial_cash_atomic=1)
    stale_runner.step(
        ShadowObservation("obs-open", "TOKEN", "2026-01-01T00:00:00Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:00Z"),
        decision_time="2026-01-01T00:00:01Z",
    )
    stale_decision = stale_runner.step(
        ShadowObservation("obs-stale", "TOKEN", "2026-01-01T00:00:00Z", "degraded"),
        Prediction("ordinary-v1", -200, 10, "2026-01-01T00:00:00Z"),
        decision_time="2026-01-01T00:00:01Z",
    )
    assert stale_decision.decision.action == "hold"
    assert "hold_and_reconcile" in stale_decision.decision.reason
    stale_exit.close()
    audit = audit_shadow_window(
        "2026-01-01T00:00:00Z",
        "2026-01-05T00:00:00Z",
        eligible_launches=20,
        healthy_scheduled_decisions=100,
        healthy_missed_decisions=2,
        unresolved_gaps=("provider-gap",),
    )
    assert audit.state == "inconclusive"
    assert "insufficient_duration" in audit.reasons
    reconciliation = reconcile_shadow([10, -5], missed_opportunities=1, data_revisions=1, stress_net_return_bps=[-20])
    assert reconciliation.prospective_only is True
    assert reconciliation.state == "inconclusive"


def test_shadow_duplicate_observation_does_not_create_action_for_changed_prediction(tmp_path):
    path = str(tmp_path / "identity.sqlite")
    identity = {
        "config_hash": "c" * 64,
        "source_config_hash": "s" * 64,
        "feature_version": "observatory.features.v0.1",
        "policy_version": "ordinary-baseline-v0.1",
    }
    store = ShadowCheckpointStore(path, run_identity=identity)
    runner = ShadowRunner(store, fixed_entry_atomic=50, max_positions=1, initial_cash_atomic=100, run_identity=identity)
    observation = ShadowObservation("stable", "TOKEN", "2026-01-01T00:00:00Z", "healthy")
    first = runner.step(observation, Prediction("ordinary-v1", 200, 10, observation.received_at), decision_time="2026-01-01T00:00:01Z")
    changed = runner.step(observation, Prediction("ordinary-v2", -200, 10, observation.received_at), decision_time="2026-01-01T00:00:01Z")
    assert first.decision.action == "enter"
    assert changed.duplicate is True
    assert changed.decision.decision_id == first.decision.decision_id
    assert len(store.decisions()) == 1
    store.close()
    mismatched = ShadowCheckpointStore(path)
    try:
        ShadowRunner(
            mismatched,
            fixed_entry_atomic=50,
            max_positions=1,
            initial_cash_atomic=100,
            run_identity={**identity, "config_hash": "d" * 64},
        )
    except ValueError as error:
        assert "identity mismatch" in str(error)
    else:
        raise AssertionError("changed run identity was accepted")
    mismatched.close()


def test_shadow_can_record_requoted_modeled_entry_and_exit_without_submission(tmp_path):
    store = ShadowCheckpointStore(str(tmp_path / "modeled.sqlite"))
    runner = ShadowRunner(store, fixed_entry_atomic=100, max_positions=1, initial_cash_atomic=1_000)
    entry_quote = PoolQuote("pool", "ETH", "TOKEN", 100_000, 200_000, 30, "2026-01-01T00:00:00Z")
    exit_quote = PoolQuote("pool", "TOKEN", "ETH", 200_000, 100_000, 30, "2026-01-01T00:00:10Z")
    entry = runner.step(
        ShadowObservation("entry", "TOKEN", "2026-01-01T00:00:01Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:01Z"),
        decision_time="2026-01-01T00:00:02Z",
        entry_quote=entry_quote,
        model_execution=True,
    )
    assert entry.decision.action == "enter"
    assert entry.decision.modeled_fill_status == "filled"
    assert entry.decision.modeled_output_atomic > 0
    assert entry.decision.execution_state == "not_submitted"
    exit_result = runner.step(
        ShadowObservation("exit", "TOKEN", "2026-01-01T00:00:11Z", "healthy"),
        Prediction("ordinary-v1", -200, 10, "2026-01-01T00:00:11Z"),
        decision_time="2026-01-01T00:00:12Z",
        exit_quote=exit_quote,
        model_execution=True,
    )
    assert exit_result.decision.action == "exit"
    assert exit_result.decision.modeled_fill_status == "filled"
    assert exit_result.decision.modeled_input_atomic == entry.decision.modeled_output_atomic
    assert exit_result.decision.execution_state == "not_submitted"
    assert store.modeled_positions() == {}
    assert len(store.observations()) == 2
    store.close()


def test_shadow_modeled_missing_entry_does_not_open_inventory(tmp_path):
    store = ShadowCheckpointStore(str(tmp_path / "missing-entry.sqlite"))
    runner = ShadowRunner(store, fixed_entry_atomic=100, max_positions=1, initial_cash_atomic=1_000)
    missing = runner.step(
        ShadowObservation("missing", "TOKEN", "2026-01-01T00:00:01Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:01Z"),
        decision_time="2026-01-01T00:00:02Z",
        model_execution=True,
    )
    assert missing.decision.action == "enter"
    assert missing.decision.modeled_fill_status == "missing_state"
    assert store.modeled_positions() == {}
    next_entry = runner.step(
        ShadowObservation("next", "OTHER", "2026-01-01T00:00:03Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:03Z"),
        decision_time="2026-01-01T00:00:04Z",
        model_execution=True,
    )
    assert next_entry.decision.action == "enter"
    assert "max_concurrent_positions" not in next_entry.decision.reason
    store.close()


def test_shadow_sequence_measures_health_and_resumes_idempotently(tmp_path):
    identity = {"config_hash": "a" * 64, "policy_version": "ordinary-baseline-v0.1"}
    store = ShadowCheckpointStore(str(tmp_path / "sequence.sqlite"), run_identity=identity)
    runner = ShadowRunner(
        store,
        fixed_entry_atomic=100,
        max_positions=1,
        initial_cash_atomic=1_000,
        run_identity=identity,
    )
    quote = {
        "pool_id": "pool-1",
        "input_asset": "ETH",
        "output_asset": "TOKEN",
        "reserve_input_atomic": 100_000,
        "reserve_output_atomic": 200_000,
        "fee_bps": 30,
        "observed_at": "2026-01-01T00:00:00Z",
    }
    entries = (
        ShadowInput.from_dict(
            {
                "observation": {
                    "observation_id": "entry",
                    "asset": "TOKEN",
                    "received_at": "2026-01-01T00:00:00Z",
                    "quality_state": "healthy",
                },
                "prediction": {
                    "model_id": "ordinary-v1",
                    "expected_return_bps": 200,
                    "uncertainty_bps": 10,
                    "as_of_time": "2026-01-01T00:00:00Z",
                },
                "entry_quote": quote,
                "model_execution": True,
                "decision_time": "2026-01-01T00:00:05Z",
            }
        ),
        ShadowInput.from_dict(
            {
                "observation": {
                    "observation_id": "stale",
                    "asset": "OTHER",
                    "received_at": "2026-01-01T00:00:06Z",
                    "quality_state": "healthy",
                },
                "prediction": {
                    "model_id": "ordinary-v1",
                    "expected_return_bps": 200,
                    "uncertainty_bps": 10,
                    "as_of_time": "2026-01-01T00:00:06Z",
                },
                "decision_time": "2026-01-01T00:00:30Z",
            }
        ),
    )
    summary = runner.run_sequence(entries + (entries[0],))
    assert summary.input_count == 3
    assert summary.processed_count == 2
    assert summary.duplicate_count == 1
    assert summary.health_counts["healthy"] == 2
    assert summary.health_counts["stale"] == 1
    assert summary.missed_decision_count == 1
    assert summary.action_counts["enter"] == 2
    assert summary.action_counts["watch"] == 1
    assert summary.modeled_fill_counts["filled"] == 2
    assert summary.signing is False and summary.broadcast is False
    assert summary.modeled_positions.get("TOKEN", 0) > 0
    store.close()


def test_shadow_can_record_requoted_modeled_entry_and_exit_without_submission(tmp_path):
    store = ShadowCheckpointStore(str(tmp_path / "modeled.sqlite"))
    runner = ShadowRunner(store, fixed_entry_atomic=100, max_positions=1, initial_cash_atomic=1_000)
    entry_quote = PoolQuote("pool", "ETH", "TOKEN", 100_000, 200_000, 30, "2026-01-01T00:00:00Z")
    exit_quote = PoolQuote("pool", "TOKEN", "ETH", 200_000, 100_000, 30, "2026-01-01T00:00:10Z")
    entry = runner.step(
        ShadowObservation("entry", "TOKEN", "2026-01-01T00:00:01Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:01Z"),
        decision_time="2026-01-01T00:00:02Z",
        entry_quote=entry_quote,
        model_execution=True,
    )
    assert entry.decision.action == "enter"
    assert entry.decision.modeled_fill_status == "filled"
    assert entry.decision.modeled_output_atomic > 0
    assert entry.decision.execution_state == "not_submitted"
    exit_result = runner.step(
        ShadowObservation("exit", "TOKEN", "2026-01-01T00:00:11Z", "healthy"),
        Prediction("ordinary-v1", -200, 10, "2026-01-01T00:00:11Z"),
        decision_time="2026-01-01T00:00:12Z",
        exit_quote=exit_quote,
        model_execution=True,
    )
    assert exit_result.decision.action == "exit"
    assert exit_result.decision.modeled_fill_status == "filled"
    assert exit_result.decision.modeled_input_atomic == entry.decision.modeled_output_atomic
    assert exit_result.decision.execution_state == "not_submitted"
    assert len(store.decisions()) == 2
    store.close()


def test_shadow_modeled_missing_entry_does_not_open_inventory(tmp_path):
    store = ShadowCheckpointStore(str(tmp_path / "missing-entry.sqlite"))
    runner = ShadowRunner(store, fixed_entry_atomic=100, max_positions=1, initial_cash_atomic=1_000)
    missing = runner.step(
        ShadowObservation("missing", "TOKEN", "2026-01-01T00:00:01Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:01Z"),
        decision_time="2026-01-01T00:00:02Z",
        model_execution=True,
    )
    assert missing.decision.action == "enter"
    assert missing.decision.modeled_fill_status == "missing_state"
    next_entry = runner.step(
        ShadowObservation("next", "OTHER", "2026-01-01T00:00:03Z", "healthy"),
        Prediction("ordinary-v1", 200, 10, "2026-01-01T00:00:03Z"),
        decision_time="2026-01-01T00:00:04Z",
        model_execution=True,
    )
    assert next_entry.decision.action == "enter"
    assert "max_concurrent_positions" not in next_entry.decision.reason
    store.close()
