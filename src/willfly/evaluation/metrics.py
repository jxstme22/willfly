"""Integer basis-point metrics and paired block bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
    block_id: str
    net_return_bps: int
    benchmark_return_bps: int
    failed: bool = False
    turnover_bps: int = 0
    exposure_bps: int = 0


@dataclass(frozen=True)
class MetricReport:
    episode_count: int
    independent_block_count: int
    mean_net_return_bps: int | None
    mean_excess_return_bps: int | None
    max_drawdown_bps: int | None
    failure_rate_bps: int
    turnover_bps: int
    mean_exposure_bps: int
    tail_worst_return_bps: int | None
    calibration_brier_scaled: int | None
    bootstrap_interval_bps: tuple[int, int] | None
    inference_state: str


def calculate_metrics(
    results: Iterable[EpisodeResult],
    *,
    equity_curve_atomic: Iterable[int] | None = None,
    bootstrap_replicates: int = 0,
    seed: int = 0,
    min_blocks: int = 4,
) -> MetricReport:
    """Calculate episode diagnostics and, when supplied, portfolio drawdown.

    Episode returns are suitable for averages and paired uncertainty, but they
    do not define a portfolio equity path. Callers must provide the ordered
    equity curve for percentage drawdown; omitting it leaves drawdown unknown.
    """
    records = tuple(results)
    blocks = sorted({record.block_id for record in records})
    net = [record.net_return_bps for record in records]
    excess = [record.net_return_bps - record.benchmark_return_bps for record in records]
    drawdown = _percentage_drawdown(equity_curve_atomic)
    interval = paired_block_bootstrap(records, replicates=bootstrap_replicates, seed=seed) if bootstrap_replicates else None
    return MetricReport(
        len(records),
        len(blocks),
        None if not net else sum(net) // len(net),
        None if not excess else sum(excess) // len(excess),
        drawdown,
        0 if not records else sum(record.failed for record in records) * 10_000 // len(records),
        0 if not records else sum(record.turnover_bps for record in records) // len(records),
        0 if not records else sum(record.exposure_bps for record in records) // len(records),
        None if not net else min(net),
        None,
        interval,
        _inference_state(len(blocks), min_blocks, drawdown, records),
    )


def _percentage_drawdown(equity_curve_atomic: Iterable[int] | None) -> int | None:
    if equity_curve_atomic is None:
        return None
    curve = tuple(equity_curve_atomic)
    if not curve:
        raise ValueError("equity curve cannot be empty")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in curve):
        raise ValueError("equity curve must contain non-negative atomic values")
    peak = curve[0]
    drawdown = 0
    for equity in curve:
        if equity > peak:
            peak = equity
        if peak:
            drawdown = max(drawdown, (peak - equity) * 10_000 // peak)
    return drawdown


def _inference_state(
    block_count: int,
    min_blocks: int,
    drawdown: int | None,
    records: tuple[EpisodeResult, ...],
) -> str:
    if block_count < min_blocks:
        return "insufficient_blocks"
    if drawdown is None:
        return "missing_equity_curve"
    return "pass"


def paired_block_bootstrap(results: Iterable[EpisodeResult], *, replicates: int, seed: int = 0) -> tuple[int, int] | None:
    records = tuple(results)
    groups: dict[str, list[int]] = {}
    for record in records:
        groups.setdefault(record.block_id, []).append(record.net_return_bps - record.benchmark_return_bps)
    if replicates <= 0 or len(groups) < 2:
        return None
    rng = random.Random(seed)
    block_values = list(groups.values())
    samples: list[int] = []
    for _ in range(replicates):
        picked = [rng.choice(block_values) for _ in block_values]
        values = [value for block in picked for value in block]
        samples.append(sum(values) // len(values))
    samples.sort()
    return samples[max(0, int(replicates * 0.025) - 1)], samples[min(replicates - 1, int(replicates * 0.975))]
