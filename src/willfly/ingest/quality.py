"""Recorder quality metrics and explicit degraded-state reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Iterable, Sequence

from willfly.domain import RawEvent


@dataclass(frozen=True)
class QualityReport:
    state: str
    event_count: int
    unique_event_count: int
    duplicate_count: int
    quarantine_count: int
    retry_count: int
    average_arrival_delay_seconds: float | None
    p95_arrival_delay_seconds: float | None
    block_lag: int | None
    gap_ranges: tuple[tuple[int, int], ...]
    storage_bytes: int
    source_state: str
    missing_parent_hashes: tuple[str, ...]


def assess_quality(
    events: Iterable[RawEvent],
    *,
    latest_head: int | None = None,
    covered_ranges: Sequence[tuple[int, int]] = (),
    expected_ranges: Sequence[tuple[int, int]] = (),
    retry_count: int = 0,
    storage_bytes: int = 0,
    source_state: str = "unknown",
    missing_parent_hashes: Sequence[str] = (),
) -> QualityReport:
    """Calculate quality without converting missing or quarantined data to zero.

    A caller must explicitly establish source freshness before a report can be
    healthy. This prevents a newly started recorder, a stale provider, or an
    unresolved ancestry path from inheriting a green state from zero counters.
    """

    if retry_count < 0 or storage_bytes < 0:
        raise ValueError("quality counters cannot be negative")
    if source_state not in {"healthy", "stale", "degraded", "unknown"}:
        raise ValueError("unsupported source_state")
    records = tuple(events)
    keys = [event.logical_key for event in records]
    unique_count = len(set(keys))
    quarantine_count = sum(event.canonical_status == "quarantined" for event in records)
    delays = sorted(max(0.0, (_parse(event.received_time) - _parse(event.event_time)).total_seconds()) for event in records)
    gaps = _missing_ranges(expected_ranges, covered_ranges)
    latest_block = max((event.block_number for event in records), default=None)
    lag = None if latest_head is None or latest_block is None else max(0, latest_head - latest_block)
    unresolved_parents = tuple(dict.fromkeys(missing_parent_hashes))
    degraded = bool(gaps or quarantine_count or unresolved_parents)
    state = "degraded" if degraded else source_state
    return QualityReport(
        state=state,
        event_count=len(records),
        unique_event_count=unique_count,
        duplicate_count=len(records) - unique_count,
        quarantine_count=quarantine_count,
        retry_count=retry_count,
        average_arrival_delay_seconds=None if not delays else sum(delays) / len(delays),
        p95_arrival_delay_seconds=None if not delays else delays[max(0, ceil(len(delays) * 0.95) - 1)],
        block_lag=lag,
        gap_ranges=gaps,
        storage_bytes=storage_bytes,
        source_state=source_state,
        missing_parent_hashes=unresolved_parents,
    )


def _missing_ranges(expected: Sequence[tuple[int, int]], covered: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    covered_blocks: set[int] = set()
    for start, end in covered:
        if start < 0 or end < start:
            raise ValueError("covered range is invalid")
        covered_blocks.update(range(start, end + 1))
    gaps: list[tuple[int, int]] = []
    for start, end in expected:
        if start < 0 or end < start:
            raise ValueError("expected range is invalid")
        gap_start: int | None = None
        for block in range(start, end + 1):
            if block not in covered_blocks and gap_start is None:
                gap_start = block
            elif block in covered_blocks and gap_start is not None:
                gaps.append((gap_start, block - 1))
                gap_start = None
        if gap_start is not None:
            gaps.append((gap_start, end))
    return tuple(gaps)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
