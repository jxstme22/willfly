"""Source-span-backed text claims, separate from market outcomes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextClaim:
    claim_id: str
    subject_id: str
    claim_type: str
    text: str
    source_url: str
    source_span: str
    published_at: str | None
    retrieved_at: str
    confidence_bps: int
    contradictions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.claim_type not in {"narrative", "risk", "catalyst", "contradiction", "unknown"}:
            raise ValueError("unsupported text claim type")
        if not all((self.claim_id, self.subject_id, self.text, self.source_url, self.source_span)):
            raise ValueError("text claims require source-backed identity and span")
        if not 0 <= self.confidence_bps <= 10_000:
            raise ValueError("confidence must be basis points")
        if self.published_at is None:
            raise ValueError("published_at is required for retrospective text features")
