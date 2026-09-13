"""License- and ID-safe boundary for a future connectome release."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ConnectomeManifest:
    release_id: str | None
    source_url: str | None
    license_url: str | None
    source_sha256: str | None
    curated_filter: str
    status: str

    def __post_init__(self) -> None:
        if self.status not in {"verified", "pending_verification", "unavailable"}:
            raise ValueError("unsupported connectome manifest status")
        if self.status == "verified" and not all((self.release_id, self.source_url, self.license_url, self.source_sha256)):
            raise ValueError("verified connectome manifests require source and license metadata")


def validate_connectome_records(records: Iterable[Mapping[str, Any]], manifest: ConnectomeManifest) -> tuple[dict[str, Any], ...]:
    """Validate node IDs as text and preserve excluded records for accounting."""

    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record.get("source"), str) or not isinstance(record.get("target"), str):
            raise ValueError("connectome IDs must remain strings")
        if "weight" not in record or not isinstance(record["weight"], (int, float)):
            raise ValueError("connectome edge weight must be numeric")
        item = dict(record)
        item["included"] = bool(record.get("included", True))
        item["exclusion_reason"] = None if item["included"] else str(record.get("exclusion_reason", "filtered"))
        normalized.append(item)
    if manifest.status != "verified":
        raise ValueError("connectome manifest must be verified before records enter a claimed experiment")
    return tuple(normalized)
