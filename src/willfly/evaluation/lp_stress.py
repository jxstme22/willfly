"""LP cost/range stress metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from willfly.evaluation.metrics import EpisodeResult, MetricReport, calculate_metrics


@dataclass(frozen=True)
class LPStressScenario:
    name: str
    price_move_bps: int
    fee_bps: int
    delay_seconds: int
    position_size_atomic: int


@dataclass(frozen=True)
class LPStressResult:
    scenario: LPStressScenario
    modeled_net_atomic: int | None
    state: str
    reason: str | None


@dataclass(frozen=True)
class LPModeCase:
    case_id: str
    block_id: str
    observed_at: str
    spot_net_return_bps: int
    lp_net_return_bps: int | None
    benchmark_return_bps: int = 0
    spot_failed: bool = False
    lp_failed: bool = False


@dataclass(frozen=True)
class LPModeComparison:
    capital_atomic: int
    spot: MetricReport
    idle: MetricReport
    lp: MetricReport | None
    lp_state: str
    reasons: tuple[str, ...]
    mutually_exclusive: bool = True


def stress_lp_scenarios(
    scenarios: Iterable[LPStressScenario],
    *,
    base_fee_atomic: int,
    base_value_atomic: int,
) -> tuple[LPStressResult, ...]:
    """Run a deliberately linearized LP stress screen.

    This is a sensitivity artifact, not a claim of executable LP PnL. The
    result stays marked ``modeled`` until pool-specific state and fee data are
    verified.
    """

    if min(base_fee_atomic, base_value_atomic) < 0:
        raise ValueError("base LP values cannot be negative")
    results: list[LPStressResult] = []
    for scenario in scenarios:
        if min(scenario.price_move_bps, scenario.fee_bps, scenario.delay_seconds, scenario.position_size_atomic) < 0:
            raise ValueError("LP stress scenario is invalid")
        modeled = base_fee_atomic - (
            scenario.position_size_atomic * scenario.price_move_bps // 10_000
        ) - (scenario.position_size_atomic * scenario.fee_bps // 10_000)
        results.append(
            LPStressResult(scenario, modeled, "modeled", "linearized_counterfactual")
        )
    return tuple(results)


def compare_lp_modes(
    cases: Iterable[LPModeCase],
    *,
    capital_atomic: int,
    lp_evidence_state: str,
    bootstrap_replicates: int = 0,
    seed: int = 0,
    minimum_blocks: int = 4,
) -> LPModeComparison:
    """Compare mutually exclusive modes without turning unavailable LP into zero PnL."""

    if capital_atomic <= 0 or lp_evidence_state not in {"verified", "inconclusive", "unavailable"}:
        raise ValueError("LP comparison inputs are invalid")
    ordered = tuple(sorted(cases, key=lambda case: (case.observed_at, case.case_id)))
    if not ordered:
        raise ValueError("LP comparison requires cases")
    spot_records = tuple(
        EpisodeResult(case.case_id, case.block_id, case.spot_net_return_bps, case.benchmark_return_bps, case.spot_failed)
        for case in ordered
    )
    idle_records = tuple(EpisodeResult(f"idle:{case.case_id}", case.block_id, 0, case.benchmark_return_bps) for case in ordered)
    spot = calculate_metrics(spot_records, equity_curve_atomic=_equity_curve(capital_atomic, spot_records), bootstrap_replicates=bootstrap_replicates, seed=seed, min_blocks=minimum_blocks)
    idle = calculate_metrics(idle_records, equity_curve_atomic=_equity_curve(capital_atomic, idle_records), bootstrap_replicates=bootstrap_replicates, seed=seed, min_blocks=minimum_blocks)
    reasons: list[str] = []
    lp_report: MetricReport | None = None
    if lp_evidence_state != "verified":
        reasons.append("lp_disabled_until_verified_evidence")
    elif any(case.lp_net_return_bps is None for case in ordered):
        reasons.append("missing_lp_outcomes")
    else:
        lp_records = tuple(
            EpisodeResult(f"lp:{case.case_id}", case.block_id, int(case.lp_net_return_bps), case.benchmark_return_bps, case.lp_failed)
            for case in ordered
        )
        lp_report = calculate_metrics(lp_records, equity_curve_atomic=_equity_curve(capital_atomic, lp_records), bootstrap_replicates=bootstrap_replicates, seed=seed, min_blocks=minimum_blocks)
    return LPModeComparison(capital_atomic, spot, idle, lp_report, lp_evidence_state, tuple(reasons))


def _equity_curve(capital_atomic: int, records: tuple[EpisodeResult, ...]) -> tuple[int, ...]:
    values = [capital_atomic]
    current = capital_atomic
    for record in records:
        current = max(0, current + current * record.net_return_bps // 10_000)
        values.append(current)
    return tuple(values)


__all__ = ["LPModeCase", "LPModeComparison", "LPStressResult", "LPStressScenario", "compare_lp_modes", "stress_lp_scenarios"]
