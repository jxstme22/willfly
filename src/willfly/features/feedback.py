"""Causal prediction/outcome joins for the learning track."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from willfly.domain import OutcomeRecord, PredictionRecord


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("feedback timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class FeedbackExample:
    prediction_id: str
    target_id: str
    instrument_id: str
    market: str
    created_at: str
    label_available_at: str
    outcome_kind: str
    outcome_status: str
    net_return_bps: int | None
    eligible_for_training: bool
    reason_flags: tuple[str, ...]
    source_refs: tuple[str, ...]
    # These fields make the outcome lineage explicit at the training boundary.
    # Defaults preserve compatibility with small hand-built fixtures from the
    # earlier contract revision; persisted domain records always populate them.
    outcome_id: str = ""
    action_id: str | None = None
    horizon_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "target_id": self.target_id,
            "instrument_id": self.instrument_id,
            "market": self.market,
            "created_at": self.created_at,
            "label_available_at": self.label_available_at,
            "outcome_kind": self.outcome_kind,
            "outcome_status": self.outcome_status,
            "net_return_bps": self.net_return_bps,
            "eligible_for_training": self.eligible_for_training,
            "reason_flags": list(self.reason_flags),
            "source_refs": list(self.source_refs),
            "outcome_id": self.outcome_id,
            "action_id": self.action_id,
            "horizon_seconds": self.horizon_seconds,
        }


@dataclass(frozen=True)
class FeedbackDataset:
    as_of_time: str
    examples: tuple[FeedbackExample, ...]
    excluded: tuple[dict[str, str], ...]
    missingness: tuple[str, ...]
    lineage: tuple[str, ...]

    @property
    def eligible_examples(self) -> tuple[FeedbackExample, ...]:
        return tuple(example for example in self.examples if example.eligible_for_training)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "feedback-dataset.v0.1",
            "as_of_time": self.as_of_time,
            "examples": [example.to_dict() for example in self.examples],
            "excluded": [dict(row) for row in self.excluded],
            "missingness": list(self.missingness),
            "lineage": list(self.lineage),
            "eligible_count": len(self.eligible_examples),
        }


def build_feedback_dataset(
    predictions: Iterable[PredictionRecord],
    outcomes: Iterable[OutcomeRecord],
    *,
    as_of_time: str,
) -> FeedbackDataset:
    """Join only outcomes whose labels were available at the dataset cutoff.

    Every outcome kind is retained for audit. Only observed/censored outcomes
    with a numeric target and no temporal/self-label violation are eligible for
    training. An observed market or simulated counterfactual outcome does not
    imply that the user traded.
    """

    cutoff = _instant(as_of_time)
    prediction_by_id = {prediction.prediction_id: prediction for prediction in predictions}
    outcome_records = tuple(outcomes)
    examples: list[FeedbackExample] = []
    excluded: list[dict[str, str]] = []
    missingness: list[str] = []
    lineage: list[str] = []
    for outcome in sorted(outcome_records, key=lambda item: (item.label_available_at or "", item.outcome_id)):
        prediction = prediction_by_id.get(outcome.prediction_id)
        lineage.extend(outcome.source_refs)
        if prediction is None:
            excluded.append({"outcome_id": outcome.outcome_id, "reason": "prediction_not_found"})
            continue
        lineage.extend(prediction.source_refs)
        available = _instant(outcome.label_available_at) if outcome.label_available_at is not None else None
        if available is None or available > cutoff:
            missingness.append("outcome_label_not_yet_available")
            excluded.append({"outcome_id": outcome.outcome_id, "reason": "label_after_cutoff_or_missing"})
            continue
        created = _instant(prediction.created_at)
        observed = _instant(outcome.observed_at)
        reasons: list[str] = []
        if observed < created or available < created:
            reasons.append("outcome_before_prediction")
        if outcome.target_id != prediction.target_id:
            reasons.append("target_identity_mismatch")
        if prediction.prediction_id in outcome.source_refs:
            reasons.append("prediction_self_label_reference")
        if prediction.state in {"invalidated", "expired"}:
            reasons.append("prediction_not_active_at_creation")
        eligible = not reasons and outcome.status in {"observed", "censored"} and outcome.net_return_bps is not None
        if outcome.status in {"unresolved", "invalidated"}:
            reasons.append("outcome_unresolved_or_invalidated")
        if outcome.net_return_bps is None:
            reasons.append("numeric_target_unavailable")
        if not eligible:
            missingness.extend(reasons)
        examples.append(
            FeedbackExample(
                prediction_id=prediction.prediction_id,
                target_id=prediction.target_id,
                instrument_id=prediction.instrument.identifier,
                market=prediction.instrument.kind,
                created_at=prediction.created_at,
                label_available_at=outcome.label_available_at or outcome.observed_at,
                outcome_kind=outcome.outcome_kind,
                outcome_status=outcome.status,
                net_return_bps=outcome.net_return_bps,
                eligible_for_training=eligible,
                reason_flags=tuple(dict.fromkeys(reasons)),
                source_refs=tuple(dict.fromkeys((*prediction.source_refs, *outcome.source_refs))),
                outcome_id=outcome.outcome_id,
                action_id=outcome.action_id,
                horizon_seconds=prediction.horizon_seconds,
            )
        )
    if not prediction_by_id:
        missingness.append("no_predictions_at_cutoff")
    if not outcome_records:
        missingness.append("no_outcomes_at_cutoff")
    return FeedbackDataset(
        as_of_time=as_of_time,
        examples=tuple(examples),
        excluded=tuple(excluded),
        missingness=tuple(dict.fromkeys(missingness)),
        lineage=tuple(dict.fromkeys(lineage)) or (f"feedback:{as_of_time}",),
    )


__all__ = ["FeedbackDataset", "FeedbackExample", "build_feedback_dataset"]
