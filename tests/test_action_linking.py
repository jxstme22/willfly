from willfly.domain import ManualAction, PaymentLeg, TradeEvidence
from willfly.domain.signal_contracts import InstrumentIdentity
from willfly.domain.wallets import activity_from_trade
from willfly.features.action_linking import link_manual_actions
from willfly.api.server import ReadOnlyStore, _route


TOKEN = "0x1111111111111111111111111111111111111111"
WALLET = "0x2222222222222222222222222222222222222222"
QUOTE = "0x3333333333333333333333333333333333333333"
TX = "0x" + "44" * 32


def _activity():
    trade = TradeEvidence(
        TX, WALLET, TOKEN, "genuine_swap",
        (PaymentLeg(QUOTE, "10", "out", WALLET, QUOTE, "pay"),),
        (PaymentLeg(TOKEN, "100", "in", QUOTE, WALLET, "receive"),),
        QUOTE, None, False, None, (), "trade-evidence.v0.2",
        "2026-09-14T00:00:01Z", "2026-09-14T00:00:02Z", ("raw:trade",), "verified", "buy", (),
    )
    return activity_from_trade(trade, canonical_status="canonical")


def _action(tx_hash: str | None = TX) -> ManualAction:
    return ManualAction(
        "action-1", "proposal-1", InstrumentIdentity(4663, "token", TOKEN, QUOTE), "spot", "enter", None,
        "2026-09-14T00:00:03Z", "2026-09-14T00:00:04Z", "reported", tx_hash, WALLET, True, ("manual:1",),
    )


def test_exact_transaction_link_preserves_manual_override() -> None:
    link = link_manual_actions([_action()], [_activity()])[0]
    assert link.status == "matched"
    assert link.activity_id is not None
    assert "exact_transaction_match" in link.reason_flags


def test_action_link_is_exposed_without_turning_it_into_execution() -> None:
    action = _action()
    store = ReadOnlyStore(manual_actions=(action,), action_links=link_manual_actions([action], [_activity()]))
    payload, status = _route(store, "/actions")
    assert status == 200
    assert payload["items"][0]["link"]["status"] == "matched"
    assert payload["items"][0]["action"]["execution_scope"] == "manual_only"


def test_missing_hash_is_ambiguous_or_pending_and_never_matches_amount_only() -> None:
    activity = _activity()
    action = _action(None)
    pending = link_manual_actions([action], [activity])[0]
    assert pending.status == "matched"
    unrelated = _activity()
    action_late = _action(None)
    action_late = ManualAction(
        action_late.action_id, action_late.proposal_id, action_late.instrument, action_late.market, action_late.action,
        action_late.exit_kind, "2026-09-14T01:00:00Z", action_late.recorded_at, action_late.execution_status,
        action_late.transaction_hash, action_late.wallet_ref, action_late.user_override, action_late.source_refs,
    )
    assert link_manual_actions([action_late], [unrelated])[0].status == "pending"
