"""Canonical and orphaned projections for block-linked raw evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from willfly.domain import RawEvent
from willfly.storage.raw import BlockHeader


class CanonicalizationError(ValueError):
    """Raised when a fork projection cannot be determined from supplied headers."""


@dataclass(frozen=True)
class CanonicalizationResult:
    tip_hash: str
    canonical_events: tuple[RawEvent, ...]
    orphaned_events: tuple[RawEvent, ...]
    confirmed_events: tuple[RawEvent, ...]
    provisional_events: tuple[RawEvent, ...]
    quarantined_events: tuple[RawEvent, ...]
    unresolved_events: tuple[RawEvent, ...]
    canonical_hashes: tuple[str, ...]
    missing_parent_hashes: tuple[str, ...]
    unknown_parent_headers: tuple[str, ...]

    @property
    def is_resolved(self) -> bool:
        """Whether the selected tip reaches a known root without an ancestry gap."""

        return not self.missing_parent_hashes and not self.unknown_parent_headers


def canonicalize_events(
    events: Iterable[RawEvent],
    *,
    tip_hash: str,
    headers: Iterable[BlockHeader] = (),
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
    header_map: dict[str, BlockHeader] = {}
    for header in headers:
        _merge_header(header_map, header)
    for event in records:
        if event.block_hash is None:
            raise CanonicalizationError("canonicalization requires block hashes")
        if event.block_number is None:
            raise CanonicalizationError("canonicalization requires block numbers")
        header = BlockHeader(
            event.block_number,
            event.block_hash,
            event.parent_hash,
            parent_known=event.parent_hash is not None or event.block_number == 0,
        )
        _merge_header(header_map, header)
    if tip_hash not in header_map:
        raise CanonicalizationError("tip hash is not present in supplied evidence")

    chain: list[BlockHeader] = []
    missing: list[str] = []
    unknown: list[str] = []
    current = header_map[tip_hash]
    seen_hashes: set[str] = set()
    while True:
        if current.block_hash in seen_hashes:
            raise CanonicalizationError("block parent cycle detected")
        seen_hashes.add(current.block_hash)
        chain.append(current)
        if not current.parent_known:
            unknown.append(current.block_hash)
            break
        if current.parent_hash is None:
            break
        parent = header_map.get(current.parent_hash)
        if parent is None:
            missing.append(current.parent_hash)
            break
        if parent.block_hash in seen_hashes:
            raise CanonicalizationError("block parent cycle detected")
        if parent.number >= current.number:
            raise CanonicalizationError("block parent number is not lower than child")
        current = parent
    resolved = not missing and not unknown
    canonical_hashes = {header.block_hash for header in chain} if resolved else set()
    tip_number = header_map[tip_hash].number
    confirmed_through = tip_number - confirmations
    canonical: list[RawEvent] = []
    orphaned: list[RawEvent] = []
    confirmed: list[RawEvent] = []
    provisional: list[RawEvent] = []
    quarantined: list[RawEvent] = []
    unresolved: list[RawEvent] = []
    for event in records:
        if event.canonical_status == "quarantined":
            quarantined.append(event)
            continue
        if not resolved:
            # A partial tip path cannot prove either inclusion or exclusion of
            # any observed branch. Keep all non-quarantined evidence provisional
            # and expose the gap rather than orphaning unrelated history.
            unresolved.append(replace(event, canonical_status="provisional"))
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
        unresolved_events=tuple(unresolved),
        canonical_hashes=tuple(header.block_hash for header in reversed(chain)) if resolved else (),
        missing_parent_hashes=tuple(dict.fromkeys(missing)),
        unknown_parent_headers=tuple(dict.fromkeys(unknown)),
    )


def _merge_header(headers: dict[str, BlockHeader], candidate: BlockHeader) -> None:
    existing = headers.get(candidate.block_hash)
    if existing is None:
        headers[candidate.block_hash] = candidate
        return
    if existing.number != candidate.number:
        raise CanonicalizationError(f"conflicting header for block {candidate.block_hash}")
    if existing.parent_known and candidate.parent_known and existing.parent_hash != candidate.parent_hash:
        raise CanonicalizationError(f"conflicting header for block {candidate.block_hash}")
    if existing.timestamp is not None and candidate.timestamp is not None and existing.timestamp != candidate.timestamp:
        raise CanonicalizationError(f"conflicting header for block {candidate.block_hash}")
    headers[candidate.block_hash] = BlockHeader(
        candidate.number,
        candidate.block_hash,
        existing.parent_hash if existing.parent_known else candidate.parent_hash,
        existing.timestamp if existing.timestamp is not None else candidate.timestamp,
        existing.parent_known or candidate.parent_known,
    )
