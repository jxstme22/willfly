"""Restricted LP baseline policies for one verified pool family."""

from __future__ import annotations

from dataclasses import dataclass

from willfly.lp.evidence import LPEvidence, is_verified_live_evidence


@dataclass(frozen=True)
class LPPolicyDecision:
    policy: str
    action: str
    tick_lower: int | None
    tick_upper: int | None
    reason: str


def fixed_wide_range(
    current_tick: int,
    *,
    width: int = 600,
    evidence: LPEvidence | None = None,
) -> LPPolicyDecision:
    if width <= 0:
        raise ValueError("range width must be positive")
    enabled = is_verified_live_evidence(evidence)
    return LPPolicyDecision(
        "fixed_wide_range",
        "open" if enabled else "watch",
        current_tick - width,
        current_tick + width,
        "fixed_discrete_range" if enabled else "lp_disabled_until_verified_live_evidence",
    )


def volatility_range(
    current_tick: int,
    volatility_bps: int,
    *,
    minimum_width: int = 120,
    multiplier: int = 2,
    evidence: LPEvidence | None = None,
) -> LPPolicyDecision:
    if volatility_bps < 0 or minimum_width <= 0 or multiplier <= 0:
        raise ValueError("volatility range parameters are invalid")
    width = max(minimum_width, volatility_bps * multiplier)
    enabled = is_verified_live_evidence(evidence)
    return LPPolicyDecision(
        "volatility_range",
        "open" if enabled else "watch",
        current_tick - width,
        current_tick + width,
        "observed_volatility_range" if enabled else "lp_disabled_until_verified_live_evidence",
    )


def idle_lp() -> LPPolicyDecision:
    return LPPolicyDecision("idle", "watch", None, None, "no_lp_position")
