"""Restricted LP baseline policies for one verified pool family."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LPPolicyDecision:
    policy: str
    action: str
    tick_lower: int | None
    tick_upper: int | None
    reason: str


def fixed_wide_range(current_tick: int, *, width: int = 600) -> LPPolicyDecision:
    if width <= 0:
        raise ValueError("range width must be positive")
    return LPPolicyDecision(
        "fixed_wide_range",
        "open",
        current_tick - width,
        current_tick + width,
        "fixed_discrete_range",
    )


def volatility_range(
    current_tick: int,
    volatility_bps: int,
    *,
    minimum_width: int = 120,
    multiplier: int = 2,
) -> LPPolicyDecision:
    if volatility_bps < 0 or minimum_width <= 0 or multiplier <= 0:
        raise ValueError("volatility range parameters are invalid")
    width = max(minimum_width, volatility_bps * multiplier)
    return LPPolicyDecision(
        "volatility_range",
        "open",
        current_tick - width,
        current_tick + width,
        "observed_volatility_range",
    )


def idle_lp() -> LPPolicyDecision:
    return LPPolicyDecision("idle", "watch", None, None, "no_lp_position")
