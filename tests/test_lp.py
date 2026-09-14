from willfly.evaluation.lp_stress import LPModeCase, LPStressScenario, compare_lp_modes, stress_lp_scenarios
from willfly.lp.evidence import LPEvidence, evidence_status
from willfly.policies.lp_baselines import fixed_wide_range, idle_lp, volatility_range
from willfly.policies.mode_selection import ModeCandidate, select_mode
from willfly.replay.lp_execution import LPEvent, replay_lp_lifecycle
from willfly.replay.lp_positions import Q96, Q128, UINT256_MODULUS, PositionState, accrue_fee_growth, amounts_for_liquidity, amounts_for_sqrt_price, fee_growth_inside_from_outside, round_tick, sqrt_price_at_tick


def test_lp_positions_round_ticks_accrue_after_leaving_range_and_preserve_residuals():
    position = PositionState("position", "pool", "TOKEN0", "TOKEN1", 10, -60, 60)
    assert round_tick(61, 60, upper=True) == 120
    assert amounts_for_liquidity(position, 0) == (600, 600)
    updated = accrue_fee_growth(position, current_tick=0, fee_growth_inside0=Q128, fee_growth_inside1=2 * Q128)
    assert (updated.tokens_owed0, updated.tokens_owed1) == (10, 20)
    outside = accrue_fee_growth(position, current_tick=100, fee_growth_inside0=Q128, fee_growth_inside1=Q128)
    assert (outside.tokens_owed0, outside.tokens_owed1) == (10, 10)
    crossed = accrue_fee_growth(updated, current_tick=100, fee_growth_inside0=2 * Q128, fee_growth_inside1=3 * Q128)
    assert (crossed.tokens_owed0, crossed.tokens_owed1) == (20, 30)
    result = replay_lp_lifecycle(
        [LPEvent("open", "open", 100, 100, source_ref="lp:open"), LPEvent("remove", "remove", 90, 120, gas_atomic=3, source_ref="lp:remove")],
        token0="TOKEN0", token1="TOKEN1", initial_balances={"TOKEN0": 100, "TOKEN1": 100},
    )
    assert result.balances == {"TOKEN0": 90, "TOKEN1": 120}
    assert result.fees_paid_atomic == {"TOKEN0": 0, "TOKEN1": 0}
    assert result.gas_paid_atomic == 3
    assert result.gas_paid_by_asset == {"unknown:gas": 3}
    assert result.unreconciled_gas_by_asset == {"unknown:gas": 3}


def test_lp_known_gas_asset_debits_balance_and_missing_gas_balance_is_liability():
    debited = replay_lp_lifecycle(
        [
            LPEvent("open", "open", 10, 10, gas_atomic=3, gas_asset="TOKEN0", source_ref="lp:open"),
            LPEvent("remove", "remove", 4, 6, gas_atomic=2, gas_asset="TOKEN0", source_ref="lp:remove"),
        ],
        token0="TOKEN0",
        token1="TOKEN1",
        initial_balances={"TOKEN0": 20, "TOKEN1": 20},
    )
    assert debited.balances == {"TOKEN0": 9, "TOKEN1": 16}
    assert debited.gas_paid_by_asset == {"TOKEN0": 5}
    assert debited.unreconciled_gas_by_asset == {}
    liability = replay_lp_lifecycle(
        [LPEvent("open", "open", 10, 0, gas_atomic=3, gas_asset="ETH", source_ref="lp:open")],
        token0="TOKEN0",
        token1="TOKEN1",
        initial_balances={"TOKEN0": 20, "TOKEN1": 20},
    )
    assert liability.balances == {"TOKEN0": 10, "TOKEN1": 20}
    assert liability.unreconciled_gas_by_asset == {"ETH": 3}
    partial = replay_lp_lifecycle(
        [LPEvent("open", "open", 0, 0, gas_atomic=3, gas_asset="ETH", source_ref="lp:partial")],
        token0="TOKEN0",
        token1="TOKEN1",
        initial_balances={"TOKEN0": 0, "TOKEN1": 0, "ETH": 2},
    )
    assert partial.balances["ETH"] == 0
    assert partial.unreconciled_gas_by_asset == {"ETH": 1}


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


