"""Spot/LP/idle mode selection under one shared portfolio."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeCandidate:
    mode: str
    score_bps: int
    supported: bool
    available_cash_atomic: int


@dataclass(frozen=True)
class ModeDecision:
    mode: str
    accepted: bool
    reason: str


def select_mode(
    candidates: tuple[ModeCandidate, ...],
    *,
    required_cash_atomic: int,
    already_allocated: bool = False,
) -> ModeDecision:
    if required_cash_atomic < 0:
        raise ValueError("required cash cannot be negative")
    if already_allocated:
        return ModeDecision("idle", False, "shared_portfolio_already_allocated")
    eligible = [
        candidate
        for candidate in candidates
        if candidate.supported and candidate.available_cash_atomic >= required_cash_atomic
    ]
    if not eligible:
        return ModeDecision("idle", True, "no_supported_affordable_mode")
    selected = sorted(eligible, key=lambda candidate: (-candidate.score_bps, candidate.mode))[0]
    return ModeDecision(selected.mode, True, "highest_registered_score")
