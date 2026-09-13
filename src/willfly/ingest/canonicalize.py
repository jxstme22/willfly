"""Canonical and orphaned projections for block-linked raw evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from willfly.domain import RawEvent


class CanonicalizationError(ValueError):
    """Raised when a fork projection cannot be determined from supplied headers."""


@dataclass(frozen=True)
class BlockHeader:
    number: int
    block_hash: str
    parent_hash: str | None


@dataclass(frozen=True)
class CanonicalizationResult:
    tip_hash: str
    canonical_events: tuple[RawEvent, ...]
    orphaned_events: tuple[RawEvent, ...]
    confirmed_events: tuple[RawEvent, ...]
    provisional_events: tuple[RawEvent, ...]
    quarantined_events: tuple[RawEvent, ...]
    canonical_hashes: tuple[str, ...]
    missing_parent_hashes: tuple[str, ...]


def canonicalize_events(
    events: Iterable[RawEvent],
    *,
    tip_hash: str,
    confirmations: int = 0,
) -> CanonicalizationResult:
    """Project a supplied tip chain while retaining all fork evidence.

    The caller supplies a tip from a chain/header source. A missing parent is a
    visible gap, not an implicit canonical root. Events marked quarantined are
    never promoted into a canonical projection.
    """

    if confirmations < 0:
        raise ValueError("confirmations cannot be negative")
    records = tuple(events)
    headers: dict[str, BlockHeader] = {}
    for event in records:
        if event.block_hash is None:
            raise CanonicalizationError("canonicalization requires block hashes")
        header = BlockHeader(event.block_number, event.block_hash, event.parent_hash)
        existing = headers.get(event.block_hash)
        if existing is not None and existing != header:
            raise CanonicalizationError(f"conflicting header for block {event.block_hash}")
        headers[event.block_hash] = header
    if tip_hash not in headers:
        raise CanonicalizationError("tip hash is not present in supplied evidence")

    chain: list[BlockHeader] = []
    missing: list[str] = []
    current = headers[tip_hash]
    seen_hashes: set[str] = set()
    while True:
        if current.block_hash in seen_hashes:
            raise CanonicalizationError("block parent cycle detected")
        seen_hashes.add(current.block_hash)
        chain.append(current)
        if current.parent_hash is None:
            break
        parent = headers.get(current.parent_hash)
        if parent is None:
            missing.append(current.parent_hash)
            break
        if parent.block_hash in seen_hashes:
            raise CanonicalizationError("block parent cycle detected")
        if parent.number >= current.number:
            raise CanonicalizationError("block parent number is not lower than child")
        current = parent
    canonical_hashes = {header.block_hash for header in chain}
    tip_number = headers[tip_hash].number
    confirmed_through = tip_number - confirmations
    canonical: list[RawEvent] = []
    orphaned: list[RawEvent] = []
    confirmed: list[RawEvent] = []
    provisional: list[RawEvent] = []
    quarantined: list[RawEvent] = []
    for event in records:
        if event.canonical_status == "quarantined":
            quarantined.append(event)
            continue
        if event.block_hash in canonical_hashes:
            projected = replace(event, canonical_status="canonical")
            canonical.append(projected)
            if event.block_number <= confirmed_through:
                confirmed.append(projected)
            else:
                provisional.append(projected)
        else:
            orphaned.append(replace(event, canonical_status="orphaned"))
    return CanonicalizationResult(
        tip_hash=tip_hash,
        canonical_events=tuple(canonical),
        orphaned_events=tuple(orphaned),
        confirmed_events=tuple(confirmed),
        provisional_events=tuple(provisional),
        quarantined_events=tuple(quarantined),
        canonical_hashes=tuple(header.block_hash for header in reversed(chain)),
        missing_parent_hashes=tuple(dict.fromkeys(missing)),
    )
