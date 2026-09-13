"""Registered feature/architecture factorial cells."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable


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


def run_factorial(*, architectures: Iterable[str], evaluator: Callable[[str, bool, bool], tuple[int, int, int, str]]) -> tuple[FactorialCell, ...]:
    cells: list[FactorialCell] = []
    for architecture, lp_features, text_features in product(tuple(architectures), (False, True), (False, True)):
        metric, cost, latency, state = evaluator(architecture, lp_features, text_features)
        cells.append(FactorialCell("market_only", lp_features, text_features, architecture, metric, cost, latency, state))
    return tuple(cells)
