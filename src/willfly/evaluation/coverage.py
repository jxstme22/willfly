"""Provider-independent recorder coverage checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from willfly.domain import RawEvent


@dataclass(frozen=True)
class CoverageAudit:
    """A bounded audit result with explicit exclusions and independence state."""

    expected_count: int
    observed_count: int
    matched_count: int
    recall: float | None
    missing_keys: tuple[tuple[int, str | None, str | None, int | None], ...]
    duplicate_keys: tuple[tuple[int, str | None, str | None, int | None], ...]
    quarantined_count: int
    provider_independent: bool
    state: str
    notes: tuple[str, ...]


def audit_coverage(
    expected: Iterable[RawEvent],
    observed: Iterable[RawEvent],
    *,
    provider_independent: bool,
    quarantined: Iterable[RawEvent] = (),
) -> CoverageAudit:
    """Compare configured-interval evidence to a separately fetched projection.

    The expected and observed iterables are intentionally kept as raw records:
    callers can choose canonical records before invoking the audit, while
    quarantined rows remain visible as exclusions rather than becoming misses.
    """

    expected_records = tuple(expected)
    observed_records = tuple(observed)
    quarantined_records = tuple(quarantined)
    expected_keys = tuple(record.logical_key for record in expected_records)
    expected_set = set(expected_keys)
    observed_keys = tuple(record.logical_key for record in observed_records)
    observed_set = set(observed_keys)
    counts: dict[tuple[int, str | None, str | None, int | None], int] = {}
    for key in observed_keys:
        counts[key] = counts.get(key, 0) + 1
    duplicate_keys = tuple(sorted(key for key, count in counts.items() if count > 1))
    missing_keys = tuple(key for key in expected_keys if key not in observed_set)
    matched_count = len(expected_set & observed_set)
    notes: list[str] = []
    if not expected_records:
        notes.append("empty_reference_cannot_establish_coverage")
    if not provider_independent:
        notes.append("provider_independence_unverified")
    if missing_keys:
        notes.append("expected_records_missing")
    if duplicate_keys:
        notes.append("duplicate_delivery_detected")
    if quarantined_records:
        notes.append("quarantined_records_excluded")
    state = "pass" if provider_independent and expected_records and not missing_keys and not duplicate_keys and not quarantined_records else "degraded"
    return CoverageAudit(
        expected_count=len(expected_records),
        observed_count=len(observed_records),
        matched_count=matched_count,
        recall=None if not expected_records else matched_count / len(expected_records),
        missing_keys=missing_keys,
        duplicate_keys=duplicate_keys,
        quarantined_count=len(quarantined_records),
        provider_independent=provider_independent,
        state=state,
        notes=tuple(notes),
    )
