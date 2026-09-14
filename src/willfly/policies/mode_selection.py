"""Spot/LP/idle mode selection under one shared portfolio."""

from __future__ import annotations

from dataclasses import dataclass

from willfly.lp.evidence import LPEvidence, is_verified_live_evidence


@dataclass(frozen=True)
class ModeCandidate:
    mode: str
    score_bps: int
    supported: bool
    available_cash_atomic: int
    evidence: LPEvidence | None = None


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
    lp_evidence: LPEvidence | None = None,
) -> ModeDecision:
    if required_cash_atomic < 0:
        raise ValueError("required cash cannot be negative")
    if already_allocated:
        return ModeDecision("idle", False, "shared_portfolio_already_allocated")
    eligible: list[ModeCandidate] = []
    lp_was_blocked = False
    for candidate in candidates:
        if not candidate.supported or candidate.available_cash_atomic < required_cash_atomic:
            continue
        if candidate.mode == "lp":
            evidence = candidate.evidence if candidate.evidence is not None else lp_evidence
            if not is_verified_live_evidence(evidence):
                lp_was_blocked = True
                continue
        eligible.append(candidate)
    if not eligible:
        if lp_was_blocked:
            return ModeDecision("idle", True, "lp_disabled_until_verified_live_evidence")
        return ModeDecision("idle", True, "no_supported_affordable_mode")
    selected = sorted(eligible, key=lambda candidate: (-candidate.score_bps, candidate.mode))[0]
    return ModeDecision(selected.mode, True, "highest_registered_score")
