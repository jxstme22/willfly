"""Bridge completed connectome experiment results into typed model outputs."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Iterable, Mapping

from willfly.domain import PredictionRecord


def build_model_output_bundle(
    experiment: Mapping[str, Any],
    templates: Iterable[PredictionRecord],
    *,
    model_name: str,
    model_id: str,
    model_version: str,
    run_ref: str,
    as_of_time: str,
    actions_by_prediction: Mapping[str, str] | None = None,
    exit_kinds_by_prediction: Mapping[str, str] | None = None,
    source_hash: str | None = None,
    template_hash: str | None = None,
) -> dict[str, Any]:
    """Create a signal-builder input from one recorded experiment result.

    The experiment result is already a serialized, hash-bound output of the
    laboratory. This adapter selects one named model metric and carries its
    sample IDs and predictions forward without deriving actions, confidence,
    calibration, or economic readiness. An incomplete experiment produces an
    empty output list and a truthful waiting training state.
    """

    if not isinstance(experiment, Mapping):
        raise ValueError("experiment result must be an object")
    if experiment.get("schema_version") != "connectome-experiment.v0.1":
        raise ValueError("experiment result schema version is unsupported")
    for value, field in (
        (model_name, "model_name"),
        (model_id, "model_id"),
        (model_version, "model_version"),
        (run_ref, "run_ref"),
        (as_of_time, "as_of_time"),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} is required")
    parsed = datetime.fromisoformat(as_of_time.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("as_of_time must include a timezone")
    status = experiment.get("status")
    if status not in {"completed", "waiting"}:
        raise ValueError("experiment result status is unsupported")
    raw_templates = tuple(templates)
    if any(not isinstance(template, PredictionRecord) for template in raw_templates):
        raise TypeError("templates must be PredictionRecord values")
    raw_models = experiment.get("models", [])
    if not isinstance(raw_models, list) or any(not isinstance(item, Mapping) for item in raw_models):
        raise ValueError("experiment models must be an array of objects")
    selected = next((item for item in raw_models if item.get("model_name") == model_name), None)
    outputs: list[dict[str, Any]] = []
    if status == "completed":
        if selected is None:
            raise ValueError(f"experiment model metric not found: {model_name}")
        raw_predictions = selected.get("predictions")
        if not isinstance(raw_predictions, list):
            raise ValueError("experiment model predictions must be an array")
        seen: set[str] = set()
        excluded_output_count = 0
        for row in raw_predictions:
            if not isinstance(row, list) or len(row) != 4:
                raise ValueError("experiment model prediction rows must be [sample_id, prediction, target, partition]")
            sample_id, predicted_bps, _target_bps, partition = row
            if not isinstance(sample_id, str) or not sample_id:
                raise ValueError("experiment model prediction sample_id is required")
            if partition not in {"validation", "test"}:
                raise ValueError("experiment model prediction partition is invalid")
            if sample_id in seen:
                raise ValueError("experiment model prediction sample IDs must be unique")
            if isinstance(predicted_bps, bool) or not isinstance(predicted_bps, (int, float)) or not math.isfinite(float(predicted_bps)):
                raise ValueError("experiment model prediction must be finite numeric")
            seen.add(sample_id)
            if partition == "test":
                excluded_output_count += 1
                continue
            outputs.append({"sample_id": sample_id, "predicted_bps": predicted_bps})
    else:
        excluded_output_count = 0

    training_state: dict[str, Any] = {
        "status": status,
        "run_id": experiment.get("run_id"),
        "model_name": model_name,
        "graph_hash": experiment.get("graph_hash"),
        "train_count": experiment.get("train_count"),
        "heldout_count": experiment.get("heldout_count"),
        "resource_seconds": experiment.get("resource_seconds"),
        "checkpoint_path": experiment.get("checkpoint_path"),
        "reasons": list(experiment.get("reasons", [])),
        "excluded_final_test_output_count": excluded_output_count,
    }
    if source_hash is not None:
        if not isinstance(source_hash, str) or not source_hash:
            raise ValueError("source_hash must be non-empty text")
        training_state["experiment_report_hash"] = source_hash
    if template_hash is not None:
        if not isinstance(template_hash, str) or not template_hash:
            raise ValueError("template_hash must be non-empty text")
        training_state["template_bundle_hash"] = template_hash
    provenance = experiment.get("provenance")
    if provenance is not None:
        if not isinstance(provenance, Mapping):
            raise ValueError("experiment provenance must be an object")
        training_state["provenance"] = dict(provenance)
    return {
        "schema_version": "willfly.model-output-bundle.v0.1",
        "as_of_time": as_of_time,
        "model_id": model_id,
        "model_version": model_version,
        "run_ref": run_ref,
        "templates": [template.to_dict() for template in raw_templates],
        "outputs": outputs,
        "actions_by_prediction": dict(actions_by_prediction or {}),
        "exit_kinds_by_prediction": dict(exit_kinds_by_prediction or {}),
        "market_readiness": {"spot": "research_only", "lp": "research_only"},
        "training_state": training_state,
    }


__all__ = ["build_model_output_bundle"]
