"""Explicit health and degraded-mode rules for the shadow loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ShadowHealth:
    state: str
    can_enter: bool
    management_action: str
    missed_deadline: bool
    reason: str


def assess_shadow_health(
    *,
    quality_state: str,
    contradictory: bool,
    now: str,
    latest_arrival: str | None,
    existing_position: bool = False,
    decision_deadline_seconds: int = 15,
) -> ShadowHealth:
    if quality_state not in {"healthy", "stale", "degraded", "unknown"}:
        raise ValueError("unsupported shadow quality state")
    if decision_deadline_seconds <= 0:
        raise ValueError("decision deadline must be positive")
    now_value = _parse(now)
    if latest_arrival is None:
        return ShadowHealth(
            "unknown",
            False,
            prescribed_management_action(existing_position, execution_state="unknown"),
            True,
            "no_received_observation",
        )
    delay = (now_value - _parse(latest_arrival)).total_seconds()
    if delay < 0:
        raise ValueError("observation arrival cannot be in the future")
    missed = delay > decision_deadline_seconds
    if contradictory:
        state = "degraded"
        reason = "contradictory_observation"
    elif quality_state != "healthy":
        state = quality_state
        reason = f"quality_{quality_state}"
    elif missed:
        state = "stale"
        reason = "decision_deadline_missed"
    else:
        state = "healthy"
        reason = "within_deadline"
    return ShadowHealth(
        state,
        state == "healthy",
        prescribed_management_action(existing_position, execution_state="known" if state == "healthy" else "unknown"),
        missed,
        reason,
    )


def prescribed_management_action(existing_position: bool, *, execution_state: str) -> str:
    if execution_state not in {"known", "unknown"}:
        raise ValueError("unsupported execution state")
    if not existing_position:
        return "pause_new_entries"
    if execution_state == "unknown":
        return "hold_and_reconcile_existing_position"
    return "hold_existing_position"


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow timestamps must include a timezone")
    return parsed
