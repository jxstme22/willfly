"""Time-gated audit and replay reconciliation for prospective shadow data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class ShadowWindowRequirements:
    minimum_days: int = 14
    minimum_eligible_launches: int = 200
    minimum_healthy_availability_bps: int = 9900

    def __post_init__(self) -> None:
        if self.minimum_days <= 0 or self.minimum_eligible_launches <= 0 or not 0 <= self.minimum_healthy_availability_bps <= 10_000:
            raise ValueError("shadow window requirements are invalid")


@dataclass(frozen=True)
class ShadowWindowAudit:
    start_time: str
    end_time: str | None
    duration_days: float
    eligible_launches: int
    healthy_scheduled_decisions: int
    healthy_missed_decisions: int
    healthy_availability_bps: int | None
    unresolved_gaps: tuple[str, ...]
    state: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ShadowReconciliation:
    compared_decisions: int
    mean_quote_drift_bps: int | None
    missed_opportunities: int
    data_revisions: int
    stress_net_return_bps: tuple[int, ...]
    state: str
    prospective_only: bool = True


def audit_shadow_window(
    start_time: str,
    end_time: str | None,
    *,
    eligible_launches: int,
    healthy_scheduled_decisions: int,
    healthy_missed_decisions: int,
    unresolved_gaps: Iterable[str] = (),
    requirements: ShadowWindowRequirements = ShadowWindowRequirements(),
) -> ShadowWindowAudit:
    if min(eligible_launches, healthy_scheduled_decisions, healthy_missed_decisions) < 0:
        raise ValueError("shadow audit counts cannot be negative")
    if healthy_missed_decisions > healthy_scheduled_decisions:
        raise ValueError("missed decisions exceed scheduled decisions")
    start = _parse(start_time)
    end = None if end_time is None else _parse(end_time)
    if end is not None and end < start:
        raise ValueError("shadow window must be chronological")
    duration = 0.0 if end is None else (end - start).total_seconds() / 86_400
    availability = None
    if healthy_scheduled_decisions:
        availability = (healthy_scheduled_decisions - healthy_missed_decisions) * 10_000 // healthy_scheduled_decisions
    reasons: list[str] = []
    if duration < requirements.minimum_days:
        reasons.append("insufficient_duration")
    if eligible_launches < requirements.minimum_eligible_launches:
        reasons.append("insufficient_eligible_launches")
    if availability is None or availability < requirements.minimum_healthy_availability_bps:
        reasons.append("healthy_interval_availability_below_gate")
    gaps = tuple(dict.fromkeys(str(gap) for gap in unresolved_gaps if str(gap)))
    if gaps:
        reasons.append("unresolved_source_gaps")
    return ShadowWindowAudit(
        start_time,
        end_time,
        duration,
        eligible_launches,
        healthy_scheduled_decisions,
        healthy_missed_decisions,
        availability,
        gaps,
        "pass" if not reasons else "inconclusive",
        tuple(reasons),
    )


def reconcile_shadow(
    quote_drifts_bps: Iterable[int],
    *,
    missed_opportunities: int,
    data_revisions: int,
    stress_net_return_bps: Iterable[int],
) -> ShadowReconciliation:
    drifts = tuple(quote_drifts_bps)
    stresses = tuple(stress_net_return_bps)
    if (
        not all(isinstance(value, int) and not isinstance(value, bool) for value in drifts)
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in stresses)
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in (missed_opportunities, data_revisions))
        or min(missed_opportunities, data_revisions) < 0
    ):
        raise ValueError("shadow reconciliation values are invalid")
    return ShadowReconciliation(
        len(drifts),
        None if not drifts else sum(drifts) // len(drifts),
        missed_opportunities,
        data_revisions,
        stresses,
        "inconclusive" if data_revisions or not stresses else "reviewed",
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow timestamps must include a timezone")
    return parsed
