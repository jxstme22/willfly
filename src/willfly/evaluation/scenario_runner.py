"""Repeatable quote stress scenarios for the trading laboratory."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from willfly.evaluation.replay_audit import CostScenario
from willfly.replay.execution import PoolQuote, simulate_fill


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario: str
    status: str
    input_atomic: int
    output_atomic: int
    net_quote_atomic: int | None
    entry_status: str
    exit_status: str
    source_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "status": self.status,
            "input_atomic": str(self.input_atomic),
            "output_atomic": str(self.output_atomic),
            "net_quote_atomic": None if self.net_quote_atomic is None else str(self.net_quote_atomic),
            "entry_status": self.entry_status,
            "exit_status": self.exit_status,
            "source_refs": list(self.source_refs),
        }


def run_quote_stress_scenarios(
    entry_quote: PoolQuote | None,
    exit_quote: PoolQuote | None,
    *,
    input_atomic: int,
    submitted_at: str,
    scenarios: Iterable[CostScenario],
) -> tuple[ScenarioOutcome, ...]:
    """Rerun one path under costs and delay; never substitute another fill."""

    if input_atomic <= 0:
        raise ValueError("input_atomic must be positive")
    if entry_quote is not None and exit_quote is not None and (
        entry_quote.input_asset != exit_quote.output_asset
        or entry_quote.output_asset != exit_quote.input_asset
    ):
        raise ValueError("round-trip quotes must reverse the same asset pair")
    outcomes: list[ScenarioOutcome] = []
    for scenario in scenarios:
        entry = _fill_with_stress(
            entry_quote,
            input_atomic=input_atomic,
            submitted_at=submitted_at,
            scenario=scenario,
        )
        if entry.status != "filled":
            outcomes.append(
                ScenarioOutcome(
                    scenario.name,
                    "entry_failed",
                    input_atomic,
                    0,
                    None,
                    entry.status,
                    "not_attempted",
                    (entry.source_ref,),
                )
            )
            continue
        exit = _fill_with_stress(
            exit_quote,
            input_atomic=entry.output_atomic,
            submitted_at=entry.available_at,
            scenario=scenario,
        )
        if exit.status != "filled":
            outcomes.append(
                ScenarioOutcome(
                    scenario.name,
                    "exit_failed",
                    input_atomic,
                    entry.output_atomic,
                    None,
                    entry.status,
                    exit.status,
                    (entry.source_ref, exit.source_ref),
                )
            )
            continue
        outcomes.append(
            ScenarioOutcome(
                scenario.name,
                "completed",
                input_atomic,
                exit.output_atomic,
                exit.output_atomic - input_atomic,
                entry.status,
                exit.status,
                (entry.source_ref, exit.source_ref),
            )
        )
    return tuple(outcomes)


def _fill_with_stress(
    quote: PoolQuote | None,
    *,
    input_atomic: int,
    submitted_at: str,
    scenario: CostScenario,
):
    if quote is not None and quote.fee_bps + scenario.fee_bps >= 10_000:
        raise ValueError("scenario fee would consume the whole input")
    stressed_quote = None if quote is None else PoolQuote(
        quote.pool_id,
        quote.input_asset,
        quote.output_asset,
        quote.reserve_input_atomic,
        quote.reserve_output_atomic,
        quote.fee_bps + scenario.fee_bps,
        quote.observed_at,
        quote.hook_supported,
    )
    result = simulate_fill(
        stressed_quote,
        input_atomic=input_atomic,
        submitted_at=submitted_at,
        processing_delay_seconds=scenario.delay_seconds,
    )
    if result.status == "filled" and scenario.slippage_bps:
        output = result.output_atomic * (10_000 - scenario.slippage_bps) // 10_000
        if output <= 0:
            return replace(result, status="reverted", output_atomic=0, reason="slippage_consumed_output")
        return replace(result, output_atomic=output)
    return result


__all__ = ["ScenarioOutcome", "run_quote_stress_scenarios"]
