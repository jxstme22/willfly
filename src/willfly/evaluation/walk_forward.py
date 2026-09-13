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


ReplayWindow = Callable[[str, tuple[EpisodeResult, ...], WalkForwardWindow], tuple[EpisodeResult, ...]]


def evaluate_walk_forward(
    scenarios: Mapping[str, Iterable[EpisodeResult]],
    windows: Iterable[WalkForwardWindow],
    *,
    strongest_practical_baseline: str | None = None,
    replay_window: ReplayWindow | None = None,
) -> WalkForwardResult:
    """Evaluate every registered scenario/window without selecting favorable periods.

    ``replay_window`` is the boundary for an execution-aware evaluator. It
    receives the declared scenario and window and must return the same ordered
    episodes after applying that window's capital, delay and costs. Without it,
    this helper remains a metadata-only summary and reports that limitation.
    """

    ordered_windows = tuple(windows)
    if not ordered_windows:
        raise ValueError("at least one evaluation window is required")
    if any(window.capital_atomic < 0 or min(window.delay_seconds, window.fee_bps, window.slippage_bps) < 0 for window in ordered_windows):
        raise ValueError("walk-forward cost settings are invalid")
    scenario_records = {name: tuple(results) for name, results in scenarios.items()}
    reports: dict[str, MetricReport] = {}
    for window in ordered_windows:
        for name, records in scenario_records.items():
            replayed = replay_window(name, records, window) if replay_window else records
            reports[f"{window.name}:{name}"] = calculate_metrics(replayed)
    if strongest_practical_baseline is not None and strongest_practical_baseline not in scenario_records:
        raise KeyError(strongest_practical_baseline)
    # This helper summarizes episodes; it does not rerun fills under window costs.
    state = "pass" if replay_window else "inconclusive_missing_replay"
    return WalkForwardResult(reports, strongest_practical_baseline, False, state)
