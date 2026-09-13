"""Causal LP/trader observations with cohort scope and arrival time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class LPObservation:
    wallet: str
    pool_id: str
    position_id: str
    action: str
    event_time: str
    received_time: str
    liquidity_delta: int
    token0_delta_atomic: str
    token1_delta_atomic: str
    tick_lower: int
    tick_upper: int
    cohort_scope: str
    source_ref: str

    def __post_init__(self) -> None:
        if self.action not in {"open", "resize", "collect", "remove", "unknown"}:
            raise ValueError("unsupported LP action")
        if self.tick_lower >= self.tick_upper or not self.source_ref or not self.cohort_scope:
            raise ValueError("LP observation is invalid")
        if _parse(self.received_time) < _parse(self.event_time):
            raise ValueError("LP receipt cannot precede event")


def causal_lp_observations(records: Iterable[LPObservation], *, arrival_cutoff: str) -> tuple[LPObservation, ...]:
    cutoff = _parse(arrival_cutoff)
    return tuple(sorted((record for record in records if _parse(record.received_time) <= cutoff), key=lambda item: (item.received_time, item.source_ref)))


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("LP timestamps must include a timezone")
    return parsed
