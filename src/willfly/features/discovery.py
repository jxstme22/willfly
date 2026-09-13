"""Launch and pool projections that preserve lifecycle missingness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from willfly.domain import Launch, PoolIdentity, RawEvent


@dataclass(frozen=True)
class PoolProjection:
    identity: PoolIdentity
    first_observed_at: str
    trading_status: str
    raw_event_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _parse(self.first_observed_at)
        if self.trading_status not in {"active", "inactive", "unknown"}:
            raise ValueError("unsupported pool trading status")
        if not self.raw_event_refs:
            raise ValueError("pool projection requires raw evidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_dict(),
            "first_observed_at": self.first_observed_at,
            "trading_status": self.trading_status,
            "raw_event_refs": list(self.raw_event_refs),
        }


@dataclass(frozen=True)
class DiscoverySnapshot:
    as_of_time: str
    launches: tuple[Launch, ...]
    pools: tuple[PoolProjection, ...]
    canonical_event_count: int
    unknown_lifecycle_count: int
    missingness: tuple[str, ...]
    quality_state: str
    lineage: tuple[str, ...]

    def __post_init__(self) -> None:
        _parse(self.as_of_time)
        if self.canonical_event_count < 0 or self.unknown_lifecycle_count < 0:
            raise ValueError("discovery counters cannot be negative")
        if self.quality_state not in {"healthy", "stale", "degraded", "unknown"}:
            raise ValueError("unsupported discovery quality state")
        if not self.lineage:
            raise ValueError("discovery snapshot requires lineage")


def build_discovery_snapshot(
    launches: Iterable[Launch],
    pools: Iterable[PoolProjection],
    *,
    as_of_time: str,
    canonical_events: Iterable[RawEvent] = (),
) -> DiscoverySnapshot:
    """Build an availability cutoff without backfilling future lifecycle facts."""

    cutoff = _parse(as_of_time)
    launch_records = tuple(launches)
    pool_records = tuple(pools)
    canonical_records = tuple(canonical_events)
    included_launches = tuple(sorted(
        (launch for launch in launch_records if _parse(launch.first_seen_at) <= cutoff),
        key=lambda launch: (launch.first_seen_at, launch.token.lower()),
    ))
    included_pools = tuple(sorted(
        (pool for pool in pool_records if _parse(pool.first_observed_at) <= cutoff),
        key=lambda pool: (pool.first_observed_at, pool.identity.pool_id or pool.identity.pool_address or ""),
    ))
    canonical = tuple(event for event in canonical_records if event.canonical_status == "canonical")
    missingness: list[str] = []
    if not launch_records:
        missingness.append("launch_history_unavailable")
    if not pool_records:
        missingness.append("pool_history_unavailable")
    if not canonical_records:
        missingness.append("canonical_event_reconciliation_unavailable")
    unknown_lifecycle = sum(launch.lifecycle_state == "unknown" for launch in included_launches)
    if unknown_lifecycle:
        missingness.append("launch_lifecycle_unknown")
    lineage = tuple(ref for launch in included_launches for ref in launch.creation_evidence)
    lineage += tuple(ref for pool in included_pools for ref in pool.raw_event_refs)
    lineage += tuple(event.logical_key[2] or "canonical-event" for event in canonical)
    if not lineage:
        lineage = (f"discovery:{as_of_time}",)
    quality_state = "degraded" if missingness else "healthy"
    return DiscoverySnapshot(
        as_of_time=as_of_time,
        launches=included_launches,
        pools=included_pools,
        canonical_event_count=len(canonical),
        unknown_lifecycle_count=unknown_lifecycle,
        missingness=tuple(dict.fromkeys(missingness)),
        quality_state=quality_state,
        lineage=tuple(dict.fromkeys(lineage)),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed
