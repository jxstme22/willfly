"""Canonical and orphaned projections for block-linked raw evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from willfly.domain import RawEvent
from willfly.storage.raw import AncestryAnchor, BlockHeader, UNSATISFIED_ANCHOR_STATES


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
    anchor_state: str = "unavailable"
    anchor_evidence: tuple[str, ...] = ()

    @property
    def is_resolved(self) -> bool:
        """Whether the selected tip reaches a trusted boundary without a gap."""

        return (
            not self.missing_parent_hashes
            and not self.unknown_parent_headers
            and self.anchor_state not in UNSATISFIED_ANCHOR_STATES
        )


def canonicalize_events(
    events: Iterable[RawEvent],
    *,
    tip_hash: str,
    headers: Iterable[BlockHeader] = (),
    confirmations: int = 0,
    anchor: AncestryAnchor | None = None,
    expected_chain_id: int | None = None,
    expected_config_identity: str | None = None,
) -> CanonicalizationResult:
    """Project a supplied tip chain while retaining all fork evidence.

    The caller supplies a tip from a chain/header source. A missing parent is a
    visible gap, not an implicit canonical root. Events marked quarantined are
    never promoted into a canonical projection.

    A bounded window resolves only when its parent walk reaches a supplied,
    qualified :class:`AncestryAnchor`. Without an anchor the walk stops at the
    oldest available header and the projection stays *unresolved* rather than
    declaring an arbitrary oldest header a trusted root. Consecutive parent
    heights are required, and a fork that reaches or crosses the anchor
    boundary invalidates the projection explicitly.
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

    anchor_evidence: list[str] = []
    anchor_state = _anchor_state(anchor, header_map, expected_chain_id, expected_config_identity, anchor_evidence)

    chain: list[BlockHeader] = []
    missing: list[str] = []
    unknown: list[str] = []
    nonconsecutive: list[str] = []
    current = header_map[tip_hash]
    seen_hashes: set[str] = set()
    anchor_hash_lower = anchor.block_hash.lower() if anchor is not None else None
    reached_anchor = False
    while True:
        if current.block_hash in seen_hashes:
            raise CanonicalizationError("block parent cycle detected")
        seen_hashes.add(current.block_hash)
        chain.append(current)
        # A qualified anchor is the trusted root. Reaching it resolves the walk.
        if anchor_hash_lower is not None and current.block_hash.lower() == anchor_hash_lower:
            reached_anchor = True
            break
        if anchor is not None and anchor_state == "qualified" and current.number <= anchor.height:
            # We have descended to the anchor height (or below) on a branch that
            # is not the anchored block: the fork reaches/crosses the trusted
            # boundary, so that boundary cannot gate this branch.
            anchor_state = "boundary_crossed"
            anchor_evidence.append(
                f"observed block {current.block_hash} at height {current.number} "
                f"diverges at or below anchor height {anchor.height}"
            )
            break
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
        # Consecutive parent heights are required: a jump means the interior
        # ancestry is not actually available even if a same-hash header exists.
        if parent.number != current.number - 1:
            nonconsecutive.append(current.parent_hash)
            missing.append(current.parent_hash)
            break
        current = parent

    if anchor is not None and not reached_anchor and anchor_state == "qualified":
        # The walk ended (gap, unknown or boundary) without reaching the anchor.
        if not missing and not unknown and not nonconsecutive:
            anchor_state = "unqualified"
    if nonconsecutive and anchor_state == "qualified":
        anchor_state = "nonconsecutive"

    resolved = (
        not missing
        and not unknown
        and anchor_state not in UNSATISFIED_ANCHOR_STATES
    )
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
        anchor_state=anchor_state,
        anchor_evidence=tuple(dict.fromkeys(anchor_evidence)),
    )


def _anchor_state(
    anchor: AncestryAnchor | None,
    header_map: dict[str, BlockHeader],
    expected_chain_id: int | None,
    expected_config_identity: str | None,
    evidence: list[str],
) -> str:
    """Validate a declared anchor against supplied evidence without inventing trust."""

    if anchor is None:
        evidence.append("no verified ancestry anchor recorded for this source")
        return "unavailable"
    if expected_chain_id is not None and anchor.chain_id != expected_chain_id:
        evidence.append(f"anchor chain {anchor.chain_id} does not match source chain {expected_chain_id}")
        return "config_mismatch"
    if expected_config_identity is not None and anchor.config_identity != expected_config_identity:
        evidence.append("anchor configuration identity does not match the active capture configuration")
        return "config_mismatch"
    header = header_map.get(anchor.block_hash)
    if header is None:
        evidence.append("anchor block is not present in supplied header evidence")
        return "unavailable"
    if header.number != anchor.height:
        evidence.append(
            f"anchor height {anchor.height} does not match stored height {header.number}"
        )
        return "mismatch"
    evidence.append(
        f"anchor {anchor.block_hash} at height {anchor.height} qualified via {anchor.qualification}"
    )
    return "qualified"


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
