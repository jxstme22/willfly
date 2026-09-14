"""Checkpointable fixed-connectome training experiments and matched controls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from willfly.models.connectome.graph import SparseGraph, graph_hash
from willfly.models.readout import FrozenReadout, ReadoutRow
from willfly.models.reservoir import SparseReservoir
from willfly.models.conventional import FeatureRow, LinearBaseline
from willfly.features.feedback import FeedbackDataset


@dataclass(frozen=True)
class TrainingSample:
    sample_id: str
    episode_id: str
    observed_at: str
    inputs: Mapping[str, float]
    target_bps: int
    partition: str
    source_refs: tuple[str, ...]
    outcome_id: str | None = None
    outcome_kind: str | None = None
    action_id: str | None = None

    def __post_init__(self) -> None:
        if not self.sample_id or not self.episode_id or not self.observed_at or not self.source_refs:
            raise ValueError("training samples require identity, time and source references")
        if self.partition not in {"train", "validation", "test"}:
            raise ValueError("training sample partition must be train, validation or test")
        if not isinstance(self.target_bps, int) or isinstance(self.target_bps, bool):
            raise ValueError("training target must be an integer basis-point value")
        if not self.inputs or any(not isinstance(key, str) or not key for key in self.inputs):
            raise ValueError("training inputs must be a non-empty node mapping")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in self.inputs.values()):
            raise ValueError("training inputs must be finite numbers")


@dataclass(frozen=True)
class FeedbackTrainingBuild:
    samples: tuple[TrainingSample, ...]
    excluded: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": [
                {
                    "sample_id": sample.sample_id,
                    "episode_id": sample.episode_id,
                    "observed_at": sample.observed_at,
                    "inputs": dict(sample.inputs),
                    "target_bps": sample.target_bps,
                    "partition": sample.partition,
                    "source_refs": list(sample.source_refs),
                    "outcome_id": sample.outcome_id,
                    "outcome_kind": sample.outcome_kind,
                    "action_id": sample.action_id,
                }
                for sample in self.samples
            ],
            "excluded": [dict(item) for item in self.excluded],
        }


def build_training_samples_from_feedback(
    dataset: FeedbackDataset,
    inputs_by_prediction: Mapping[str, Mapping[str, float]],
    *,
    partitions_by_prediction: Mapping[str, str],
) -> FeedbackTrainingBuild:
    """Adapt eligible causal labels without inventing features or splits."""

    samples: list[TrainingSample] = []
    excluded: list[dict[str, str]] = []
    eligible = tuple(sorted(dataset.eligible_examples, key=lambda item: (item.created_at, item.prediction_id, item.outcome_id)))
    by_prediction: dict[str, list[Any]] = {}
    for example in eligible:
        by_prediction.setdefault(example.prediction_id, []).append(example)
    ambiguous_predictions = {
        prediction_id
        for prediction_id, examples in by_prediction.items()
        if len({example.outcome_id or example.prediction_id for example in examples}) > 1
    }
    for prediction_id in sorted(ambiguous_predictions):
        for example in by_prediction[prediction_id]:
            excluded.append(
                {
                    "prediction_id": example.prediction_id,
                    "outcome_id": example.outcome_id or example.prediction_id,
                    "reason": "multiple_eligible_outcomes_for_prediction",
                }
            )
    for example in eligible:
        if example.prediction_id in ambiguous_predictions:
            continue
        inputs = inputs_by_prediction.get(example.prediction_id)
        if inputs is None:
            excluded.append({"prediction_id": example.prediction_id, "reason": "feature_inputs_missing"})
            continue
        partition = partitions_by_prediction.get(example.prediction_id)
        if partition is None:
            excluded.append({"prediction_id": example.prediction_id, "reason": "partition_assignment_missing"})
            continue
        if example.net_return_bps is None:  # Defensive guard for custom dataset implementations.
            excluded.append({"prediction_id": example.prediction_id, "reason": "numeric_target_unavailable"})
            continue
        samples.append(
            TrainingSample(
                sample_id=f"feedback:{example.prediction_id}",
                episode_id=f"{example.market}:{example.instrument_id}",
                observed_at=example.created_at,
                inputs=inputs,
                target_bps=example.net_return_bps,
                partition=partition,
                source_refs=example.source_refs,
                outcome_id=example.outcome_id or example.prediction_id,
                outcome_kind=example.outcome_kind,
                action_id=example.action_id,
            )
        )
    return FeedbackTrainingBuild(tuple(samples), tuple(excluded))


@dataclass(frozen=True)
class ExperimentConfig:
    run_id: str
    decay: float = 0.9
    input_scale: float = 1.0
    l2: float = 1.0
    seed: int = 7
    minimum_train_examples: int = 4

    def __post_init__(self) -> None:
        if not self.run_id or not 0 <= self.decay < 1 or self.input_scale < 0 or self.l2 < 0:
            raise ValueError("connectome experiment controls are invalid")
        if self.minimum_train_examples <= 0:
            raise ValueError("minimum_train_examples must be positive")

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ModelMetric:
    model_name: str
    graph_hash: str | None
    train_count: int
    heldout_count: int
    mae_bps: float | None
    predictions: tuple[tuple[str, float, int, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "graph_hash": self.graph_hash,
            "train_count": self.train_count,
            "heldout_count": self.heldout_count,
            "mae_bps": self.mae_bps,
            "predictions": [list(item) for item in self.predictions],
        }


@dataclass(frozen=True)
class ExperimentResult:
    run_id: str
    status: str
    graph_hash: str
    train_count: int
    heldout_count: int
    models: tuple[ModelMetric, ...]
    resource_seconds: float
    checkpoint_path: str | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"completed", "waiting"}:
            raise ValueError("unsupported connectome experiment status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "connectome-experiment.v0.1",
            "run_id": self.run_id,
            "status": self.status,
            "graph_hash": self.graph_hash,
            "train_count": self.train_count,
            "heldout_count": self.heldout_count,
            "models": [model.to_dict() for model in self.models],
            "resource_seconds": self.resource_seconds,
            "checkpoint_path": self.checkpoint_path,
            "reasons": list(self.reasons),
        }


def run_connectome_experiment(
    graph: SparseGraph,
    samples: Sequence[TrainingSample],
    *,
    config: ExperimentConfig,
    checkpoint_path: str | Path | None = None,
    resume: bool = True,
) -> ExperimentResult:
    """Train fixed-graph readouts and matched controls from qualified samples.

    The recurrent graph is never changed by readout fitting. Checkpoints store
    encoded state rows and are bound to graph/config/sample hashes, so a changed
    dataset cannot silently resume an old run.
    """

    started = time.perf_counter()
    records = tuple(sorted(samples, key=lambda item: (item.episode_id, item.observed_at, item.sample_id)))
    train = tuple(item for item in records if item.partition == "train")
    heldout = tuple(item for item in records if item.partition in {"validation", "test"})
    current_graph_hash = graph_hash(graph)
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else None
    reasons: list[str] = []
    if len(train) < config.minimum_train_examples:
        reasons.append("insufficient_qualified_train_examples")
    if not heldout:
        reasons.append("no_heldout_examples")
    if reasons:
        return ExperimentResult(
            config.run_id,
            "waiting",
            current_graph_hash,
            len(train),
            len(heldout),
            (),
            time.perf_counter() - started,
            str(checkpoint) if checkpoint else None,
            tuple(reasons),
        )
    sample_hash = _hash_samples(records)
    config_hash = _hash_payload(config.to_dict())
    model_graphs = {
        "fly": graph,
        "shuffled_wiring": graph.shuffled_control(config.seed),
        "random_weights": graph.random_weight_control(config.seed),
    }
    state_rows: dict[str, dict[str, tuple[float, ...]]] = {}
    if checkpoint is not None and resume and checkpoint.exists():
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "connectome-checkpoint.v0.1":
            raise ValueError("unsupported connectome checkpoint schema")
        if payload.get("graph_hash") != current_graph_hash or payload.get("sample_hash") != sample_hash or payload.get("config_hash") != config_hash:
            raise ValueError("connectome checkpoint identity does not match this experiment")
        raw_states = payload.get("state_rows", {})
        if not isinstance(raw_states, dict):
            raise ValueError("connectome checkpoint state rows are malformed")
        state_rows = {
            name: {sample_id: tuple(float(value) for value in values) for sample_id, values in rows.items()}
            for name, rows in raw_states.items()
            if isinstance(rows, dict)
        }
    for model_name, model_graph in model_graphs.items():
        if model_name in state_rows and set(state_rows[model_name]) == {sample.sample_id for sample in records}:
            continue
        reservoir = SparseReservoir(graph=model_graph, decay=config.decay, input_scale=config.input_scale)
        encoded: dict[str, tuple[float, ...]] = {}
        current_episode: str | None = None
        state = None
        for sample in records:
            if sample.episode_id != current_episode:
                state = reservoir.reset(sample.episode_id)
                current_episode = sample.episode_id
            assert state is not None
            state = reservoir.step(state, sample.inputs)
            encoded[sample.sample_id] = state.values
        state_rows[model_name] = encoded
    if checkpoint is not None:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(
            json.dumps(
                {
                    "schema_version": "connectome-checkpoint.v0.1",
                    "run_id": config.run_id,
                    "graph_hash": current_graph_hash,
                    "sample_hash": sample_hash,
                    "config_hash": config_hash,
                    "state_rows": {name: {sample_id: list(values) for sample_id, values in rows.items()} for name, rows in state_rows.items()},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    metrics: list[ModelMetric] = []
    for model_name, model_graph in model_graphs.items():
        train_rows = [ReadoutRow(state_rows[model_name][sample.sample_id], float(sample.target_bps)) for sample in train]
        readout = FrozenReadout.fit(train_rows, graph_hash_value=graph_hash(model_graph), l2=config.l2)
        predictions = tuple(
            (
                sample.sample_id,
                readout.predict(state_rows[model_name][sample.sample_id]),
                sample.target_bps,
                sample.partition,
            )
            for sample in heldout
        )
        metrics.append(_metric(model_name, graph_hash(model_graph), len(train), predictions))
    # Matched non-recurrent controls use the exact same partitions and inputs.
    feature_names = tuple(sorted({name for sample in records for name in sample.inputs}))
    no_state_rows = tuple(
        FeatureRow(sample.sample_id, sample.episode_id, tuple(float(sample.inputs.get(name, 0.0)) for name in feature_names), sample.target_bps)
        for sample in records
    )
    train_ids = {sample.sample_id for sample in train}
    no_state = LinearBaseline.fit([row for row in no_state_rows if row.row_id in train_ids], l2=config.l2, seed=config.seed)
    # Ordinary is a one-dimensional mean-input control; no-state retains the
    # full input vector. Both are feature-only controls with no graph wiring.
    ordinary_rows = [
        FeatureRow(sample.sample_id, sample.episode_id, (sum(sample.inputs.values()) / len(sample.inputs),), sample.target_bps)
        for sample in records
    ]
    ordinary = LinearBaseline.fit([row for row in ordinary_rows if row.row_id in train_ids], l2=config.l2, seed=config.seed)
    no_state_predictions = tuple(
        (
            sample.sample_id,
            no_state.predict(tuple(float(sample.inputs.get(name, 0.0)) for name in feature_names)),
            sample.target_bps,
            sample.partition,
        )
        for sample in heldout
    )
    ordinary_predictions = tuple(
        (
            sample.sample_id,
            ordinary.predict((sum(sample.inputs.values()) / len(sample.inputs),)),
            sample.target_bps,
            sample.partition,
        )
        for sample in heldout
    )
    metrics.extend(
        (
            _metric("no_state", None, len(train), no_state_predictions),
            _metric("ordinary", None, len(train), ordinary_predictions),
        )
    )
    return ExperimentResult(
        config.run_id,
        "completed",
        current_graph_hash,
        len(train),
        len(heldout),
        tuple(metrics),
        time.perf_counter() - started,
        str(checkpoint) if checkpoint else None,
        (),
    )


def _metric(
    model_name: str,
    model_hash: str | None,
    train_count: int,
    predictions: tuple[tuple[str, float, int, str], ...],
) -> ModelMetric:
    mae = sum(abs(predicted - target) for _, predicted, target, _partition in predictions) / len(predictions) if predictions else None
    return ModelMetric(model_name, model_hash, train_count, len(predictions), mae, predictions)


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _hash_samples(samples: Sequence[TrainingSample]) -> str:
    return _hash_payload(
        [
            {
                "sample_id": sample.sample_id,
                "episode_id": sample.episode_id,
                "observed_at": sample.observed_at,
                "inputs": dict(sample.inputs),
                "target_bps": sample.target_bps,
                "partition": sample.partition,
                "source_refs": list(sample.source_refs),
            }
            for sample in samples
        ]
    )


__all__ = [
    "ExperimentConfig",
    "ExperimentResult",
    "FeedbackTrainingBuild",
    "ModelMetric",
    "TrainingSample",
    "build_training_samples_from_feedback",
    "run_connectome_experiment",
]
