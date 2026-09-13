"""Locked chronological walk-forward evaluation metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from willfly.evaluation.metrics import EpisodeResult, MetricReport, calculate_metrics


@dataclass(frozen=True)
class WalkForwardWindow:
    name: str
    capital_atomic: int
    delay_seconds: int
    fee_bps: int
    slippage_bps: int


@dataclass(frozen=True)
class WalkForwardResult:
    windows: Mapping[str, MetricReport]
    strongest_practical_baseline: str | None
    selected_before_holdout: bool
    state: str


def evaluate_walk_forward(
    scenarios: Mapping[str, Iterable[EpisodeResult]],
    windows: Iterable[WalkForwardWindow],
    *,
    strongest_practical_baseline: str | None = None,
) -> WalkForwardResult:
    """Evaluate every registered scenario/window without selecting favorable periods."""

    ordered_windows = tuple(windows)
    if not ordered_windows:
        raise ValueError("at least one evaluation window is required")
    if any(window.capital_atomic < 0 or min(window.delay_seconds, window.fee_bps, window.slippage_bps) < 0 for window in ordered_windows):
        raise ValueError("walk-forward cost settings are invalid")
    scenario_records = {name: tuple(results) for name, results in scenarios.items()}
    reports: dict[str, MetricReport] = {}
    for window in ordered_windows:
        for name, records in scenario_records.items():
            reports[f"{window.name}:{name}"] = calculate_metrics(records)
    if strongest_practical_baseline is not None and strongest_practical_baseline not in scenario_records:
        raise KeyError(strongest_practical_baseline)
    # This helper summarizes episodes; it does not rerun fills under window costs.
    return WalkForwardResult(reports, strongest_practical_baseline, False, "inconclusive")
