"""Vendor claim normalization without upgrading claims into ground truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ScannerObservation:
    vendor: str
    subject_id: str
    observed_at: str | None
    retrieved_time: str
    reason_flags: tuple[str, ...]
    raw_payload: Mapping[str, Any]
    status: str

    def __post_init__(self) -> None:
        if self.vendor not in {"rhtrenches", "mezzanine"}:
            raise ValueError("unsupported scanner vendor")
        if self.status not in {"observed", "stale", "unavailable", "unknown"}:
            raise ValueError("unsupported scanner status")


def normalize_scanner_claim(vendor: str, subject_id: str, payload: Mapping[str, Any], *, retrieved_time: str) -> ScannerObservation:
    flags = payload.get("reason_flags", [])
    if not isinstance(flags, list) or not all(isinstance(flag, str) and flag for flag in flags):
        raise ValueError("scanner reason_flags must be non-empty strings")
    status = str(payload.get("status", "unknown"))
    if status not in {"observed", "stale", "unavailable", "unknown"}:
        status = "unknown"
    return ScannerObservation(vendor, subject_id, payload.get("source_as_of_time"), retrieved_time, tuple(flags), dict(payload), status)
