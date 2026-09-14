"""Turn explicit model outputs into versioned research-only signal records."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

from willfly.domain import Confidence, PredictionRecord, SignalProposal, default_signal_contract


@dataclass(frozen=True)
class SignalBuildResult:
    predictions: tuple[PredictionRecord, ...]
    proposals: tuple[SignalProposal, ...]
    excluded: tuple[dict[str, str], ...]

    def to_bundle(
        self,
        *,
        as_of_time: str,
        market_readiness: Mapping[str, str] | None = None,
        training_state: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "willfly.signal-snapshot.v0.1",
            "as_of_time": as_of_time,
            "predictions": [prediction.to_dict() for prediction in self.predictions],
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "market_readiness": dict(market_readiness or {"spot": "research_only", "lp": "research_only"}),
            "training_state": None if training_state is None else dict(training_state),
            "excluded": [dict(item) for item in self.excluded],
        }


def build_research_signals(
    templates: Iterable[PredictionRecord],
    model_outputs: Iterable[tuple[str, float]],
    *,
    model_id: str,
    model_version: str,
    run_ref: str,
    actions_by_prediction: Mapping[str, str] | None = None,
    exit_kinds_by_prediction: Mapping[str, str] | None = None,
) -> SignalBuildResult:
    """Build uncalibrated versioned predictions and manually gated proposals.

    ``model_outputs`` uses either a template prediction ID or the feedback
    adapter's ``feedback:<prediction_id>`` sample ID. The function never
    derives an action from a numeric score: callers must provide the action
    mapping explicitly, and the frozen signal contract validates it.
    """

    if not model_id or not model_version or not run_ref:
        raise ValueError("model_id, model_version and run_ref are required")
    contract = default_signal_contract()
    template_records = tuple(templates)
    template_by_id = {prediction.prediction_id: prediction for prediction in template_records}
    if len(template_by_id) != len(template_records):
        raise ValueError("template prediction IDs must be unique")
    actions = actions_by_prediction or {}
    exit_kinds = exit_kinds_by_prediction or {}
    confidence = Confidence("unavailable")
    predictions: list[PredictionRecord] = []
    proposals: list[SignalProposal] = []
    excluded: list[dict[str, str]] = []
    seen_templates: set[str] = set()
    for sample_id, predicted_bps in model_outputs:
        template_id = sample_id.removeprefix("feedback:")
        template = template_by_id.get(template_id)
        if template is None:
            excluded.append({"sample_id": sample_id, "reason": "prediction_template_missing"})
            continue
        if template_id in seen_templates:
            excluded.append({"sample_id": sample_id, "reason": "duplicate_model_output"})
            continue
        seen_templates.add(template_id)
        if isinstance(predicted_bps, bool) or not isinstance(predicted_bps, (int, float)) or not math.isfinite(float(predicted_bps)):
            excluded.append({"sample_id": sample_id, "reason": "model_output_non_finite"})
            continue
        try:
            contract.validate_prediction(template)
        except ValueError:
            excluded.append({"sample_id": sample_id, "reason": "prediction_template_contract_invalid"})
            continue
        prediction_id = f"{model_version}:{template.prediction_id}"
        evidence_refs = tuple(dict.fromkeys((*template.source_refs, run_ref)))
        prediction = PredictionRecord(
            prediction_id=prediction_id,
            contract_version=template.contract_version,
            target_id=template.target_id,
            horizon_seconds=template.horizon_seconds,
            instrument=template.instrument,
            created_at=template.created_at,
            evidence_cutoff=template.evidence_cutoff,
            expires_at=template.expires_at,
            model_id=model_id,
            model_version=model_version,
            expected_value_bps=int(round(float(predicted_bps))),
            uncertainty_bps=None,
            confidence=confidence,
            portfolio_context=template.portfolio_context,
            source_refs=evidence_refs,
            state="research_prediction",
        )
        predictions.append(prediction)
        action = actions.get(template_id)
        if action is None:
            excluded.append({"sample_id": sample_id, "reason": "proposal_action_mapping_missing"})
            continue
        exit_kind = exit_kinds.get(template_id)
        market = "spot" if template.instrument.kind == "token" else "lp"
        try:
            proposal = SignalProposal(
                proposal_id=f"{model_version}:proposal:{template.prediction_id}",
                prediction_id=prediction_id,
                target_id=template.target_id,
                horizon_seconds=template.horizon_seconds,
                market=market,
                action=action,
                exit_kind=exit_kind,
                instrument=template.instrument,
                created_at=template.created_at,
                expires_at=template.expires_at,
                model_version=model_version,
                confidence=confidence,
                portfolio_context=template.portfolio_context,
                evidence_refs=evidence_refs,
                proposal_state="research_only",
                execution_scope="manual_only",
            )
            contract.validate_proposal(proposal)
        except ValueError:
            excluded.append({"sample_id": sample_id, "reason": "proposal_contract_invalid"})
            continue
        proposals.append(proposal)
    return SignalBuildResult(tuple(predictions), tuple(proposals), tuple(excluded))


__all__ = ["SignalBuildResult", "build_research_signals"]
