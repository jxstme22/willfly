"""Availability-ordered deterministic replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class ReplayEvent:
    event_id: str
    event_time: str
    available_at: str
    payload: Any

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id cannot be empty")
        _parse(self.event_time)
        _parse(self.available_at)
        if _parse(self.available_at) < _parse(self.event_time):
            raise ValueError("availability cannot precede event time")


@dataclass(frozen=True)
class ReplayTick:
    tick_id: str
    tick_time: str

    def __post_init__(self) -> None:
        if not self.tick_id.strip():
            raise ValueError("tick_id cannot be empty")
        _parse(self.tick_time)


@dataclass(frozen=True)
class ReplaySnapshot:
    tick_id: str
    tick_time: str
    newly_available: tuple[ReplayEvent, ...]
    available_events: tuple[ReplayEvent, ...]


class ReplayScheduler:
    """Replay events by availability, with stable ordering for ties."""

    def __init__(self, events: Iterable[ReplayEvent]) -> None:
        records = tuple(events)
        if len({event.event_id for event in records}) != len(records):
            raise ValueError("replay event IDs must be unique")
        self._events = tuple(sorted(records, key=lambda event: (_parse(event.available_at), _parse(event.event_time), event.event_id)))

    @property
    def events(self) -> tuple[ReplayEvent, ...]:
        return self._events

    def run(self, ticks: Iterable[ReplayTick]) -> tuple[ReplaySnapshot, ...]:
        ordered_ticks = tuple(ticks)
        if any(_parse(left.tick_time) > _parse(right.tick_time) for left, right in zip(ordered_ticks, ordered_ticks[1:])):
            raise ValueError("replay ticks must be chronological")
        seen: list[ReplayEvent] = []
        cursor = 0
        snapshots: list[ReplaySnapshot] = []
        for tick in ordered_ticks:
            tick_time = _parse(tick.tick_time)
            newly: list[ReplayEvent] = []
            while cursor < len(self._events) and _parse(self._events[cursor].available_at) <= tick_time:
                event = self._events[cursor]
                newly.append(event)
                seen.append(event)
                cursor += 1
            snapshots.append(ReplaySnapshot(tick.tick_id, tick.tick_time, tuple(newly), tuple(seen)))
        return tuple(snapshots)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("replay timestamps must include a timezone")
    return parsed
