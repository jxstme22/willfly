from dataclasses import replace

from willfly.domain import PaymentLeg, TradeEvidence
from willfly.domain.wallets import WalletActivity, activity_from_lp, activity_from_trade, build_wallet_observation
from willfly.features.lp_behavior import LPObservation
from willfly.storage.wallet import WalletObservationStore


TOKEN = "0x1111111111111111111111111111111111111111"
WALLET = "0x2222222222222222222222222222222222222222"
QUOTE = "0x3333333333333333333333333333333333333333"
TX = "0x" + "44" * 32


def _trade() -> TradeEvidence:
    return TradeEvidence(
        transaction_hash=TX,
        wallet=WALLET,
        token=TOKEN,
        classification="genuine_swap",
        payment_legs=(PaymentLeg(QUOTE, "10", "out", WALLET, QUOTE, "payment:1"),),
        receipt_legs=(PaymentLeg(TOKEN, "100", "in", QUOTE, WALLET, "receipt:1"),),
        quote_asset=QUOTE,
        valuation_method=None,
        estimated_usd=False,
        estimated_usd_value=None,
        reason_flags=(),
        method_version="trade-evidence.v0.2",
        as_of_time="2026-09-14T00:00:01Z",
        retrieved_time="2026-09-14T00:00:02Z",
        raw_event_refs=("raw:swap:1",),
        route_status="verified",
        trade_direction="buy",
    )


def _lp(action: str, delta: int, ref: str) -> LPObservation:
    return LPObservation(
        WALLET,
        "0x" + "55" * 32,
        "position-1",
        action,
        "2026-09-14T00:00:03Z",
        "2026-09-14T00:00:04Z",
        delta,
        "1",
        "2",
        -10,
        10,
        "public-wallet-fixture",
        ref,
    )


def test_trade_conversion_preserves_exact_deltas_and_unknown_routes() -> None:
    activity = activity_from_trade(_trade(), canonical_status="canonical")
    assert activity.status == "confirmed"
    assert activity.asset_deltas_atomic == {QUOTE: "-10", TOKEN: "100"}
    unknown = replace(_trade(), classification="ambiguous", payment_legs=(), route_status="uncertain", trade_direction="unknown")
    unresolved = activity_from_trade(unknown)
    assert unresolved.status == "unknown"
    assert unresolved.route_status == "uncertain"
    assert "trade_route_or_classification_unresolved" in unresolved.reason_flags


def test_observer_derives_position_and_excludes_fork_or_unknown_state() -> None:
    open_activity = activity_from_lp(_lp("open", 100, "lp:open"), canonical_status="canonical")
    remove_activity = activity_from_lp(_lp("remove", 40, "lp:remove"), canonical_status="canonical")
    unresolved = activity_from_lp(_lp("unknown", 50, "lp:unknown"), canonical_status="unresolved")
    observation = build_wallet_observation(
        [remove_activity, unresolved, open_activity],
        wallet=WALLET,
        as_of_time="2026-09-14T00:00:10Z",
        arrival_cutoff="2026-09-14T00:00:10Z",
    )
    assert observation.positions[0].liquidity == 60
    assert observation.positions[0].lifecycle_state == "unknown"
    assert observation.quality_state == "degraded"
    assert "position_canonicality_unresolved" in observation.missingness


def test_store_is_idempotent_survives_restart_and_retains_revisions(tmp_path) -> None:
    activity = activity_from_lp(_lp("open", 100, "lp:open"), canonical_status="provisional")
    with WalletObservationStore(tmp_path) as store:
        first = store.record([activity, activity])
        assert first.inserted == 1 and first.duplicates == 1
        revised = replace(activity, canonical_status="orphaned")
        assert store.record([revised]).revised == 1
        assert len(store.list_revisions(activity.activity_id)) == 1
        cursor = store.save_cursor(
            wallet=WALLET,
            source="robinhood-v4",
            filter_identity="filter:v1",
            last_block_number=100,
            last_block_hash="0x" + "aa" * 32,
        )
        assert cursor.state == "healthy"
    with WalletObservationStore(tmp_path) as restarted:
        assert len(restarted.list_activities(wallet=WALLET)) == 1
        assert restarted.observation(
            wallet=WALLET,
            as_of_time="2026-09-14T00:00:10Z",
            arrival_cutoff="2026-09-14T00:00:10Z",
        ).positions[0].lifecycle_state == "unknown"
        repaired = restarted.save_cursor(
            wallet=WALLET,
            source="robinhood-v4",
            filter_identity="filter:v2",
            last_block_number=101,
            last_block_hash="0x" + "bb" * 32,
        )
        assert repaired.state == "needs_repair"
        assert repaired.reason == "cursor_filter_identity_changed"


def test_activity_contract_rejects_unknown_route_status_for_lp() -> None:
    try:
        WalletActivity(
            "lp:bad",
            WALLET,
            "lp",
            "open",
            "confirmed",
            "canonical",
            "2026-09-14T00:00:00Z",
            "2026-09-14T00:00:01Z",
            None,
            "pool",
            "position",
            1,
            {},
            "uncertain",
            ("lp:bad",),
            (),
        )
    except ValueError as exc:
        assert "LP route status" in str(exc)
    else:
        raise AssertionError("invalid LP route status was accepted")
