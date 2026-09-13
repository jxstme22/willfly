import json
from pathlib import Path

import pytest

from willfly.domain.signal_contracts import (
    Confidence,
    InstrumentIdentity,
    ManualAction,
    OutcomeRecord,
    PortfolioContext,
    PredictionRecord,
    SignalProposal,
    default_signal_contract,
)


TOKEN = InstrumentIdentity(4663, "token", "0x" + "1" * 40, "native:ETH")
POOL = InstrumentIdentity(4663, "pool", "0x" + "2" * 64, "native:ETH", "uniswap_v4")
CONTEXT = PortfolioContext(
    "2026-09-14T00:00:00Z",
    "flat",
    "public_only",
    "healthy",
    "100000",
    (),
    ("observation:1",),
)


def _prediction(target_id: str = "spot_entry_net_return", instrument=TOKEN) -> PredictionRecord:
    return PredictionRecord(
        "prediction-1",
        "signal-contract-v0.1.0",
        target_id,
        300,
        instrument,
        "2026-09-14T00:00:00Z",
        "2026-09-13T23:59:59Z",
        "2026-09-14T00:00:15Z",
        "male-cns-readout",
        "candidate-1",
        125,
        250,
        Confidence("uncalibrated_score", score=7),
        CONTEXT,
        ("feature:1",),
    )


def test_default_contract_freezes_targets_horizons_and_manual_scope():
    contract = default_signal_contract()
    assert contract.horizons_seconds == (60, 300, 900)
    assert contract.primary_horizon_seconds == 300
    assert {target.target_id for target in contract.targets} == {
        "spot_entry_net_return", "spot_hold_net_return", "spot_exit_net_return",
        "lp_entry_net_return", "lp_hold_net_return", "lp_exit_net_return",
    }
    assert contract.execution_scope == "manual_only"
    assert contract.signing_enabled is False
    assert contract.funding_enabled is False


def test_checked_in_signal_config_matches_executable_contract():
    payload = json.loads(
        (Path(__file__).parents[1] / "configs/experiments/signal-contracts-v0.1.json").read_text()
    )
    assert default_signal_contract().to_dict() == payload


def test_prediction_and_proposal_round_trip_with_explicit_expiry():
    contract = default_signal_contract()
    prediction = _prediction()
    contract.validate_prediction(prediction)
    assert PredictionRecord.from_dict(prediction.to_dict()) == prediction
    proposal = SignalProposal(
        "proposal-1", prediction.prediction_id, prediction.target_id, 300, "spot", "enter", None,
        TOKEN, prediction.created_at, "2026-09-14T00:00:15Z", prediction.model_version,
        prediction.confidence, CONTEXT, ("prediction:1",),
    )
    contract.validate_proposal(proposal)
    assert SignalProposal.from_dict(proposal.to_dict()) == proposal


def test_lp_exit_requires_pool_and_explicit_liquidity_operation():
    contract = default_signal_contract()
    prediction = _prediction("lp_exit_net_return", POOL)
    contract.validate_prediction(prediction)
    proposal = SignalProposal(
        "proposal-lp", prediction.prediction_id, prediction.target_id, 300, "lp", "exit", "remove_liquidity",
        POOL, prediction.created_at, "2026-09-14T00:00:15Z", prediction.model_version,
        prediction.confidence, CONTEXT, ("prediction:lp",),
    )
    contract.validate_proposal(proposal)
    with pytest.raises(ValueError, match="pool instrument"):
        SignalProposal(
            proposal.proposal_id, proposal.prediction_id, proposal.target_id, proposal.horizon_seconds,
            proposal.market, proposal.action, proposal.exit_kind, TOKEN, proposal.created_at,
            proposal.expires_at, proposal.model_version, proposal.confidence,
            proposal.portfolio_context, proposal.evidence_refs,
        )


def test_confidence_never_coerces_an_ordinal_score_to_probability():
    with pytest.raises(ValueError, match="cannot claim a probability"):
        Confidence("uncalibrated_score", score=7, probability_bps=7000)
    with pytest.raises(ValueError, match="calibration reference"):
        Confidence("calibrated_probability", probability_bps=7000)
    assert Confidence("unavailable").to_dict()["probability_bps"] is None


def test_manual_actions_and_outcomes_keep_actual_and_simulated_separate():
    action = ManualAction(
        "action-1", "proposal-1", TOKEN, "spot", "enter", None,
        "2026-09-14T00:00:05Z", "2026-09-14T00:00:06Z", "matched",
        "0x" + "a" * 64, "wallet:public-1", False, ("receipt:1",),
    )
    assert ManualAction.from_dict(action.to_dict()) == action
    actual = OutcomeRecord(
        "outcome-actual", "prediction-1", "spot_entry_net_return", "actual_manual", "observed",
        "2026-09-14T00:05:00Z", "2026-09-14T00:05:01Z", 80, ("receipt:1",), action.action_id,
    )
    simulated = OutcomeRecord(
        "outcome-sim", "prediction-1", "spot_entry_net_return", "simulated_counterfactual", "observed",
        "2026-09-14T00:05:00Z", "2026-09-14T00:05:01Z", 100, ("market:1",),
    )
    assert OutcomeRecord.from_dict(actual.to_dict()) == actual
    assert simulated.action_id is None
    with pytest.raises(ValueError, match="cannot claim a manual action"):
        OutcomeRecord(
            simulated.outcome_id, simulated.prediction_id, simulated.target_id,
            simulated.outcome_kind, simulated.status, simulated.observed_at,
            simulated.label_available_at, simulated.net_return_bps, simulated.source_refs,
            action.action_id,
        )
