import json

from willfly.evaluation.shadow import audit_shadow_window, reconcile_shadow
from willfly.policies.prediction import Prediction
from willfly.shadow.config import freeze_shadow_config
from willfly.shadow.health import assess_shadow_health
from willfly.shadow.runner import ShadowCheckpointStore, ShadowObservation, ShadowRunner


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
