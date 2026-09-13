"""Canonical and orphaned projections for block-linked raw evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from willfly.domain import RawEvent
from willfly.storage.raw import (
    AncestryAnchor,
    BlockHeader,
    parse_anchor_evidence,
)


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
    proven_height_range: tuple[int, int] | None = None

    @property
    def is_resolved(self) -> bool:
        """Whether the selected tip reaches a trusted boundary without a gap."""

        return (
            not self.missing_parent_hashes
            and not self.unknown_parent_headers
            and self.anchor_state == "qualified"
            and self.proven_height_range is not None
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
        and anchor_state == "qualified"
        and reached_anchor
    )
    canonical_hashes = {header.block_hash.lower() for header in chain} if resolved else set()
    tip_number = header_map[tip_hash].number
    confirmed_through = tip_number - confirmations
    proven_height_range = (
        (anchor.height, tip_number)
        if resolved and anchor is not None and anchor_state == "qualified" and reached_anchor
        else None
    )
    canonical_headers = {header.block_hash.lower(): header for header in chain}
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
        event_header = canonical_headers.get(event.block_hash.lower()) if event.block_hash else None
        if (
            event_header is not None
            and event.block_hash.lower() in canonical_hashes
            and event.block_number == event_header.number
        ):
            projected = replace(event, canonical_status="canonical")
            canonical.append(projected)
            if event.block_number <= confirmed_through:
                confirmed.append(projected)
            else:
                provisional.append(projected)
        elif proven_height_range is not None and (
            event.block_number < proven_height_range[0] or event.block_number > proven_height_range[1]
        ):
            # The selected tip and anchor prove only this interval. An event
            # observed before the anchor or after the selected tip is outside
            # the projection scope, not evidence of a competing branch.
            unresolved.append(replace(event, canonical_status="provisional"))
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
        proven_height_range=proven_height_range,
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
    if anchor.qualification == "operator_declared_unverified":
        evidence.append("operator-declared unverified anchor cannot certify canonical history")
        return "unverified"
    if anchor.qualification not in {"genesis", "independent_header_cross_check"}:
        evidence.append(f"anchor qualification {anchor.qualification!r} is unsupported")
        return "unsupported"
    if expected_chain_id is not None and anchor.chain_id != expected_chain_id:
        evidence.append(f"anchor chain {anchor.chain_id} does not match source chain {expected_chain_id}")
        return "config_mismatch"
    if expected_config_identity is not None and anchor.config_identity != expected_config_identity:
        evidence.append("anchor configuration identity does not match the active capture configuration")
        return "config_mismatch"
    header = next(
        (candidate for key, candidate in header_map.items() if key.lower() == anchor.block_hash.lower()),
        None,
    )
    if header is None:
        evidence.append("anchor block is not present in supplied header evidence")
        return "unavailable"
    if header.number != anchor.height:
        evidence.append(
            f"anchor height {anchor.height} does not match stored height {header.number}"
        )
        return "mismatch"
    try:
        records = [parse_anchor_evidence(item) for item in anchor.evidence]
    except ValueError as exc:
        evidence.append(str(exc))
        return "unqualified"

    if anchor.qualification == "genesis":
        if anchor.height != 0 or header.number != 0 or not header.parent_known or header.parent_hash is not None:
            evidence.append("genesis anchor must identify block 0 with a known null parent")
            return "unqualified"
        matching = next((record for record in records if record.get("kind") == "genesis_header"), None)
        if matching is None or not _matches_identity(matching, anchor, expected_chain_id):
            evidence.append("genesis evidence does not match the active chain/header identity")
            return "unqualified"
        evidence.append(f"genesis header {anchor.block_hash} at height 0 satisfies the local genesis invariant")
        return "qualified"

    matching = next(
        (record for record in records if record.get("kind") == "independent_header_cross_check"), None
    )
    if matching is None or not _matches_identity(matching, anchor, expected_chain_id):
        evidence.append("independent header evidence is missing or does not match the active identity")
        return "unqualified"
    primary_endpoint = matching.get("primary_endpoint")
    independent_endpoint = matching.get("independent_endpoint")
    read_methods = matching.get("read_methods")
    external_header = matching.get("external_header")
    primary_header = matching.get("primary_header")
    if (
        not isinstance(primary_endpoint, str)
        or not primary_endpoint.strip()
        or not isinstance(independent_endpoint, str)
        or not independent_endpoint.strip()
        or primary_endpoint.strip().lower() == independent_endpoint.strip().lower()
        or not isinstance(read_methods, list)
        or read_methods != ["eth_chainId", "eth_getBlockByNumber"]
        or matching.get("verification") != "performed_rpc_cross_check"
        or matching.get("trust_policy") != "distinct_configured_endpoints_operator_assumption"
        or matching.get("finality_status") != "not_verified"
        or not _header_evidence_matches(external_header, anchor=anchor, header=header)
        or not _header_evidence_matches(primary_header, anchor=anchor, header=header)
    ):
        evidence.append("independent RPC evidence lacks two distinct performed identity checks")
        return "unqualified"
    evidence.append(
        f"anchor {anchor.block_hash} at height {anchor.height} qualified by performed RPC identity checks"
    )
    return "qualified"


def assess_ancestry_anchor(
    anchor: AncestryAnchor | None,
    headers: Iterable[BlockHeader],
    *,
    expected_chain_id: int | None = None,
    expected_config_identity: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Return a fail-closed anchor state and its reviewable evidence."""

    header_map: dict[str, BlockHeader] = {}
    for header in headers:
        _merge_header(header_map, header)
    evidence: list[str] = []
    state = _anchor_state(anchor, header_map, expected_chain_id, expected_config_identity, evidence)
    return state, tuple(dict.fromkeys(evidence))


def _matches_identity(
    record: dict[str, object], anchor: AncestryAnchor, expected_chain_id: int | None
) -> bool:
    return (
        type(record.get("chain_id")) is int
        and record.get("chain_id") == anchor.chain_id
        and (expected_chain_id is None or record.get("chain_id") == expected_chain_id)
        and type(record.get("config_identity")) is str
        and record.get("config_identity") == anchor.config_identity
        and type(record.get("height")) is int
        and record.get("height") == anchor.height
        and _same_hash(record.get("block_hash"), anchor.block_hash)
    )


def _same_hash(left: object, right: str) -> bool:
    return type(left) is str and left.lower() == right.lower()


def _same_optional_hash(left: object, right: str | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return type(left) is str and left.lower() == right.lower()


def _header_evidence_matches(
    value: object, *, anchor: AncestryAnchor, header: BlockHeader
) -> bool:
    """Validate nested header shape before applying Python equality."""

    if not isinstance(value, dict):
        return False
    if set(value) - {"number", "hash", "parent_hash"}:
        return False
    number = value.get("number")
    if type(number) is not int or number != anchor.height:
        return False
    if not _same_hash(value.get("hash"), anchor.block_hash):
        return False
    if "parent_hash" in value and not _same_optional_hash(value.get("parent_hash"), header.parent_hash):
        return False
    return True


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
