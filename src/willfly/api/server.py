"""A small local HTTP surface for inspection, never execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping
from urllib.parse import parse_qs, unquote, urlparse

from willfly.domain import Launch, Observation, PredictionRecord, SignalProposal, WalletObservation
from willfly.domain.contracts import ADDRESS_RE, BYTES32_RE
from willfly.features.discovery import DiscoverySnapshot, PoolProjection
from willfly.features.projections import ObservatoryProjection
from willfly.storage.raw import RawBatchStore
from willfly.ui.dashboard import render_dashboard
from willfly.ui.signals import build_signal_inbox


@dataclass(frozen=True)
class ReadOnlyStore:
    launches: tuple[Launch, ...] = ()
    pools: tuple[PoolProjection, ...] = ()
    timelines: tuple[Observation, ...] = ()
    quality_state: str = "unknown"
    quality_details: dict[str, object] | None = None
    discovery_snapshot: DiscoverySnapshot | None = None
    exclusions: tuple[Mapping[str, object], ...] = ()
    evidence: Mapping[str, Mapping[str, object]] | None = None
    predictions: tuple[PredictionRecord, ...] = ()
    proposals: tuple[SignalProposal, ...] = ()
    signal_as_of_time: str | None = None
    market_readiness: Mapping[str, str] | None = None
    wallet_observations: tuple[WalletObservation, ...] = ()
    training_state: Mapping[str, object] | None = None

    @classmethod
    def from_discovery(
        cls,
        snapshot: DiscoverySnapshot,
        *,
        timelines: tuple[Observation, ...] = (),
        quality_details: dict[str, object] | None = None,
    ) -> "ReadOnlyStore":
        return cls(
            launches=snapshot.launches,
            pools=snapshot.pools,
            timelines=timelines,
            quality_state=snapshot.quality_state,
            quality_details=quality_details,
            discovery_snapshot=snapshot,
        )

    @classmethod
    def from_projection(cls, projection: ObservatoryProjection) -> "ReadOnlyStore":
        return cls(
            launches=projection.discovery.launches,
            pools=projection.discovery.pools,
            timelines=projection.timelines,
            quality_state=projection.discovery.quality_state,
            quality_details={
                "as_of_time": projection.as_of_time,
                "canonical_event_count": projection.discovery.canonical_event_count,
                "exclusion_count": len(projection.exclusions),
            },
            discovery_snapshot=projection.discovery,
            exclusions=projection.exclusions,
            evidence=projection.evidence,
        )

    @classmethod
    def from_persisted_snapshot(cls, store: RawBatchStore, snapshot_id: str) -> "ReadOnlyStore":
        return cls.from_projection(ObservatoryProjection.from_dict(store.load_snapshot(snapshot_id)))

    def list_launches(self, *, cursor: int, limit: int, lifecycle: str | None = None) -> dict[str, object]:
        if cursor < 0 or limit <= 0 or limit > 100:
            raise ValueError("cursor must be non-negative and limit must be between 1 and 100")
        records = [launch for launch in self.launches if lifecycle is None or launch.lifecycle_state == lifecycle]
        page = records[cursor : cursor + limit]
        next_cursor = cursor + len(page)
        return {
            "items": [launch.to_dict() for launch in page],
            "next_cursor": None if next_cursor >= len(records) else str(next_cursor),
            "total": len(records),
        }

    def get_timeline(self, token: str) -> Observation:
        if ADDRESS_RE.fullmatch(token) is None:
            raise ValueError("token must be an EVM address")
        for timeline in self.timelines:
            if timeline.subject_id.lower() == token.lower():
                return timeline
        raise KeyError(token)

    def get_pool(self, pool_id: str) -> PoolProjection:
        if BYTES32_RE.fullmatch(pool_id) is None:
            raise ValueError("pool_id must be a bytes32 value")
        for pool in self.pools:
            if pool.identity.pool_id and pool.identity.pool_id.lower() == pool_id.lower():
                return pool
        raise KeyError(pool_id)

    def list_exclusions(self, *, cursor: int, limit: int) -> dict[str, object]:
        if cursor < 0 or limit <= 0 or limit > 100:
            raise ValueError("cursor must be non-negative and limit must be between 1 and 100")
        page = self.exclusions[cursor : cursor + limit]
        next_cursor = cursor + len(page)
        return {
            "items": [dict(item) for item in page],
            "next_cursor": None if next_cursor >= len(self.exclusions) else str(next_cursor),
            "total": len(self.exclusions),
        }

    def get_evidence(self, reference: str) -> Mapping[str, object]:
        if not reference:
            raise ValueError("evidence reference is required")
        details = (self.evidence or {}).get(reference)
        if details is None:
            raise KeyError(reference)
        return details

    def list_signals(self, *, cursor: int, limit: int) -> dict[str, object]:
        if cursor < 0 or limit <= 0 or limit > 100:
            raise ValueError("cursor must be non-negative and limit must be between 1 and 100")
        as_of = self.signal_as_of_time or self.quality_details.get("as_of_time", "1970-01-01T00:00:00Z") if self.quality_details else "1970-01-01T00:00:00Z"
        entries = build_signal_inbox(
            self.predictions,
            self.proposals,
            as_of_time=as_of,
            market_readiness=self.market_readiness,
        )
        page = entries[cursor : cursor + limit]
        next_cursor = cursor + len(page)
        return {
            "items": [entry.to_dict() for entry in page],
            "next_cursor": None if next_cursor >= len(entries) else str(next_cursor),
            "total": len(entries),
            "as_of_time": as_of,
        }

    def list_positions(self, *, wallet: str | None = None) -> dict[str, object]:
        observations = self.wallet_observations
        if wallet is not None:
            observations = tuple(item for item in observations if item.wallet.lower() == wallet.lower())
        return {
            "items": [position.to_dict() | {"wallet": observation.wallet} for observation in observations for position in observation.positions],
            "observation_count": len(observations),
        }

    def training(self) -> dict[str, object]:
        return dict(self.training_state or {"status": "unknown", "reason": "training_state_unavailable"})

    def dashboard(self) -> str:
        snapshot = self.discovery_snapshot or DiscoverySnapshot(
            as_of_time="1970-01-01T00:00:00Z",
            launches=self.launches,
            pools=self.pools,
            canonical_event_count=0,
            unknown_lifecycle_count=sum(launch.lifecycle_state == "unknown" for launch in self.launches),
            missingness=("persisted_projection_unavailable",),
            quality_state=self.quality_state,
            lineage=("dashboard:empty",),
        )
        as_of = self.signal_as_of_time or snapshot.as_of_time
        signals = build_signal_inbox(self.predictions, self.proposals, as_of_time=as_of, market_readiness=self.market_readiness)
        positions = [position.to_dict() | {"wallet": observation.wallet} for observation in self.wallet_observations for position in observation.positions]
        return render_dashboard(snapshot, self.timelines, self.exclusions, signals=signals, positions=tuple(positions), training_state=self.training_state)


def create_server(*, store: ReadOnlyStore, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a local-only-by-default server with GET endpoints only."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if urlparse(self.path).path in {"/", "/dashboard"}:
                body = store.dashboard().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            try:
                payload, status = _route(store, self.path)
            except KeyError as exc:
                payload, status = {"status": "error", "error": str(exc)}, 404
            except ValueError as exc:
                payload, status = {"status": "error", "error": str(exc)}, 400
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload, sort_keys=True).encode())

        def do_POST(self) -> None:  # noqa: N802 - explicit read-only rejection
            self.send_error(405, "read-only API")

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def _route(store: ReadOnlyStore, path: str) -> tuple[dict[str, object], int]:
    parsed = urlparse(path)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    params = parse_qs(parsed.query)
    if parts == ["health"]:
        return {
            "status": "ok" if store.quality_state == "healthy" else store.quality_state,
            "quality_state": store.quality_state,
            "details": store.quality_details or {},
        }, 200
    if parts == ["launches"]:
        return store.list_launches(
            cursor=_int_param(params, "cursor", 0),
            limit=_int_param(params, "limit", 25),
            lifecycle=_single_param(params, "lifecycle"),
        ), 200
    if len(parts) == 3 and parts[0] == "tokens" and parts[2] == "timeline":
        timeline = store.get_timeline(parts[1])
        return timeline.to_dict(), 200
    if len(parts) == 2 and parts[0] == "pools":
        pool = store.get_pool(parts[1])
        return {
            "identity": pool.identity.to_dict(),
            "first_observed_at": pool.first_observed_at,
            "trading_status": pool.trading_status,
            "raw_event_refs": list(pool.raw_event_refs),
        }, 200
    if parts == ["exclusions"]:
        return store.list_exclusions(cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25)), 200
    if parts == ["signals"]:
        return store.list_signals(cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25)), 200
    if parts == ["positions"]:
        return store.list_positions(wallet=_single_param(params, "wallet")), 200
    if parts == ["training"]:
        return store.training(), 200
    if len(parts) == 2 and parts[0] == "evidence":
        return dict(store.get_evidence(parts[1])), 200
    return {"status": "error", "error": "not found"}, 404


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = _single_param(params, name)
    return default if value is None else int(value)


def _single_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name, [])
    if len(values) > 1:
        raise ValueError(f"parameter {name} must occur once")
    return values[0] if values else None
