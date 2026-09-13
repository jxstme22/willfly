from willfly.evaluation.metrics import EpisodeResult, calculate_metrics
from willfly.evaluation.baseline_lab import BaselineCase, BaselineLabConfig, run_baseline_laboratory
from willfly.evaluation.runs import BudgetExceeded, RunTracker
from willfly.evaluation.walk_forward import WalkForwardWindow, evaluate_walk_forward
from willfly.models.conventional import FeatureRow, LinearBaseline, RecurrentBaseline
from willfly.policies.baselines import BaselineConfig, MarketObservation, confirmation_momentum, idle_cash, tracked_wallet_follow, verified_flow_filter
from willfly.policies.prediction import Prediction, map_prediction


def test_baselines_share_cutoff_and_keep_unknown_cohort_unavailable():
    observation = MarketObservation("TOKEN", "2026-01-01T00:00:00Z", 100, 1000, 20, True, "unknown", 2)
    config = BaselineConfig(minimum_flow_atomic=50, minimum_liquidity_atomic=500)
    assert idle_cash(observation).action == "watch"
    assert confirmation_momentum(observation).action == "enter"
    assert verified_flow_filter(observation, config).action == "enter"
    assert tracked_wallet_follow(observation).reason == "cohort_unavailable_or_uncertain"
    assert map_prediction(Prediction("model", 300, 100, observation.as_of_time)).action == "enter"


def test_conventional_models_reset_recurrent_state_and_runs_enforce_budget():
    rows = [FeatureRow("a1", "a", (1.0, 0.0), 100), FeatureRow("a2", "a", (1.0, 1.0), 200), FeatureRow("b1", "b", (1.0, 0.0), 50)]
    linear = LinearBaseline.fit(rows, seed=7)
    assert linear.to_dict() == LinearBaseline.fit(rows, seed=7).to_dict()
    recurrent = RecurrentBaseline.fit(rows, seed=7)
    predictions = recurrent.predict_episode(rows)
    assert len(predictions) == 3
    tracker = RunTracker(search_budget=1)
    run_id = tracker.start(source={"s": 1}, code={"c": 1}, data={"d": 1}, config={"x": 1}, seeds=(1, 2, 3, 4, 5), parameter_count=4)
    assert tracker.trial(run_id) == 1
    try:
        tracker.trial(run_id)
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("budget overrun was accepted")
    assert tracker.runs[0].status == "failed"
    assert tracker.runs[0].failure == "search_budget_exceeded"


def test_metrics_and_walk_forward_keep_failures_and_all_windows():
    results = [EpisodeResult("a", "block-1", 100, 50), EpisodeResult("b", "block-2", -50, 0, failed=True)]
    report = calculate_metrics(results, equity_curve_atomic=[1000, 1010, 1005], bootstrap_replicates=20, seed=1)
    assert report.mean_excess_return_bps == 0
    assert report.failure_rate_bps == 5000
    assert report.inference_state == "insufficient_blocks"
    walk = evaluate_walk_forward({"idle": results}, [WalkForwardWindow("test-1", 100, 0, 30, 50), WalkForwardWindow("test-2", 200, 5, 40, 100)], strongest_practical_baseline="idle")
    assert set(walk.windows) == {"test-1:idle", "test-2:idle"}
    assert walk.state == "inconclusive_missing_replay"


def test_drawdown_uses_ordered_equity_not_summed_episode_returns():
    records = [EpisodeResult("a", "block-1", -5000, 0), EpisodeResult("b", "block-2", -5000, 0)]
    report = calculate_metrics(records, equity_curve_atomic=[100_000, 95_000, 90_000], min_blocks=2)
    assert report.max_drawdown_bps == 1000
    assert report.inference_state == "pass"


def test_baseline_laboratory_hashes_inputs_and_compares_all_policies():
    cases = [
        BaselineCase(
            f"case-{index}",
            f"block-{index}",
            MarketObservation("TOKEN", f"2026-01-01T00:0{index}:00Z", 100, 1000, 20, True, "member", 2),
            100 if index % 2 else -50,
            benchmark_return_bps=10,
            exposure_if_enter_bps=500,
        )
        for index in range(4)
    ]
    config = BaselineLabConfig(capital_atomic=100_000, minimum_blocks=4)
    first = run_baseline_laboratory(cases, config=config)
    second = run_baseline_laboratory(cases, config=config)
    assert first.dataset_hash == second.dataset_hash
    assert first.config_hash == second.config_hash
    assert first.code_hash == second.code_hash
    assert first.policy_names == (
        "confirmation_momentum",
        "fixed_horizon_hold",
        "idle_cash",
        "tracked_wallet_follow",
        "verified_flow_filter",
    )
    assert first.baseline_selection is None
    assert first.evidence_state == "pass"
    assert first.reports["idle_cash"].max_drawdown_bps == 0
    assert first.reports["confirmation_momentum"].max_drawdown_bps is not None
