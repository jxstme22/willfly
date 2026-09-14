from willfly.api.server import ReadOnlyStore, _route
from willfly.domain.signal_contracts import Confidence, InstrumentIdentity, ManualAction, PortfolioContext, PredictionRecord, SignalProposal
from willfly.features.action_linking import ManualActionLink
from willfly.ui.signals import build_signal_inbox


TOKEN = InstrumentIdentity(4663, "token", "0x" + "1" * 40, "native:ETH")
CONTEXT = PortfolioContext("2026-09-14T00:00:00Z", "flat", "public_only", "healthy", "100", (), ("obs:1",))


def _prediction() -> PredictionRecord:
    return PredictionRecord(
        "prediction-1", "signal-contract-v0.1.0", "spot_entry_net_return", 300, TOKEN,
        "2026-09-14T00:00:00Z", "2026-09-13T23:59:59Z", "2026-09-14T00:00:15Z",
        "male-cns-readout", "candidate-1", 100, 200, Confidence("uncalibrated_score", score=5),
        CONTEXT, ("feature:1",),
    )


def _proposal() -> SignalProposal:
    return SignalProposal(
        "proposal-1", "prediction-1", "spot_entry_net_return", 300, "spot", "enter", None, TOKEN,
        "2026-09-14T00:00:00Z", "2026-09-14T00:00:15Z", "candidate-1",
        Confidence("uncalibrated_score", score=5), CONTEXT, ("prediction:1",),
    )


def test_inbox_abstains_research_only_and_expires_stale_proposals() -> None:
    research = build_signal_inbox([_prediction()], [_proposal()], as_of_time="2026-09-14T00:00:10Z")
    assert research[0].proposed_action == "enter"
    assert research[0].displayed_action == "abstain"
    assert research[0].display_state == "research_only"
    assert "spot_economic_readiness_gate_open" in research[0].reason_flags
    expired = build_signal_inbox([_prediction()], [_proposal()], as_of_time="2026-09-14T00:00:20Z", market_readiness={"spot": "qualified"})
    assert expired[0].displayed_action == "abstain"
    assert expired[0].display_state == "expired"


def test_read_only_api_exposes_signals_positions_and_training_state() -> None:
    store = ReadOnlyStore(
        predictions=(_prediction(),),
        proposals=(_proposal(),),
        signal_as_of_time="2026-09-14T00:00:10Z",
        training_state={"status": "waiting", "reason": "insufficient_qualified_train_examples"},
    )
    signals, status = _route(store, "/signals")
    assert status == 200 and signals["total"] == 1
    assert signals["items"][0]["displayed_action"] == "abstain"
    health, status = _route(store, "/health")
    assert status == 200
    assert health["details"]["signal_monitor_state"] == "current_research_only"
    assert health["details"]["current_signal_count"] == 1
    expired_store = ReadOnlyStore(
        predictions=(_prediction(),),
        proposals=(_proposal(),),
        signal_as_of_time="2026-09-14T00:00:20Z",
        market_readiness={"spot": "qualified"},
    )
    expired_health, status = _route(expired_store, "/health")
    assert status == 200
    assert expired_health["details"]["signal_monitor_state"] == "historical_expired"
    assert expired_health["details"]["expired_signal_count"] == 1
    positions, status = _route(store, "/positions")
    assert status == 200 and positions["items"] == []
    training, status = _route(store, "/training")
    assert status == 200 and training["status"] == "waiting"
    models, status = _route(store, "/models")
    assert status == 200 and models["status"] == "unknown"


def test_read_only_api_exposes_attached_model_registry_state() -> None:
    store = ReadOnlyStore(
        model_state={"active_version": "candidate-v2", "known_versions": ["active-v1", "candidate-v2"]}
    )
    models, status = _route(store, "/models")
    assert status == 200
    assert models["active_version"] == "candidate-v2"


def test_signal_api_exposes_manual_action_link_status() -> None:
    action = ManualAction(
        "action-1",
        "proposal-1",
        TOKEN,
        "spot",
        "enter",
        None,
        "2026-09-14T00:00:03Z",
        "2026-09-14T00:00:04Z",
        "reported",
        None,
        None,
        True,
        ("manual:1",),
    )
    link = ManualActionLink("action-1", "matched", "activity-1", ("exact_transaction_match",), ("activity:1",))
    store = ReadOnlyStore(
        predictions=(_prediction(),),
        proposals=(_proposal(),),
        signal_as_of_time="2026-09-14T00:00:10Z",
        manual_actions=(action,),
        action_links=(link,),
    )
    signals, status = _route(store, "/signals")
    assert status == 200
    assert signals["items"][0]["manual_status"] == "matched"
