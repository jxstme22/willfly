"""Explicit unavailable boundary for optional Mezzanine observations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MezzanineCapability:
    status: str
    reason: str
    evidence_state: str = "unknown"


def capability() -> MezzanineCapability:
    return MezzanineCapability(
        "unavailable",
        "no_supported_production_api_verified",
    )
