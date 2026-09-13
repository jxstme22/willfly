from willfly.evaluation.lp_stress import LPStressScenario, stress_lp_scenarios
from willfly.policies.lp_baselines import fixed_wide_range, idle_lp, volatility_range
from willfly.policies.mode_selection import ModeCandidate, select_mode
from willfly.replay.lp_execution import LPEvent, replay_lp_lifecycle
from willfly.replay.lp_positions import Q128, PositionState, accrue_fee_growth, amounts_for_liquidity, round_tick


def test_lp_positions_round_ticks_accrue_only_when_in_range_and_preserve_residuals():
    position = PositionState("position", "pool", "TOKEN0", "TOKEN1", 10, -60, 60)
    assert round_tick(61, 60, upper=True) == 120
    assert amounts_for_liquidity(position, 0) == (600, 600)
    updated = accrue_fee_growth(position, current_tick=0, fee_growth_inside0=Q128, fee_growth_inside1=2 * Q128)
    assert (updated.tokens_owed0, updated.tokens_owed1) == (10, 20)
    unchanged = accrue_fee_growth(position, current_tick=100, fee_growth_inside0=Q128, fee_growth_inside1=Q128)
    assert unchanged.tokens_owed0 == 0
    result = replay_lp_lifecycle(
        [LPEvent("open", "open", 100, 100, source_ref="lp:open"), LPEvent("remove", "remove", 90, 120, gas_atomic=3, source_ref="lp:remove")],
        token0="TOKEN0", token1="TOKEN1", initial_balances={"TOKEN0": 100, "TOKEN1": 100},
    )
    assert result.balances == {"TOKEN0": 90, "TOKEN1": 120}
    assert result.gas_paid_atomic == 3


def test_lp_policies_and_mode_selection_never_double_allocate():
    assert fixed_wide_range(0).tick_lower == -600
    assert volatility_range(0, 100).tick_upper > 0
    assert idle_lp().action == "watch"
    decision = select_mode((ModeCandidate("lp", 200, True, 100), ModeCandidate("spot", 100, True, 100)), required_cash_atomic=50)
    assert decision.mode == "lp"
    assert select_mode((), required_cash_atomic=50).mode == "idle"
    assert select_mode((ModeCandidate("spot", 100, True, 100),), required_cash_atomic=50, already_allocated=True).accepted is False


def test_lp_stress_is_explicitly_modeled():
    results = stress_lp_scenarios([LPStressScenario("wide-stress", 2000, 100, 5, 1000)], base_fee_atomic=50, base_value_atomic=1000)
    assert results[0].state == "modeled"
    assert results[0].modeled_net_atomic is not None and results[0].modeled_net_atomic < 0
