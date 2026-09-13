from dataclasses import replace

from willfly.domain import Launch, PaymentLeg, PoolIdentity, RawEvent, TradeEvidence
from willfly.features.discovery import PoolProjection, build_discovery_snapshot
from willfly.features.timelines import build_token_timeline


TOKEN = "0x1111111111111111111111111111111111111111"
WALLET = "0x2222222222222222222222222222222222222222"
QUOTE = "0x3333333333333333333333333333333333333333"


def _launch(first_seen: str, lifecycle: str = "unknown") -> Launch:
    return Launch(
        chain_id=4663,
        token=TOKEN,
        launch_contract=None,
        launch_contract_version=None,
        creation_evidence=("launch:tx",),
        creator=None,
        created_at="2026-09-13T00:00:00Z",
        first_seen_at=first_seen,
        origin_confidence="observed",
        linked_pool_ids=(),
        lifecycle_state=lifecycle,
    )


def _trade(classification: str, event_time: str, retrieved_time: str, amount: str = "100") -> TradeEvidence:
    payment = PaymentLeg(QUOTE, "10", "out", WALLET, QUOTE, "payment:1")
    receipt = PaymentLeg(TOKEN, amount, "in", QUOTE, WALLET, "receipt:1")
    return TradeEvidence(
        transaction_hash="0x" + str(len(event_time)).zfill(2) * 32,
        wallet=WALLET,
        token=TOKEN,
        classification=classification,
        payment_legs=(payment,) if classification == "genuine_swap" else (),
        receipt_legs=(receipt,),
        quote_asset=QUOTE,
        valuation_method=None,
        estimated_usd=False,
        estimated_usd_value=None,
        reason_flags=("fixture",),
        method_version="trade-evidence.v0.2",
        as_of_time=event_time,
        retrieved_time=retrieved_time,
        raw_event_refs=(f"trade:{event_time}",),
        route_status="verified" if classification == "genuine_swap" else "uncertain",
        trade_direction="buy" if classification == "genuine_swap" else "unknown",
    )


def test_discovery_snapshot_keeps_unknown_lifecycle_and_separates_first_seen() -> None:
    pool = PoolProjection(
        identity=PoolIdentity(4663, "uniswap_v4", "0x" + "44" * 20, None, "0x" + "55" * 32, "0x" + "0" * 40, TOKEN, 3000, 60, "0x" + "0" * 40),
        first_observed_at="2026-09-13T00:00:03Z",
        trading_status="inactive",
        raw_event_refs=("pool:event",),
    )
    future = _launch("2026-09-13T00:01:00Z", "graduated")
    snapshot = build_discovery_snapshot(
        [_launch("2026-09-13T00:00:02Z"), future],
        [pool],
        as_of_time="2026-09-13T00:00:10Z",
    )
    assert len(snapshot.launches) == 1
    assert snapshot.launches[0].lifecycle_state == "unknown"
    assert snapshot.pools[0].trading_status == "inactive"
    assert snapshot.canonical_event_count == 0
    assert "canonical_event_reconciliation_unavailable" in snapshot.missingness


def test_timeline_uses_event_and_arrival_cutoffs_and_excludes_planted_receipt() -> None:
    old_swap = _trade("genuine_swap", "2026-09-13T00:00:01Z", "2026-09-13T00:00:02Z")
    late_swap = _trade("genuine_swap", "2026-09-13T00:00:03Z", "2026-09-13T00:00:20Z", "900")
    ambiguous = _trade("ambiguous", "2026-09-13T00:00:04Z", "2026-09-13T00:00:05Z", "1000")
    snapshot = build_token_timeline(
        [old_swap, late_swap, ambiguous],
        token=TOKEN,
        event_cutoff="2026-09-13T00:00:10Z",
        arrival_cutoff="2026-09-13T00:00:10Z",
    )
    assert snapshot.values["verified_buy_count"] == 1
    assert snapshot.values["verified_token_in_atomic"] == "100"
    assert snapshot.values["ambiguous_activity_count"] == 1
    assert "ambiguous_activity_excluded_from_verified_flow" in snapshot.missingness


def test_timeline_excludes_legacy_genuine_rows_and_reports_buys_sells_separately() -> None:
    buy = _trade("genuine_swap", "2026-09-13T00:00:01Z", "2026-09-13T00:00:02Z", "100")
    sell_payment = PaymentLeg(TOKEN, "40", "out", WALLET, QUOTE, "sell:payment")
    sell_receipt = PaymentLeg(QUOTE, "7", "in", QUOTE, WALLET, "sell:receipt")
    sell = replace(
        buy,
        transaction_hash="0x" + "99" * 32,
        payment_legs=(sell_payment,),
        receipt_legs=(sell_receipt,),
        trade_direction="sell",
        raw_event_refs=("sell",),
    )
    legacy = replace(
        buy,
        transaction_hash="0x" + "88" * 32,
        method_version="trade-evidence.v0.1",
        raw_event_refs=("legacy",),
    )
    snapshot = build_token_timeline(
        [buy, sell, legacy],
        token=TOKEN,
        event_cutoff="2026-09-13T00:00:10Z",
        arrival_cutoff="2026-09-13T00:00:10Z",
    )
    assert snapshot.values["verified_buy_count"] == 1
    assert snapshot.values["verified_sell_count"] == 1
    assert snapshot.values["verified_token_in_atomic"] == "100"
    assert snapshot.values["verified_token_out_atomic"] == "40"
    assert snapshot.values["verified_quote_in_atomic"] == {QUOTE: "7"}
    assert "unverified_trade_evidence_excluded_from_verified_flow" in snapshot.missingness
