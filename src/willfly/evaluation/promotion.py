"""Reproducible candidate evaluation and guarded model-version registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PredictionPoint:
    prediction_id: str
    model_version: str
    market: str
    window_id: str
    split: str
    observed_at: str
    predicted_bps: float
    target_bps: int
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (self.prediction_id, self.model_version, self.market, self.window_id, self.observed_at)):
            raise ValueError("prediction point identity is required")
        if self.market not in {"spot", "lp"}:
            raise ValueError("prediction point market must be spot or lp")
        if self.split not in {"forward", "final_test"}:
            raise ValueError("prediction point split must be forward or final_test")
        parsed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("prediction point observed_at must include a timezone")
        if not math.isfinite(self.predicted_bps) or not isinstance(self.target_bps, int) or isinstance(self.target_bps, bool):
            raise ValueError("prediction point values are invalid")
        if not self.source_refs:
            raise ValueError("prediction point requires source_refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "model_version": self.model_version,
            "market": self.market,
            "window_id": self.window_id,
            "split": self.split,
            "observed_at": self.observed_at,
            "predicted_bps": self.predicted_bps,
            "target_bps": self.target_bps,
            "source_refs": list(self.source_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PredictionPoint":
        if not isinstance(data, Mapping):
            raise ValueError("prediction point must be an object")
        identity_fields = ("prediction_id", "model_version", "market", "window_id", "split", "observed_at")
        if any(not isinstance(data.get(field), str) or not data[field] for field in identity_fields):
            raise ValueError("prediction point identity fields are invalid")
        source_refs = data.get("source_refs")
        if not isinstance(source_refs, list) or any(not isinstance(value, str) or not value for value in source_refs):
            raise ValueError("prediction point source_refs must be a list")
        predicted_bps = data.get("predicted_bps")
        target_bps = data.get("target_bps")
        if isinstance(predicted_bps, bool) or not isinstance(predicted_bps, (int, float)):
            raise ValueError("prediction point predicted_bps must be numeric")
        if isinstance(target_bps, bool) or not isinstance(target_bps, int):
            raise ValueError("prediction point target_bps must be an integer")
        return cls(
            data["prediction_id"],
            data["model_version"],
            data["market"],
            data["window_id"],
            data["split"],
            data["observed_at"],
            predicted_bps,
            target_bps,
            tuple(str(value) for value in source_refs),
        )


@dataclass(frozen=True)
class WindowScore:
    model_version: str
    market: str
    window_id: str
    split: str
    count: int
    mae_bps: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_version: str
    active_version: str
    evaluated_at: str
    dataset_hash: str
    final_test_hash: str
    forward_scores: tuple[WindowScore, ...]
    final_test_scores: tuple[WindowScore, ...]
    decision: str
    reasons: tuple[str, ...]
    active_forward_scores: tuple[WindowScore, ...] = ()
    active_final_test_scores: tuple[WindowScore, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in {"qualified", "inconclusive", "rejected"}:
            raise ValueError("unsupported candidate evaluation decision")
        parsed = datetime.fromisoformat(self.evaluated_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("evaluated_at must include a timezone")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "candidate-evaluation.v0.1",
            "candidate_version": self.candidate_version,
            "active_version": self.active_version,
            "evaluated_at": self.evaluated_at,
            "dataset_hash": self.dataset_hash,
            "final_test_hash": self.final_test_hash,
            "forward_scores": [score.to_dict() for score in self.forward_scores],
            "final_test_scores": [score.to_dict() for score in self.final_test_scores],
            "active_forward_scores": [score.to_dict() for score in self.active_forward_scores],
            "active_final_test_scores": [score.to_dict() for score in self.active_final_test_scores],
            "decision": self.decision,
            "reasons": list(self.reasons),
        }


def evaluate_candidate(
    points: Iterable[PredictionPoint],
    *,
    candidate_version: str,
    active_version: str,
    evaluated_at: str,
    dataset_hash: str,
    minimum_forward_windows: int = 2,
    minimum_points_per_window: int = 2,
) -> CandidateEvaluation:
    """Score candidate and active predictions without selecting on final test."""

    records = tuple(points)
    if not candidate_version or not active_version or not dataset_hash:
        raise ValueError("candidate, active and dataset identities are required")
    if minimum_forward_windows <= 0 or minimum_points_per_window <= 0:
        raise ValueError("evaluation minimums must be positive")
    candidate = tuple(point for point in records if point.model_version == candidate_version)
    active = tuple(point for point in records if point.model_version == active_version)
    final = tuple(point for point in records if point.split == "final_test")
    forward = tuple(point for point in records if point.split == "forward")
    reasons: list[str] = []
    if not candidate:
        reasons.append("candidate_points_missing")
    if not active:
        reasons.append("active_points_missing")
    if not final:
        reasons.append("untouched_final_test_missing")
    window_ids = sorted({point.window_id for point in forward})
    if len(window_ids) < minimum_forward_windows:
        reasons.append("insufficient_forward_windows")
    candidate_scores = _scores(tuple(point for point in candidate if point.split == "forward"))
    active_scores = _scores(tuple(point for point in active if point.split == "forward"))
    final_candidate = _scores(tuple(point for point in final if point.model_version == candidate_version))
    final_active = _scores(tuple(point for point in final if point.model_version == active_version))
    if any(score.count < minimum_points_per_window for score in candidate_scores + active_scores):
        reasons.append("insufficient_points_per_window")
    paired_forward = _paired_improvement(candidate_scores, active_scores, split="forward")
    paired_final = _paired_improvement(final_candidate, final_active, split="final_test")
    if not _same_evidence_grid(
        tuple(point for point in candidate if point.split == "forward"),
        tuple(point for point in active if point.split == "forward"),
        split="forward",
    ):
        reasons.append("candidate_forward_evidence_grid_mismatch")
    if not _same_evidence_grid(
        tuple(point for point in final if point.model_version == candidate_version),
        tuple(point for point in final if point.model_version == active_version),
        split="final_test",
    ):
        reasons.append("candidate_final_test_evidence_grid_mismatch")
    if paired_forward is not True:
        reasons.append("candidate_forward_gate_not_met")
    if paired_final is not True:
        reasons.append("candidate_final_test_gate_not_met")
    decision = "qualified" if not reasons else "inconclusive"
    return CandidateEvaluation(
        candidate_version,
        active_version,
        evaluated_at,
        dataset_hash,
        _hash_points(final),
        tuple(candidate_scores),
        tuple(final_candidate),
        decision,
        tuple(dict.fromkeys(reasons)),
        tuple(active_scores),
        tuple(final_active),
    )


class ModelRegistry:
    """Persistent active/candidate history with explicit promotion and rollback."""

    def __init__(self, path: str | Path, *, initial_active_version: str) -> None:
        if not initial_active_version:
            raise ValueError("initial_active_version is required")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS model_registry (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)"
        )
        self._connection.commit()
        if self._get("active_version") is None:
            self._set("active_version", initial_active_version)
            self._set("history", [])
            self._set("consumed_final_tests", [])
            self._set("known_versions", [initial_active_version])

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ModelRegistry":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def active_version(self) -> str:
        value = self._get("active_version")
        if not isinstance(value, str):
            raise ValueError("model registry has no active version")
        return value

    def history(self) -> tuple[dict[str, Any], ...]:
        value = self._get("history") or []
        return tuple(dict(item) for item in value)

    def status(self) -> dict[str, Any]:
        """Return the durable active-version state for operator inspection."""

        return {
            "active_version": self.active_version,
            "known_versions": list(self._get("known_versions") or []),
            "consumed_final_test_count": len(self._get("consumed_final_tests") or []),
            "history": list(self.history()),
        }

    def record_evaluation(self, report: CandidateEvaluation) -> None:
        consumed = list(self._get("consumed_final_tests") or [])
        if report.final_test_hash in consumed:
            raise ValueError("final test has already been consumed by an evaluation")
        consumed.append(report.final_test_hash)
        self._set("consumed_final_tests", consumed)
        history = list(self._get("history") or [])
        history.append({"kind": "evaluation", **report.to_dict()})
        self._set("history", history)

    def promote(self, report: CandidateEvaluation) -> str:
        if report.active_version != self.active_version:
            raise ValueError("candidate report active version is stale")
        if report.decision != "qualified":
            raise ValueError("only a qualified evaluation may promote")
        if report.final_test_hash in (self._get("consumed_final_tests") or []):
            raise ValueError("final test has already been consumed by an evaluation")
        self._consume_and_promote(report)
        return report.candidate_version

    def promote_and_record(self, report: CandidateEvaluation) -> str:
        if report.active_version != self.active_version:
            raise ValueError("candidate report active version is stale")
        if report.decision != "qualified":
            raise ValueError("only a qualified evaluation may promote")
        self.record_evaluation(report)
        self._set("active_version", report.candidate_version)
        known = list(self._get("known_versions") or [])
        if report.candidate_version not in known:
            known.append(report.candidate_version)
        self._set("known_versions", known)
        history = list(self._get("history") or [])
        history.append({"kind": "promotion", "version": report.candidate_version, "evaluated_at": report.evaluated_at})
        self._set("history", history)
        return report.candidate_version

    def _consume_and_promote(self, report: CandidateEvaluation) -> None:
        consumed = list(self._get("consumed_final_tests") or [])
        consumed.append(report.final_test_hash)
        self._set("consumed_final_tests", consumed)
        self._set("active_version", report.candidate_version)
        known = list(self._get("known_versions") or [])
        if report.candidate_version not in known:
            known.append(report.candidate_version)
        self._set("known_versions", known)
        history = list(self._get("history") or [])
        history.append({"kind": "promotion", "version": report.candidate_version, "evaluated_at": report.evaluated_at})
        self._set("history", history)

    def rollback(self, version: str, *, reason: str, evaluated_at: str) -> str:
        if not version or not reason:
            raise ValueError("rollback version and reason are required")
        known = set(self._get("known_versions") or ())
        if version not in known:
            raise ValueError("rollback target is not a recorded model version")
        parsed = datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("rollback evaluated_at must include a timezone")
        self._set("active_version", version)
        history = list(self._get("history") or [])
        history.append({"kind": "rollback", "version": version, "reason": reason, "evaluated_at": evaluated_at})
        self._set("history", history)
        return version

    def _get(self, key: str) -> Any:
        row = self._connection.execute("SELECT value_json FROM model_registry WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row["value_json"])

    def _set(self, key: str, value: Any) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO model_registry(key, value_json) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (key, json.dumps(value, sort_keys=True)),
            )


def _scores(points: Iterable[PredictionPoint]) -> tuple[WindowScore, ...]:
    grouped: dict[tuple[str, str, str], list[PredictionPoint]] = {}
    for point in points:
        grouped.setdefault((point.market, point.window_id, point.split), []).append(point)
    return tuple(
        WindowScore(
            model_version=records[0].model_version,
            market=market,
            window_id=window_id,
            split=split,
            count=len(records),
            mae_bps=sum(abs(point.predicted_bps - point.target_bps) for point in records) / len(records),
        )
        for (market, window_id, split), records in sorted(grouped.items())
    )


def _paired_improvement(candidate: Iterable[WindowScore], active: Iterable[WindowScore], *, split: str) -> bool | None:
    candidate_map = {(score.market, score.window_id): score for score in candidate if score.split == split}
    active_map = {(score.market, score.window_id): score for score in active if score.split == split}
    if not candidate_map or set(candidate_map) != set(active_map):
        return None
    return all(candidate_map[key].mae_bps < active_map[key].mae_bps for key in candidate_map)


def _same_evidence_grid(
    candidate: Iterable[PredictionPoint], active: Iterable[PredictionPoint], *, split: str
) -> bool:
    """Require paired models to score the same observed outcomes."""

    def grouped(points: Iterable[PredictionPoint]) -> dict[tuple[str, str], tuple[tuple[Any, ...], ...]]:
        rows: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
        for point in points:
            if point.split != split:
                continue
            key = (point.market, point.window_id)
            rows.setdefault(key, []).append((point.observed_at, point.target_bps, point.source_refs))
        return {key: tuple(sorted(values)) for key, values in rows.items()}

    return grouped(candidate) == grouped(active)


def _hash_points(points: Iterable[PredictionPoint]) -> str:
    payload = [
        {
            "prediction_id": point.prediction_id,
            "model_version": point.model_version,
            "market": point.market,
            "window_id": point.window_id,
            "split": point.split,
            "observed_at": point.observed_at,
            "predicted_bps": point.predicted_bps,
            "target_bps": point.target_bps,
            "source_refs": list(point.source_refs),
        }
        for point in sorted(points, key=lambda item: (item.split, item.window_id, item.market, item.prediction_id, item.model_version))
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


__all__ = ["CandidateEvaluation", "ModelRegistry", "PredictionPoint", "WindowScore", "evaluate_candidate"]
