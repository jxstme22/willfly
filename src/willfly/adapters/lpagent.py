"""Explicit capability matrix for optional LP Agent read access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ReadCapability:
    source: str
    endpoint: str | None
    status: str
    supported_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    terms_reference: str | None
    evidence_state: str

    def __post_init__(self) -> None:
        if self.status not in {"tested", "documented", "unavailable", "unsupported"}:
            raise ValueError("unsupported capability status")
        if self.evidence_state not in {"observed", "documented", "unknown"}:
            raise ValueError("unsupported capability evidence state")


def unavailable_capability(source: str, reason: str) -> ReadCapability:
    return ReadCapability(source, None, "unavailable", (), (reason,), None, "unknown")


def capability_matrix() -> tuple[ReadCapability, ...]:
    return (
        unavailable_capability("lpagent", "no_supported_robinhood_read_endpoint_verified"),
        unavailable_capability("rhtrenches", "no_supported_production_api_verified"),
        unavailable_capability("mezzanine", "no_supported_production_api_verified"),
    )
