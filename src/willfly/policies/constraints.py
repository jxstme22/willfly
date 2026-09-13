"""Shared-cash candidate allocation with explicit rejection reasons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    asset: str
    signal_time: str
    score_bps: int

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.asset or not self.signal_time:
            raise ValueError("candidate identity and signal time are required")


@dataclass(frozen=True)
class AllocationDecision:
    candidate_id: str
    accepted: bool
    allocation_atomic: int
    reason: str


@dataclass(frozen=True)
class AllocationResult:
    decisions: tuple[AllocationDecision, ...]
    remaining_cash_atomic: int
    open_positions: tuple[str, ...]


def allocate_candidates(
    candidates: Iterable[Candidate],
    *,
    cash_atomic: int,
    fixed_entry_atomic: int,
    max_positions: int,
    existing_positions: Iterable[str] = (),
) -> AllocationResult:
    """Allocate one fixed ticket at a time without leverage or adding."""

    if min(cash_atomic, fixed_entry_atomic) < 0 or fixed_entry_atomic == 0 or max_positions < 0:
        raise ValueError("allocation constraints are invalid")
    records = tuple(candidates)
    if len({candidate.candidate_id for candidate in records}) != len(records):
        raise ValueError("candidate IDs must be unique")
    positions = set(existing_positions)
    decisions: list[AllocationDecision] = []
    remaining = cash_atomic
    accepted_count = len(positions)
    for candidate in sorted(records, key=lambda item: (-item.score_bps, item.signal_time, item.candidate_id)):
        if candidate.asset in positions:
            decisions.append(AllocationDecision(candidate.candidate_id, False, 0, "position_already_open_no_adding"))
        elif accepted_count >= max_positions:
            decisions.append(AllocationDecision(candidate.candidate_id, False, 0, "max_concurrent_positions"))
        elif remaining < fixed_entry_atomic:
            decisions.append(AllocationDecision(candidate.candidate_id, False, 0, "insufficient_simulation_cash"))
        else:
            decisions.append(AllocationDecision(candidate.candidate_id, True, fixed_entry_atomic, "accepted"))
            remaining -= fixed_entry_atomic
            positions.add(candidate.asset)
            accepted_count += 1
    return AllocationResult(tuple(decisions), remaining, tuple(sorted(positions)))
