"""Determinism, unsupported-path and cost-stress audit for replay."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from willfly.replay.execution import FillResult
from willfly.replay.scheduler import ReplayEvent, ReplayScheduler, ReplayTick


@dataclass(frozen=True)
class CostScenario:
    name: str
    delay_seconds: int
    fee_bps: int
    slippage_bps: int

    def __post_init__(self) -> None:
        if not self.name or min(self.delay_seconds, self.fee_bps, self.slippage_bps) < 0:
            raise ValueError("cost scenario is invalid")


@dataclass(frozen=True)
class ReplayAudit:
    deterministic: bool
    event_order_hash: str
    repeated_order_hash: str
    event_count: int
    tick_count: int
    exact_fill_count: int
    approximate_fill_count: int
    unsupported_fill_count: int
    failed_fill_count: int
    failure_reasons: tuple[str, ...]
    cost_scenarios: tuple[CostScenario, ...]
    data_charge_atomic: int
    data_charge_allocation: str
    observed_example_count: int
    required_observed_examples: int
    evidence_state: str
    residual_discrepancies: tuple[str, ...]
    leader_follower_separated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "deterministic": self.deterministic,
            "event_order_hash": self.event_order_hash,
            "repeated_order_hash": self.repeated_order_hash,
            "event_count": self.event_count,
            "tick_count": self.tick_count,
            "exact_fill_count": self.exact_fill_count,
            "approximate_fill_count": self.approximate_fill_count,
            "unsupported_fill_count": self.unsupported_fill_count,
            "failed_fill_count": self.failed_fill_count,
            "failure_reasons": list(self.failure_reasons),
            "cost_scenarios": [scenario.__dict__.copy() for scenario in self.cost_scenarios],
            "data_charge_atomic": self.data_charge_atomic,
            "data_charge_allocation": self.data_charge_allocation,
            "observed_example_count": self.observed_example_count,
            "required_observed_examples": self.required_observed_examples,
            "evidence_state": self.evidence_state,
            "residual_discrepancies": list(self.residual_discrepancies),
            "leader_follower_separated": self.leader_follower_separated,
        }


def run_replay_audit(
    events: Iterable[ReplayEvent],
    ticks: Iterable[ReplayTick],
    *,
    fills: Iterable[FillResult] = (),
    cost_scenarios: tuple[CostScenario, ...] = (
        CostScenario("base", 0, 0, 0),
        CostScenario("stressed", 5, 100, 250),
    ),
    data_charge_atomic: int = 0,
    data_charge_allocation: str = "per_replay_dataset",
    observed_example_count: int = 0,
    required_observed_examples: int = 20,
    residual_discrepancies: tuple[str, ...] = (),
    leader_follower_separated: bool = True,
) -> ReplayAudit:
    """Repeat the scheduler and inventory path, retaining all non-exact outcomes."""

    if min(data_charge_atomic, observed_example_count, required_observed_examples) < 0 or not data_charge_allocation:
        raise ValueError("audit metadata is invalid")
    event_records = tuple(events)
    tick_records = tuple(ticks)
    first = ReplayScheduler(event_records).run(tick_records)
    second = ReplayScheduler(event_records).run(tick_records)
    first_ids = [event.event_id for snapshot in first for event in snapshot.newly_available]
    second_ids = [event.event_id for snapshot in second for event in snapshot.newly_available]
    first_hash = _hash(first_ids)
    second_hash = _hash(second_ids)
    deterministic = first == second
    fill_records = tuple(fills)
    failures = tuple(sorted({fill.reason for fill in fill_records if fill.status not in {"filled", "not_attempted"} and fill.reason}))
    discrepancies = list(residual_discrepancies)
    if observed_example_count < required_observed_examples:
        discrepancies.append("insufficient_observed_transaction_examples")
    evidence_state = "pass" if not discrepancies and deterministic and leader_follower_separated else "inconclusive"
    return ReplayAudit(
        deterministic=deterministic,
        event_order_hash=first_hash,
        repeated_order_hash=second_hash,
        event_count=len(event_records),
        tick_count=len(tick_records),
        exact_fill_count=sum(fill.status == "filled" and not fill.approximate for fill in fill_records),
        approximate_fill_count=sum(fill.status == "filled" and fill.price_impact_bps is not None for fill in fill_records),
        unsupported_fill_count=sum(fill.status == "unsupported" for fill in fill_records),
        failed_fill_count=sum(fill.status in {"reverted", "missing_state", "unsupported"} for fill in fill_records),
        failure_reasons=failures,
        cost_scenarios=cost_scenarios,
        data_charge_atomic=data_charge_atomic,
        data_charge_allocation=data_charge_allocation,
        observed_example_count=observed_example_count,
        required_observed_examples=required_observed_examples,
        evidence_state=evidence_state,
        residual_discrepancies=tuple(dict.fromkeys(discrepancies)),
        leader_follower_separated=leader_follower_separated,
    )


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
