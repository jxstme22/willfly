"""Chronological split manifests with purge and leakage checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Iterable, Mapping


class SplitLeakageError(ValueError):
    """Raised when a feature or split would use future information."""


@dataclass(frozen=True)
class LabelReference:
    record_id: str
    group_id: str
    observation_time: str
    horizon_end: str
    feature_as_of_time: str
    future_derived: bool = False

    def __post_init__(self) -> None:
        observation = _parse(self.observation_time)
        horizon_end = _parse(self.horizon_end)
        feature_time = _parse(self.feature_as_of_time)
        if not self.record_id or not self.group_id or horizon_end <= observation:
            raise ValueError("label reference is invalid")
        if feature_time > observation or self.future_derived:
            raise SplitLeakageError(f"future-derived feature in {self.record_id}")


@dataclass(frozen=True)
class SplitWindow:
    name: str
    start: str
    end: str

    def __post_init__(self) -> None:
        if not self.name or _parse(self.end) <= _parse(self.start):
            raise ValueError("split window is invalid")


@dataclass(frozen=True)
class SplitExclusion:
    record_id: str
    reason: str


@dataclass(frozen=True)
class SplitManifest:
    partitions: Mapping[str, tuple[str, ...]]
    exclusions: tuple[SplitExclusion, ...]
    manifest_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "partitions": {name: list(ids) for name, ids in self.partitions.items()},
            "exclusions": [exclusion.__dict__.copy() for exclusion in self.exclusions],
            "manifest_hash": self.manifest_hash,
        }


def build_split_manifest(
    records: Iterable[LabelReference],
    windows: Iterable[SplitWindow],
) -> SplitManifest:
    """Assign records chronologically, purging cross-partition overlap/group reuse."""

    ordered_windows = tuple(windows)
    if not ordered_windows:
        raise ValueError("at least one split window is required")
    if len({window.name for window in ordered_windows}) != len(ordered_windows):
        raise ValueError("split window names must be unique")
    if any(_parse(left.end) > _parse(right.start) for left, right in zip(ordered_windows, ordered_windows[1:])):
        raise ValueError("split windows overlap or are out of order")
    records = tuple(sorted(records, key=lambda record: (_parse(record.observation_time), record.record_id)))
    partitions: dict[str, list[str]] = {window.name: [] for window in ordered_windows}
    exclusions: list[SplitExclusion] = []
    group_partitions: dict[str, str] = {}
    prior_intervals: list[tuple[int, tuple[datetime, datetime]]] = []
    assigned: set[str] = set()
    for record in records:
        matching = [window for window in ordered_windows if _parse(window.start) <= _parse(record.observation_time) < _parse(window.end)]
        if not matching:
            exclusions.append(SplitExclusion(record.record_id, "outside_split_windows"))
            continue
        window = matching[0]
        window_index = ordered_windows.index(window)
        if _parse(record.horizon_end) > _parse(window.end):
            exclusions.append(SplitExclusion(record.record_id, "label_exceeds_partition_end"))
            continue
        if record.record_id in assigned:
            exclusions.append(SplitExclusion(record.record_id, "duplicate_record"))
            continue
        prior_group_window = group_partitions.get(record.group_id)
        if prior_group_window is not None and prior_group_window != window.name:
            exclusions.append(SplitExclusion(record.record_id, "group_reused_across_partitions"))
            continue
        interval = (_parse(record.observation_time), _parse(record.horizon_end))
        if any(index < window_index and _overlap(interval, previous) for index, previous in prior_intervals):
            exclusions.append(SplitExclusion(record.record_id, "purged_label_horizon_overlap"))
            continue
        partitions[window.name].append(record.record_id)
        assigned.add(record.record_id)
        group_partitions[record.group_id] = window.name
        prior_intervals.append((window_index, interval))
    payload = {
        "partitions": {name: ids for name, ids in partitions.items()},
        "exclusions": [exclusion.__dict__ for exclusion in exclusions],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return SplitManifest({name: tuple(ids) for name, ids in partitions.items()}, tuple(exclusions), digest)


def _overlap(left: tuple[datetime, datetime], right: tuple[datetime, datetime]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("split timestamps must include a timezone")
    return parsed
