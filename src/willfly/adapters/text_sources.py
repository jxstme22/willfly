"""Safe boundary for public text extraction inputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextSourceRecord:
    source_url: str
    content: str
    published_at: str | None
    retrieved_at: str
    permitted: bool


def accept_text_source(record: TextSourceRecord) -> TextSourceRecord:
    if not record.permitted:
        raise ValueError("source content is not permitted for archival")
    if not record.source_url or not record.content:
        raise ValueError("text source requires URL and content")
    return record
