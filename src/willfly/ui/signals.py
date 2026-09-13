"""Read-only signal inbox projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from willfly.domain import PredictionRecord, SignalProposal


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("signal inbox timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class SignalInboxEntry:
    proposal_id: str
    prediction_id: str
    model_id: str
    model_version: str
    market: str
    proposed_action: str
    displayed_action: str
    display_state: str
    instrument: Mapping[str, Any]
    created_at: str
    expires_at: str
    confidence: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    manual_status: str
    reason_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "prediction_id": self.prediction_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "market": self.market,
            "proposed_action": self.proposed_action,
            "displayed_action": self.displayed_action,
            "display_state": self.display_state,
            "instrument": dict(self.instrument),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "confidence": dict(self.confidence),
            "evidence_refs": list(self.evidence_refs),
            "manual_status": self.manual_status,
            "reason_flags": list(self.reason_flags),
        }


def build_signal_inbox(
    predictions: Iterable[PredictionRecord],
    proposals: Iterable[SignalProposal],
    *,
    as_of_time: str,
    market_readiness: Mapping[str, str] | None = None,
) -> tuple[SignalInboxEntry, ...]:
    """Project model outputs into safe display actions without mutating them."""

    cutoff = _instant(as_of_time)
    prediction_by_id = {prediction.prediction_id: prediction for prediction in predictions}
    readiness = {"spot": "research_only", "lp": "research_only", **(market_readiness or {})}
    entries: list[SignalInboxEntry] = []
    for proposal in sorted(proposals, key=lambda item: (item.created_at, item.proposal_id), reverse=True):
        prediction = prediction_by_id.get(proposal.prediction_id)
        reasons: list[str] = []
        displayed_action = proposal.action
        if prediction is None:
            state = "abstain"
            displayed_action = "abstain"
            reasons.append("prediction_record_missing")
            instrument = proposal.instrument.to_dict()
            model_id = "unknown"
        else:
            state = proposal.proposal_state
            instrument = prediction.instrument.to_dict()
            model_id = prediction.model_id
            if _instant(proposal.expires_at) <= cutoff or prediction.state == "expired":
                state = "expired"
                displayed_action = "abstain"
                reasons.append("proposal_expired")
            elif proposal.proposal_state == "invalidated" or prediction.state == "invalidated":
                state = "invalidated"
                displayed_action = "abstain"
                reasons.append("proposal_invalidated")
            elif readiness.get(proposal.market) != "qualified":
                displayed_action = "abstain" if proposal.action != "hold" else "hold"
                state = "research_only"
                reasons.append(f"{proposal.market}_economic_readiness_gate_open")
            if proposal.execution_scope != "manual_only":
                state = "abstain"
                displayed_action = "abstain"
                reasons.append("execution_scope_not_manual_only")
        entries.append(
            SignalInboxEntry(
                proposal_id=proposal.proposal_id,
                prediction_id=proposal.prediction_id,
                model_id=model_id,
                model_version=proposal.model_version,
                market=proposal.market,
                proposed_action=proposal.action,
                displayed_action=displayed_action,
                display_state=state,
                instrument=instrument,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
                confidence=proposal.confidence.to_dict(),
                evidence_refs=proposal.evidence_refs,
                manual_status="not_recorded",
                reason_flags=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(entries)


__all__ = ["SignalInboxEntry", "build_signal_inbox"]
