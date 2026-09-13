"""Immutable causal Observatory projections built from reconciled evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from willfly.domain import Launch, Observation, PoolIdentity, RawEvent, TradeEvidence, WalletCohort
from willfly.features.discovery import DiscoverySnapshot, PoolProjection, build_discovery_snapshot
from willfly.features.timelines import build_token_timeline


@dataclass(frozen=True)
class LifecycleRevision:
    """An observed lifecycle fact, distinct from mutable current launch state."""

    token: str
    lifecycle_state: str
    observed_at: str
    raw_references: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.lifecycle_state not in {"active", "graduated", "non_graduate", "unknown"}:
            raise ValueError("unsupported lifecycle state")
        _instant(self.observed_at)
        if not self.raw_references:
            raise ValueError("lifecycle revision requires raw references")

    def to_dict(self) -> dict[str, object]:
        return {
            "token": self.token,
            "lifecycle_state": self.lifecycle_state,
            "observed_at": self.observed_at,
            "raw_references": list(self.raw_references),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "LifecycleRevision":
        return cls(
            token=str(data["token"]),
            lifecycle_state=str(data["lifecycle_state"]),
            observed_at=str(data["observed_at"]),
            raw_references=tuple(str(value) for value in data["raw_references"]),
        )


@dataclass(frozen=True)
class ObservatoryProjection:
    """Portable, as-of bundle consumed by the local inspection surface."""

    as_of_time: str
    discovery: DiscoverySnapshot
    timelines: tuple[Observation, ...]
    exclusions: tuple[Mapping[str, object], ...]
    evidence: Mapping[str, Mapping[str, object]]

    def __post_init__(self) -> None:
        _instant(self.as_of_time)
        if self.discovery.as_of_time != self.as_of_time:
            raise ValueError("discovery snapshot cutoff must match projection cutoff")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "observatory-projection.v0.1",
            "as_of_time": self.as_of_time,
            "discovery": {
                "as_of_time": self.discovery.as_of_time,
                "launches": [launch.to_dict() for launch in self.discovery.launches],
                "pools": [pool.to_dict() for pool in self.discovery.pools],
                "canonical_event_count": self.discovery.canonical_event_count,
                "unknown_lifecycle_count": self.discovery.unknown_lifecycle_count,
                "missingness": list(self.discovery.missingness),
                "quality_state": self.discovery.quality_state,
                "lineage": list(self.discovery.lineage),
            },
            "timelines": [timeline.to_dict() for timeline in self.timelines],
            "exclusions": [dict(row) for row in self.exclusions],
            "evidence": {key: dict(value) for key, value in self.evidence.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ObservatoryProjection":
        if data.get("schema_version") != "observatory-projection.v0.1":
            raise ValueError("unsupported Observatory projection schema")
        discovery_data = _mapping(data.get("discovery"), "discovery")
        pools = tuple(
            PoolProjection(
                identity=PoolIdentity.from_dict(_mapping(item.get("identity"), "pool.identity")),
                first_observed_at=str(item["first_observed_at"]),
                trading_status=str(item["trading_status"]),
                raw_event_refs=tuple(str(value) for value in item["raw_event_refs"]),
            )
            for item in _sequence(discovery_data.get("pools"), "discovery.pools")
            if isinstance(item, Mapping)
        )
        discovery = DiscoverySnapshot(
            as_of_time=str(discovery_data["as_of_time"]),
            launches=tuple(Launch.from_dict(item) for item in _sequence(discovery_data.get("launches"), "discovery.launches") if isinstance(item, Mapping)),
            pools=pools,
            canonical_event_count=int(discovery_data["canonical_event_count"]),
            unknown_lifecycle_count=int(discovery_data["unknown_lifecycle_count"]),
            missingness=tuple(str(value) for value in _sequence(discovery_data.get("missingness"), "discovery.missingness")),
            quality_state=str(discovery_data["quality_state"]),
            lineage=tuple(str(value) for value in _sequence(discovery_data.get("lineage"), "discovery.lineage")),
        )
        return cls(
            as_of_time=str(data["as_of_time"]),
            discovery=discovery,
            timelines=tuple(Observation.from_dict(item) for item in _sequence(data.get("timelines"), "timelines") if isinstance(item, Mapping)),
            exclusions=tuple(dict(item) for item in _sequence(data.get("exclusions"), "exclusions") if isinstance(item, Mapping)),
            evidence={str(key): dict(value) for key, value in _mapping(data.get("evidence"), "evidence").items() if isinstance(value, Mapping)},
        )


def materialize_observatory_projection(
    *,
    as_of_time: str,
    launches: Iterable[Launch],
    pools: Iterable[PoolProjection],
    raw_events: Iterable[RawEvent],
    trades: Iterable[TradeEvidence],
    lifecycle_revisions: Iterable[LifecycleRevision] = (),
    cohorts: Iterable[WalletCohort] | None = None,
    cohort_id: str | None = None,
) -> ObservatoryProjection:
    """Build an as-of bundle without admitting future or noncanonical facts."""

    cutoff = _instant(as_of_time)
    raw_records = tuple(raw_events)
    canonical = tuple(event for event in raw_records if event.canonical_status == "canonical")
    excluded: list[Mapping[str, object]] = [
        {
            "kind": "raw_event",
            "logical_key": list(event.logical_key),
            "canonical_status": event.canonical_status,
            "reason": "noncanonical_raw_evidence",
        }
        for event in raw_records
        if event.canonical_status != "canonical"
    ]
    projected_launches = _launches_as_of(launches, lifecycle_revisions, cutoff)
    discovery = build_discovery_snapshot(
        projected_launches,
        pools,
        as_of_time=as_of_time,
        canonical_events=canonical,
    )
    trade_records = tuple(trades)
    for trade in trade_records:
        if trade.classification == "genuine_swap" and (
            trade.route_status != "verified" or trade.trade_direction == "unknown" or trade.method_version != "trade-evidence.v0.2"
        ):
            excluded.append(
                {
                    "kind": "trade",
                    "transaction_hash": trade.transaction_hash,
                    "reason": "unverified_trade_evidence",
                    "route_status": trade.route_status,
                    "method_version": trade.method_version,
                }
            )
    tokens = sorted({launch.token for launch in projected_launches} | {trade.token for trade in trade_records})
    timelines = tuple(
        build_token_timeline(
            trade_records,
            token=token,
            event_cutoff=as_of_time,
            arrival_cutoff=as_of_time,
            cohorts=cohorts,
            cohort_id=cohort_id,
        )
        for token in tokens
    )
    evidence = {
        _raw_evidence_key(event): {
            "kind": "raw_event",
            "logical_key": list(event.logical_key),
            "canonical_status": event.canonical_status,
            "source": event.source,
            "received_time": event.received_time,
        }
        for event in raw_records
    }
    for revision in lifecycle_revisions:
        if _instant(revision.observed_at) <= cutoff:
            for reference in revision.raw_references:
                evidence.setdefault(reference, {"kind": "lifecycle_revision", "token": revision.token, "observed_at": revision.observed_at})
    return ObservatoryProjection(as_of_time, discovery, timelines, tuple(excluded), evidence)


def _launches_as_of(
    launches: Iterable[Launch], revisions: Iterable[LifecycleRevision], cutoff: datetime
) -> tuple[Launch, ...]:
    latest: dict[str, LifecycleRevision] = {}
    for revision in sorted(revisions, key=lambda item: _instant(item.observed_at)):
        if _instant(revision.observed_at) <= cutoff:
            latest[revision.token.lower()] = revision
    projected: list[Launch] = []
    for launch in launches:
        revision = latest.get(launch.token.lower())
        # Current mutable launch state is not a causal lifecycle observation.
        projected.append(replace(launch, lifecycle_state=revision.lifecycle_state if revision else "unknown"))
    return tuple(projected)


def _raw_evidence_key(event: RawEvent) -> str:
    return "raw:" + event.source + ":" + ":".join(str(value) for value in event.logical_key)


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array")
    return value
