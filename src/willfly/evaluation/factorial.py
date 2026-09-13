"""Registered feature/architecture factorial cells."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from itertools import product
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class FactorialCell:
    market_features: str
    lp_features: bool
    text_features: bool
    architecture: str
    metric_bps: int
    cost_atomic: int
    latency_seconds: int
    evidence_state: str
    dataset_hash: str = ""
    config_hash: str = ""
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactorialReview:
    state: str
    reasons: tuple[str, ...]
    cells: tuple[FactorialCell, ...]


def run_factorial(
    *,
    architectures: Iterable[str],
    evaluator: Callable[[str, bool, bool], tuple[int, int, int, str]],
    dataset_hash: str = "fixture-dataset",
    config_hash: str = "fixture-config",
    evidence_refs: Sequence[str] = (),
) -> tuple[FactorialCell, ...]:
    if not dataset_hash or not config_hash:
        raise ValueError("factorial dataset and config identities are required")
    cells: list[FactorialCell] = []
    for architecture, lp_features, text_features in product(tuple(architectures), (False, True), (False, True)):
        metric, cost, latency, state = evaluator(architecture, lp_features, text_features)
        if min(cost, latency) < 0 or state not in {"pass", "inconclusive", "unavailable"}:
            raise ValueError("factorial evaluator returned invalid evidence")
        cells.append(FactorialCell("market_only", lp_features, text_features, architecture, metric, cost, latency, state, dataset_hash, config_hash, tuple(evidence_refs)))
    return tuple(cells)


def review_factorial(
    cells: Iterable[FactorialCell],
    *,
    architectures: Iterable[str],
    dataset_hash: str,
    config_hash: str,
) -> FactorialReview:
    """Check completeness and identity before attributing any contribution."""

    records = tuple(cells)
    expected_architectures = tuple(sorted(set(architectures)))
    reasons: list[str] = []
    expected_keys = {
        (architecture, lp_features, text_features)
        for architecture, lp_features, text_features in product(expected_architectures, (False, True), (False, True))
    }
    actual_keys = {(cell.architecture, cell.lp_features, cell.text_features) for cell in records}
    if actual_keys != expected_keys:
        reasons.append("factorial_cells_incomplete")
    if any(cell.dataset_hash != dataset_hash or cell.config_hash != config_hash for cell in records):
        reasons.append("factorial_identity_mismatch")
    if any(cell.evidence_state != "pass" for cell in records):
        reasons.append("factorial_cell_not_pass")
    if any(not cell.evidence_refs for cell in records):
        reasons.append("factorial_evidence_refs_missing")
    return FactorialReview("pass" if not reasons else "inconclusive", tuple(dict.fromkeys(reasons)), records)


def factorial_hash(cells: Iterable[FactorialCell]) -> str:
    payload = [cell.__dict__ for cell in cells]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


__all__ = ["FactorialCell", "FactorialReview", "factorial_hash", "review_factorial", "run_factorial"]
