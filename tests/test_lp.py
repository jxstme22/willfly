from willfly.evaluation.lp_stress import LPModeCase, LPStressScenario, compare_lp_modes, stress_lp_scenarios
from willfly.policies.lp_baselines import fixed_wide_range, idle_lp, volatility_range
from willfly.policies.mode_selection import ModeCandidate, select_mode
from willfly.replay.lp_execution import LPEvent, replay_lp_lifecycle
from willfly.replay.lp_positions import Q96, Q128, UINT256_MODULUS, PositionState, accrue_fee_growth, amounts_for_liquidity, amounts_for_sqrt_price, round_tick


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
    assert result.fees_paid_atomic == {"TOKEN0": 0, "TOKEN1": 0}
    assert result.gas_paid_atomic == 3


def test_lp_exact_sqrt_price_amounts_and_modular_fee_growth_are_supported():
    position = PositionState("position", "pool", "TOKEN0", "TOKEN1", 10, -60, 60)
    assert amounts_for_sqrt_price(
        position,
        current_sqrt_price_x96=Q96,
        lower_sqrt_price_x96=Q96 // 2,
        upper_sqrt_price_x96=2 * Q96,
    ) == (5, 5)
    previous = PositionState("position", "pool", "TOKEN0", "TOKEN1", 10, -60, 60, UINT256_MODULUS - 2, UINT256_MODULUS - 3)
    wrapped = accrue_fee_growth(previous, current_tick=0, fee_growth_inside0=1, fee_growth_inside1=2)
    assert wrapped.tokens_owed0 == 0 and wrapped.tokens_owed1 == 0


def test_lp_remove_collect_without_position_and_duplicate_delivery_do_not_credit_twice():
    events = [
        LPEvent("orphan", "remove", 90, 120, source_ref="lp:orphan"),
        LPEvent("open", "open", 100, 100, source_ref="lp:open"),
        LPEvent("remove", "remove", 90, 120, source_ref="lp:remove"),
        LPEvent("remove", "remove", 90, 120, source_ref="lp:remove-duplicate"),
    ]
    result = replay_lp_lifecycle(events, token0="TOKEN0", token1="TOKEN1", initial_balances={"TOKEN0": 100, "TOKEN1": 100})
    assert result.balances == {"TOKEN0": 90, "TOKEN1": 120}
    assert result.failed_actions == ("orphan", "remove")


def test_lp_owner_and_position_identity_are_checked():
    result = replay_lp_lifecycle(
        [
            LPEvent("open", "open", 10, 10, source_ref="lp:open", position_id="p1", owner="alice"),
            LPEvent("bad-owner", "collect", 2, 3, source_ref="lp:bad-owner", position_id="p1", owner="bob"),
            LPEvent("good-collect", "collect", 2, 3, source_ref="lp:good-collect", position_id="p1", owner="alice"),
        ],
        token0="TOKEN0",
        token1="TOKEN1",
        initial_balances={"TOKEN0": 10, "TOKEN1": 10},
    )
    assert result.failed_actions == ("bad-owner",)
    assert result.fees_paid_atomic == {"TOKEN0": 2, "TOKEN1": 3}


def test_lp_mode_comparison_keeps_unverified_lp_out_of_shared_capital_metrics():
    cases = tuple(
        LPModeCase(f"case-{index}", f"block-{index}", f"2026-01-01T00:0{index}:00Z", 100, 200)
        for index in range(4)
    )
    disabled = compare_lp_modes(cases, capital_atomic=100_000, lp_evidence_state="inconclusive")
    assert disabled.mutually_exclusive is True
    assert disabled.lp is None
    assert disabled.reasons == ("lp_disabled_until_verified_evidence",)
    enabled = compare_lp_modes(cases, capital_atomic=100_000, lp_evidence_state="verified")
    assert enabled.lp is not None
    assert enabled.lp.max_drawdown_bps == 0


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
