"""Token timelines with separate event-time and availability cutoffs."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from willfly.domain import TradeEvidence, WalletCohort, Observation
from willfly.adapters.protocols.v4 import deduplicate_trade_evidence


def build_token_timeline(
    trades: Iterable[TradeEvidence],
    *,
    token: str,
    event_cutoff: str,
    arrival_cutoff: str,
    feature_version: str = "timeline.v0.1",
    cohorts: Iterable[WalletCohort] | None = None,
    cohort_id: str | None = None,
) -> Observation:
    """Calculate a point-in-time token view using both causal cutoffs.

    A trade discovered after ``arrival_cutoff`` is excluded even when its event
    timestamp is old. Ambiguous and transfer-like rows remain counted but never
    contribute to verified buying pressure.
    """

    event_limit = _parse(event_cutoff)
    arrival_limit = _parse(arrival_cutoff)
    token_lower = token.lower()
    all_records = tuple(trade for trade in trades if trade.token.lower() == token_lower)
    included = tuple(
        trade
        for trade in all_records
        if _parse(trade.as_of_time) <= event_limit and _parse(trade.retrieved_time) <= arrival_limit
    )
    verified_candidates = tuple(
        trade
        for trade in included
        if trade.classification == "genuine_swap"
        and trade.route_status == "verified"
        and trade.trade_direction in {"buy", "sell"}
        and trade.method_version == "trade-evidence.v0.2"
    )
    verified = deduplicate_trade_evidence(verified_candidates)
    verified_buys = tuple(trade for trade in verified if trade.trade_direction == "buy")
    verified_sells = tuple(trade for trade in verified if trade.trade_direction == "sell")
    verified_token_in = sum(
        int(leg.amount_atomic)
        for trade in verified_buys
        for leg in trade.receipt_legs
        if leg.asset.lower() == token_lower and leg.direction == "in"
    )
    verified_token_out = sum(
        int(leg.amount_atomic)
        for trade in verified_sells
        for leg in trade.payment_legs
        if leg.asset.lower() == token_lower and leg.direction == "out"
    )
    payment_out: dict[str, int] = {}
    quote_in: dict[str, int] = {}
    for trade in verified_buys:
        for leg in trade.payment_legs:
            if leg.direction == "out":
                payment_out[leg.asset] = payment_out.get(leg.asset, 0) + int(leg.amount_atomic)
        for refund in trade.refund_legs:
            payment_out[refund.asset] = payment_out.get(refund.asset, 0) - int(refund.amount_atomic)
    for trade in verified_sells:
        for leg in trade.receipt_legs:
            if leg.direction == "in":
                quote_in[leg.asset] = quote_in.get(leg.asset, 0) + int(leg.amount_atomic)
    cohort_state, cohort_wallet_count, cohort_missingness, cohort_lineage = _cohort_summary(
        cohorts, cohort_id, arrival_limit
    )
    missingness = list(cohort_missingness)
    if not included:
        missingness.append("no_trade_history_at_cutoff")
    if any(trade.classification == "ambiguous" for trade in included):
        missingness.append("ambiguous_activity_excluded_from_verified_flow")
    if any(trade.classification in {"transfer", "gift_or_airdrop"} for trade in included):
        missingness.append("non_swap_activity_excluded_from_verified_flow")
    if any(trade.classification == "genuine_swap" and trade not in verified_candidates for trade in included):
        missingness.append("unverified_trade_evidence_excluded_from_verified_flow")
    lineage = tuple(ref for trade in included for ref in trade.raw_event_refs) or (f"timeline:{token}:{event_cutoff}",)
    values = {
        "trade_count": len(included),
        "verified_buy_count": len(verified_buys),
        "verified_sell_count": len(verified_sells),
        "verified_token_in_atomic": str(verified_token_in),
        "verified_token_out_atomic": str(verified_token_out),
        "verified_payment_out_atomic": {asset: str(amount) for asset, amount in sorted(payment_out.items())},
        "verified_quote_in_atomic": {asset: str(amount) for asset, amount in sorted(quote_in.items())},
        "ambiguous_activity_count": sum(trade.classification == "ambiguous" for trade in included),
        "transfer_activity_count": sum(trade.classification == "transfer" for trade in included),
        "gift_or_airdrop_count": sum(trade.classification == "gift_or_airdrop" for trade in included),
        "cohort_id": cohort_id,
        "cohort_membership_state": cohort_state,
        "cohort_wallet_count": cohort_wallet_count,
    }
    latest_event = max((trade.as_of_time for trade in included), default=None)
    latest_arrival = max((trade.retrieved_time for trade in included), default=None)
    return Observation(
        subject_type="token",
        subject_id=token,
        as_of_time=event_cutoff,
        latest_included_event_time=latest_event,
        latest_included_arrival_time=latest_arrival,
        feature_version=feature_version,
        values=values,
        missingness={name: "unknown" for name in dict.fromkeys(missingness)},
        quality_state="degraded" if missingness else "healthy",
        lineage=tuple(dict.fromkeys(lineage + cohort_lineage)),
    )


def _cohort_summary(
    cohorts: Iterable[WalletCohort] | None,
    cohort_id: str | None,
    arrival_limit: datetime,
) -> tuple[str, int | None, tuple[str, ...], tuple[str, ...]]:
    if cohorts is None or cohort_id is None:
        return "unknown", None, ("wallet_cohort_unavailable",), ()
    records = tuple(
        cohort
        for cohort in cohorts
        if cohort.cohort_id == cohort_id and _parse(cohort.observed_at) <= arrival_limit
    )
    if not records:
        return "unknown", None, ("wallet_cohort_history_unknown",), (f"cohort:{cohort_id}",)
    latest_by_wallet: dict[str, WalletCohort] = {}
    for record in sorted(records, key=lambda item: item.observed_at):
        latest_by_wallet[record.wallet.lower()] = record
    members = [record for record in latest_by_wallet.values() if record.membership_state == "member"]
    states = {record.membership_state for record in latest_by_wallet.values()}
    state = "member" if members and states == {"member"} else "unknown"
    missingness = () if state == "member" else ("cohort_membership_uncertain",)
    lineage = tuple(ref for record in latest_by_wallet.values() for ref in record.raw_references)
    return state, len(members), missingness, lineage


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed
