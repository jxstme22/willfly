from dataclasses import replace

from willfly.domain import PaymentLeg, TradeEvidence
from willfly.domain.wallets import activity_from_trade, build_wallet_observation
from willfly.replay.accounting import reconcile_wallet_observation


TOKEN = "0x1111111111111111111111111111111111111111"
WALLET = "0x2222222222222222222222222222222222222222"
QUOTE = "0x3333333333333333333333333333333333333333"


def _trade(classification: str = "genuine_swap") -> TradeEvidence:
    return TradeEvidence(
        "0x" + "44" * 32,
        WALLET,
        TOKEN,
        classification,
        (PaymentLeg(QUOTE, "10", "out", WALLET, QUOTE, "payment"),) if classification == "genuine_swap" else (),
        (PaymentLeg(TOKEN, "100", "in", QUOTE, WALLET, "receipt"),),
        QUOTE,
        None,
        False,
        None,
        (),
        "trade-evidence.v0.2",
        "2026-09-14T00:00:00Z",
        "2026-09-14T00:00:01Z",
        ("raw:trade",),
        "verified" if classification == "genuine_swap" else "uncertain",
        "buy" if classification == "genuine_swap" else "unknown",
        (),
    )


def test_accounting_separates_reconciled_flow_from_unknown_residuals() -> None:
    confirmed = activity_from_trade(_trade(), canonical_status="canonical")
    unknown = activity_from_trade(replace(_trade(), transaction_hash="0x" + "55" * 32, classification="ambiguous", route_status="uncertain", trade_direction="unknown"))
    observation = build_wallet_observation(
        [confirmed, unknown],
        wallet=WALLET,
        as_of_time="2026-09-14T00:01:00Z",
        arrival_cutoff="2026-09-14T00:01:00Z",
    )
    report = reconcile_wallet_observation(observation)
    assert report.balances_delta_atomic == {QUOTE: "-10", TOKEN: "100"}
    assert report.residual_assets_atomic == {QUOTE: "-10", TOKEN: "100"}
    assert unknown.activity_id in report.unresolved_activity_ids
    assert report.status == "degraded"
