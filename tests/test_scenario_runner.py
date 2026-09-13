from willfly.evaluation.replay_audit import CostScenario
from willfly.evaluation.scenario_runner import run_quote_stress_scenarios
from willfly.replay.execution import PoolQuote


def test_quote_stress_replays_same_path_with_delay_fee_and_slippage() -> None:
    entry = PoolQuote("pool", "ETH", "TOKEN", 100_000, 200_000, 30, "2026-09-14T00:00:00Z")
    exit_quote = PoolQuote("pool", "TOKEN", "ETH", 200_000, 100_000, 30, "2026-09-14T00:00:01Z")
    outcomes = run_quote_stress_scenarios(
        entry,
        exit_quote,
        input_atomic=1_000,
        submitted_at="2026-09-14T00:00:01Z",
        scenarios=(CostScenario("base", 0, 0, 0), CostScenario("stressed", 5, 100, 250)),
    )
    assert [outcome.status for outcome in outcomes] == ["completed", "completed"]
    assert outcomes[0].net_quote_atomic != outcomes[1].net_quote_atomic
    assert outcomes[1].source_refs[0].startswith("quote:pool:")


def test_missing_or_unsupported_quotes_remain_failures() -> None:
    outcome = run_quote_stress_scenarios(
        None,
        None,
        input_atomic=100,
        submitted_at="2026-09-14T00:00:00Z",
        scenarios=(CostScenario("missing", 0, 0, 0),),
    )[0]
    assert outcome.status == "entry_failed"
    assert outcome.entry_status == "missing_state"


def test_mismatched_quotes_cannot_be_called_one_round_trip() -> None:
    entry = PoolQuote("pool", "ETH", "TOKEN", 100, 100, 30, "2026-09-14T00:00:00Z")
    exit_quote = PoolQuote("pool", "OTHER", "ETH", 100, 100, 30, "2026-09-14T00:00:00Z")
    try:
        run_quote_stress_scenarios(
            entry,
            exit_quote,
            input_atomic=10,
            submitted_at="2026-09-14T00:00:00Z",
            scenarios=(CostScenario("base", 0, 0, 0),),
        )
    except ValueError as error:
        assert "reverse" in str(error)
    else:
        raise AssertionError("mismatched round-trip quotes were accepted")
