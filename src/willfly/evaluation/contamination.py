"""Historical contamination audit for text/LLM features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from willfly.features.text_schema import TextClaim


@dataclass(frozen=True)
class ContaminationAudit:
    usable_claim_ids: tuple[str, ...]
    excluded_claim_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    state: str


def audit_claim_times(claims: Iterable[TextClaim], *, feature_cutoff: str) -> ContaminationAudit:
    cutoff = _parse(feature_cutoff)
    usable: list[str] = []
    excluded: list[str] = []
    reasons: list[str] = []
    for claim in claims:
        if (
            _parse(claim.published_at or claim.retrieved_at) <= cutoff
            and _parse(claim.retrieved_at) <= cutoff
            and _parse(claim.retrieved_at) >= _parse(claim.published_at or claim.retrieved_at)
        ):
            usable.append(claim.claim_id)
        else:
            excluded.append(claim.claim_id)
            reasons.append("claim_after_feature_cutoff")
    return ContaminationAudit(tuple(usable), tuple(excluded), tuple(dict.fromkeys(reasons)), "pass" if not excluded else "degraded")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("claim timestamps must include a timezone")
    return parsed