def test_lp_exact_sqrt_price_amounts_handle_full_range_boundaries():
    position = PositionState("position", "pool", "TOKEN0", "TOKEN1", 10, -60, 60)
    lower = Q96 // 2
    upper = 2 * Q96
    assert amounts_for_sqrt_price(
        position,
        current_sqrt_price_x96=lower,
        lower_sqrt_price_x96=lower,
        upper_sqrt_price_x96=upper,
    )[1] == 0
    assert amounts_for_sqrt_price(
        position,
        current_sqrt_price_x96=upper,
        lower_sqrt_price_x96=lower,
        upper_sqrt_price_x96=upper,
    )[0] == 0


def test_lp_lifecycle_rejects_amounts_that_disagree_with_protocol_price_checkpoint():
    rejected = replay_lp_lifecycle(
        [
            LPEvent(
                "open",
                "open",
                6,
                5,
                source_ref="lp:open",
                liquidity=10,
                tick_lower=-60,
                tick_upper=60,
                current_sqrt_price_x96=Q96,
                lower_sqrt_price_x96=Q96 // 2,
                upper_sqrt_price_x96=2 * Q96,
            )
        ],
        token0="TOKEN0",
        token1="TOKEN1",
        initial_balances={"TOKEN0": 6, "TOKEN1": 5},
    )
    assert rejected.failed_actions == ("open",)
    assert rejected.balances == {"TOKEN0": 6, "TOKEN1": 5}


def test_lp_remove_collect_without_position_and_duplicate_delivery_do_not_credit_twice():
    events = [
        LPEvent("orphan", "remove", 90, 120, source_ref="lp:orphan"),
        LPEvent("open", "open", 100, 100, source_ref="lp:open"),
        LPEvent("remove", "remove", 90, 120, source_ref="lp:remove"),
        LPEvent("remove", "remove", 90, 120, source_ref="lp:remove-duplicate"),
    ]
    result = replay_lp_lifecycle(events, token0="TOKEN0", token1="TOKEN1", initial_balances={"TOKEN0": 100, "TOKEN1": 100})
    assert result.balances == {"TOKEN0": 90, "TOKEN1": 120}
    assert result.failed_actions == ("orphan",)
    assert result.duplicate_action_ids == ("remove",)


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


def test_lp_signed_resize_burn_returns_inventory_and_keeps_zero_position_for_collect():
    result = replay_lp_lifecycle(
        [
            LPEvent("open", "open", 10, 10, source_ref="lp:open", position_id="p1", owner="alice", liquidity=10),
            LPEvent("burn", "resize", 4, 6, source_ref="lp:burn", position_id="p1", owner="alice", liquidity_delta=-4),
            LPEvent("remove", "remove", 6, 4, source_ref="lp:remove", position_id="p1", owner="alice"),
        ],
        token0="TOKEN0",
        token1="TOKEN1",
        initial_balances={"TOKEN0": 10, "TOKEN1": 10},
    )
    assert result.failed_actions == ()
    assert result.balances == {"TOKEN0": 10, "TOKEN1": 10}


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
    assert fixed_wide_range(0).action == "watch"
    assert volatility_range(0, 100).tick_upper > 0
    assert idle_lp().action == "watch"
    live_evidence = LPEvidence(
        chain_id=4663,
        deployment_ref="rpc:deployment",
        bytecode_ref="rpc:bytecode",
        live_protocol_verified=True,
        token_order_verified=True,
        tick_math_verified=True,
        hook_behavior_verified=True,
        supported_tokens_verified=True,
        position_state_verified=True,
        receipt_accounting_verified=True,
        gas_denomination_verified=True,
        complete_receipts_verified=True,
        observed_checkpoint_count=20,
        source_refs=("rpc:position",),
    )
    decision = select_mode((ModeCandidate("lp", 200, True, 100, live_evidence), ModeCandidate("spot", 100, True, 100)), required_cash_atomic=50)
    assert decision.mode == "lp"
    assert select_mode((ModeCandidate("lp", 200, True, 100),), required_cash_atomic=50).reason == "lp_disabled_until_verified_live_evidence"
    assert select_mode((), required_cash_atomic=50).mode == "idle"
    assert select_mode((ModeCandidate("spot", 100, True, 100),), required_cash_atomic=50, already_allocated=True).accepted is False


