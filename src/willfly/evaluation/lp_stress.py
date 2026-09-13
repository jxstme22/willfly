"""LP cost/range stress metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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
