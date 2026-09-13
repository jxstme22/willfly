"""Matched connectome/control comparison and progression gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class ModelComparison:
    model_name: str
    seed: int
    metric_bps: int
    compute_seconds: float
    graph_hash: str | None


@dataclass(frozen=True)
class AblationResult:
    name: str
    metric_bps: int
    scope: str
    graph_hash: str | None


@dataclass(frozen=True)
class NeuralReview:
    decision: str
    state: str
    reasons: tuple[str, ...]
    comparisons: tuple[ModelComparison, ...]
    ablations: tuple[AblationResult, ...]


def run_matched_comparisons(
    model_names: Sequence[str],
    seeds: Sequence[int],
    evaluator: Callable[[str, int], tuple[int, float, str | None]],
) -> tuple[ModelComparison, ...]:
    if len(seeds) < 5:
        raise ValueError("matched neural comparisons require at least five seeds")
    return tuple(ModelComparison(name, seed, *evaluator(name, seed)) for name in model_names for seed in seeds)


def review_neural_progression(
    comparisons: Sequence[ModelComparison],
    ablations: Sequence[AblationResult],
    *,
    minimum_test_windows: int = 4,
    positive_windows: int = 0,
    uncertainty_interval_positive: bool = False,
) -> NeuralReview:
    reasons: list[str] = []
    # Supplied scalar metrics/booleans are not a verified held-out portfolio
    # comparison. Keep the release gate closed until that evaluator is wired.
    reasons.append("portfolio_evidence_not_validated")
    if len({comparison.seed for comparison in comparisons}) < 5:
        reasons.append("fewer_than_five_seeds")
    if positive_windows < minimum_test_windows:
        reasons.append("insufficient_positive_test_windows")
    if not uncertainty_interval_positive:
        reasons.append("positive_uncertainty_gate_not_met")
    if not comparisons:
        reasons.append("no_comparisons")
    decision = "retain" if not reasons else "inconclusive"
    return NeuralReview(decision, "pass" if decision == "retain" else "inconclusive", tuple(reasons), tuple(comparisons), tuple(ablations))