def test_lp_stress_is_explicitly_modeled():
    results = stress_lp_scenarios([LPStressScenario("wide-stress", 2000, 100, 5, 1000)], base_fee_atomic=50, base_value_atomic=1000)
    assert results[0].state == "modeled"
    assert results[0].modeled_net_atomic is not None and results[0].modeled_net_atomic < 0


def test_lp_fee_growth_inside_uses_modular_outside_boundary_state():
    position = PositionState("p", "pool", "A", "B", 5, -10, 10)
    assert fee_growth_inside_from_outside(
        position,
        current_tick=0,
        fee_growth_global0=100,
        fee_growth_global1=200,
        fee_growth_outside_lower0=10,
        fee_growth_outside_lower1=20,
        fee_growth_outside_upper0=30,
        fee_growth_outside_upper1=40,
    ) == (60, 140)


def test_lp_exact_tick_math_and_unsupported_paths_stay_out_of_ledger():
    assert sqrt_price_at_tick(0) == Q96
    result = replay_lp_lifecycle(
        [
            LPEvent("hooked", "open", 10, 10, source_ref="lp:hooked", hook="0x" + "1" * 40),
            LPEvent("valid", "open", 10, 10, source_ref="lp:valid"),
            LPEvent("unsupported-token", "open", 10, 10, source_ref="lp:token"),
        ],
        token0="A",
        token1="B",
        initial_balances={"A": 20, "B": 20},
        supported_tokens={"A", "B"},
    )
    assert result.unsupported_actions == ("hooked",)
    assert result.failed_actions == ("unsupported-token",)
    assert result.balances == {"A": 10, "B": 10}


def test_lp_failed_and_orphaned_receipts_keep_lineage_without_crediting_tokens():
    result = replay_lp_lifecycle(
        [
            LPEvent("reverted", "failed", 8, 9, gas_atomic=3, gas_asset="ETH", source_ref="receipt:revert", receipt_status="reverted"),
            LPEvent("orphaned", "remove", 8, 9, gas_atomic=4, gas_asset="ETH", source_ref="receipt:orphan", canonical_status="orphaned", status="confirmed"),
        ],
        token0="A",
        token1="B",
        initial_balances={"A": 20, "B": 20, "ETH": 10},
    )
    assert result.failed_actions == ("reverted",)
    assert result.orphaned_action_ids == ("orphaned",)
    assert result.balances == {"A": 20, "B": 20, "ETH": 7}
    assert result.source_refs == ("receipt:revert", "receipt:orphan")


def test_lp_canonical_receipt_can_supersede_provisional_orphan_delivery():
    result = replay_lp_lifecycle(
        [
            LPEvent("open", "open", 10, 10, source_ref="receipt:orphan", canonical_status="orphaned"),
            LPEvent("open", "open", 10, 10, source_ref="receipt:canonical"),
            LPEvent("open", "open", 10, 10, source_ref="receipt:duplicate"),
        ],
        token0="A",
        token1="B",
        initial_balances={"A": 10, "B": 10},
    )
    assert result.balances == {"A": 0, "B": 0}
    assert result.orphaned_action_ids == ()
    assert result.duplicate_action_ids == ("open",)


def test_lp_evidence_gate_requires_live_requirements_even_with_documented_state():
    assert evidence_status(LPEvidence()) == "inconclusive"
    cases = (LPModeCase("one", "b1", "2026-01-01T00:00:00Z", 100, 200),)
    report = compare_lp_modes(cases, capital_atomic=100, lp_evidence_state="verified", lp_evidence=LPEvidence())
    assert report.lp is None
    assert report.reasons == ("lp_disabled_until_verified_live_evidence",)
