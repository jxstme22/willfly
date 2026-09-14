"""A small local HTTP surface for inspection, never execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from willfly.domain import Launch, ManualAction, Observation, PredictionRecord, SignalProposal, WalletObservation
from willfly.domain.contracts import ADDRESS_RE, BYTES32_RE
from willfly.features.discovery import DiscoverySnapshot, PoolProjection
from willfly.features.projections import ObservatoryProjection
from willfly.storage.raw import RawBatchStore
from willfly.ui.dashboard import render_dashboard
from willfly.ui.signals import build_signal_inbox
from willfly.features.action_linking import ManualActionLink


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
    model_state: Mapping[str, object] | None = None
    manual_actions: tuple[ManualAction, ...] = ()
    action_links: tuple[ManualActionLink, ...] = ()
    signal_loader: Callable[[], Mapping[str, object]] | None = None
    runtime_loader: Callable[[], Mapping[str, object]] | None = None
    signal_file: str | None = None
    signal_file_hash: str | None = None
    signal_provenance: Mapping[str, object] | None = None

    def refresh(self) -> "ReadOnlyStore":
        """Reload an operator-published signal snapshot for each GET request."""

        loader = self.runtime_loader or self.signal_loader
        if loader is None:
            return self
        values = loader()
        return replace(self, **dict(values))

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

    def list_launches(
        self,
        *,
        cursor: int,
        limit: int,
        lifecycle: str | None = None,
        search: str | None = None,
        sort: str = "first_seen_at",
        direction: str = "asc",
    ) -> dict[str, object]:
        """List launches from the cutoff with deterministic filtering and paging."""

        _validate_page(cursor, limit)
        if lifecycle and lifecycle not in {"active", "graduated", "non_graduate", "unknown"}:
            raise ValueError("unsupported lifecycle filter")
        records = [launch for launch in self.launches if lifecycle is None or launch.lifecycle_state == lifecycle]
        records = [launch for launch in records if _matches(search, launch.to_dict())]
        sorters: dict[str, Callable[[Launch], object]] = {
            "token": lambda item: item.token.lower(),
            "first_seen_at": lambda item: item.first_seen_at,
            "created_at": lambda item: item.created_at or "",
            "lifecycle_state": lambda item: item.lifecycle_state,
        }
        records = _sorted(records, sorters, sort, direction, tie=lambda item: item.token.lower())
        page, next_cursor = _page(records, cursor, limit)
        return _page_response([launch.to_dict() for launch in page], cursor, limit, len(records), next_cursor, {
            "lifecycle": lifecycle, "search": search or "", "sort": sort, "direction": direction,
        })

    def get_timeline(self, token: str) -> Observation:
        if ADDRESS_RE.fullmatch(token) is None:
            raise ValueError("token must be an EVM address")
        for timeline in self.timelines:
            if timeline.subject_id.lower() == token.lower():
                return timeline
        raise KeyError(token)

    def get_pool(self, pool_id: str) -> PoolProjection:
        if ADDRESS_RE.fullmatch(pool_id) is None and BYTES32_RE.fullmatch(pool_id) is None:
            raise ValueError("pool_id must be a pool address or bytes32 value")
        for pool in self.pools:
            identity = pool.identity
            if (identity.pool_id or identity.pool_address or "").lower() == pool_id.lower():
                return pool
        raise KeyError(pool_id)

    def list_pools(
        self,
        *,
        cursor: int,
        limit: int,
        protocol: str | None = None,
        trading_status: str | None = None,
        search: str | None = None,
        sort: str = "first_observed_at",
        direction: str = "asc",
    ) -> dict[str, object]:
        _validate_page(cursor, limit)
        if protocol and protocol not in {"uniswap_v3", "uniswap_v4"}:
            raise ValueError("unsupported pool protocol")
        if trading_status and trading_status not in {"active", "inactive", "unknown"}:
            raise ValueError("unsupported trading status filter")
        records = [
            pool for pool in self.pools
            if (protocol is None or pool.identity.protocol == protocol)
            and (trading_status is None or pool.trading_status == trading_status)
            and _matches(search, pool.to_dict())
        ]
        sorters: dict[str, Callable[[PoolProjection], object]] = {
            "pool_id": lambda item: (item.identity.pool_id or item.identity.pool_address or "").lower(),
            "first_observed_at": lambda item: item.first_observed_at,
            "trading_status": lambda item: item.trading_status,
        }
        records = _sorted(records, sorters, sort, direction, tie=lambda item: (item.identity.pool_id or item.identity.pool_address or "").lower())
        page, next_cursor = _page(records, cursor, limit)
        return _page_response([pool.to_dict() for pool in page], cursor, limit, len(records), next_cursor, {
            "protocol": protocol, "trading_status": trading_status, "search": search or "", "sort": sort, "direction": direction,
        })

    def list_timelines(
        self,
        *,
        cursor: int,
        limit: int,
        search: str | None = None,
        quality_state: str | None = None,
        sort: str = "as_of_time",
        direction: str = "desc",
    ) -> dict[str, object]:
        _validate_page(cursor, limit)
        if quality_state and quality_state not in {"healthy", "stale", "degraded", "unknown"}:
            raise ValueError("unsupported observation quality filter")
        records = [
            timeline for timeline in self.timelines
            if (quality_state is None or timeline.quality_state == quality_state)
            and _matches(search, timeline.to_dict())
        ]
        sorters: dict[str, Callable[[Observation], object]] = {
            "subject_id": lambda item: item.subject_id.lower(),
            "as_of_time": lambda item: item.as_of_time,
            "quality_state": lambda item: item.quality_state,
        }
        records = _sorted(records, sorters, sort, direction, tie=lambda item: item.subject_id.lower())
        page, next_cursor = _page(records, cursor, limit)
        return _page_response([timeline.to_dict() for timeline in page], cursor, limit, len(records), next_cursor, {
            "quality_state": quality_state, "search": search or "", "sort": sort, "direction": direction,
        })

    def list_exclusions(
        self,
        *,
        cursor: int,
        limit: int,
        search: str | None = None,
        kind: str | None = None,
        sort: str = "kind",
        direction: str = "asc",
    ) -> dict[str, object]:
        _validate_page(cursor, limit)
        records = [item for item in self.exclusions if (kind is None or str(item.get("kind", "")) == kind) and _matches(search, item)]
        sorters: dict[str, Callable[[Mapping[str, object]], object]] = {
            "kind": lambda item: str(item.get("kind", "")),
            "reason": lambda item: str(item.get("reason", "")),
            "reference": lambda item: str(item.get("transaction_hash", item.get("logical_key", ""))),
        }
        records = _sorted(records, sorters, sort, direction, tie=lambda item: str(item.get("reason", "")))
        page, next_cursor = _page(records, cursor, limit)
        return _page_response([dict(item) for item in page], cursor, limit, len(records), next_cursor, {
            "kind": kind, "search": search or "", "sort": sort, "direction": direction,
        })

    def get_evidence(self, reference: str) -> Mapping[str, object]:
        if not reference:
            raise ValueError("evidence reference is required")
        details = (self.evidence or {}).get(reference)
        if details is None:
            raise KeyError(reference)
        return details

    def list_signals(
        self,
        *,
        cursor: int,
        limit: int,
        search: str | None = None,
        market: str | None = None,
        action: str | None = None,
        state: str | None = None,
        manual_status: str | None = None,
        sort: str = "created_at",
        direction: str = "desc",
    ) -> dict[str, object]:
        _validate_page(cursor, limit)
        as_of = self._as_of_time()
        proposal_status = {
            action.proposal_id: next(
                (link.status for link in self.action_links if link.action_id == action.action_id),
                "not_recorded",
            )
            for action in self.manual_actions
            if action.proposal_id is not None
        }
        entries = build_signal_inbox(
            self.predictions,
            self.proposals,
            as_of_time=as_of,
            market_readiness=self.market_readiness,
            manual_status_by_proposal=proposal_status,
        )
        records = [entry for entry in entries if (market is None or entry.market == market) and (action is None or entry.proposed_action == action) and (state is None or entry.display_state == state) and (manual_status is None or entry.manual_status == manual_status) and _matches(search, entry.to_dict())]
        sorters: dict[str, Callable[[Any], object]] = {
            "created_at": lambda item: item.created_at,
            "expires_at": lambda item: item.expires_at,
            "market": lambda item: item.market,
            "display_state": lambda item: item.display_state,
            "manual_status": lambda item: item.manual_status,
        }
        records = _sorted(records, sorters, sort, direction, tie=lambda item: item.proposal_id)
        page, next_cursor = _page(records, cursor, limit)
        payload = _page_response([entry.to_dict() for entry in page], cursor, limit, len(records), next_cursor, {
            "search": search or "", "market": market, "action": action, "state": state,
            "manual_status": manual_status, "sort": sort, "direction": direction,
        })
        payload["as_of_time"] = as_of
        return payload

    def list_positions(
        self,
        *,
        wallet: str | None = None,
        cursor: int = 0,
        limit: int = 25,
        search: str | None = None,
        lifecycle: str | None = None,
        sort: str = "last_observed_at",
        direction: str = "desc",
    ) -> dict[str, object]:
        _validate_page(cursor, limit)
        observations = self.wallet_observations
        if wallet is not None:
            observations = tuple(item for item in observations if item.wallet.lower() == wallet.lower())
        items = [position.to_dict() | {"wallet": observation.wallet} for observation in observations for position in observation.positions]
        if lifecycle and lifecycle not in {"open", "closed", "unknown"}:
            raise ValueError("unsupported position lifecycle filter")
        items = [item for item in items if (lifecycle is None or item.get("lifecycle_state") == lifecycle) and _matches(search, item)]
        keys: dict[str, Callable[[Mapping[str, object]], object]] = {
            "last_observed_at": lambda item: str(item.get("last_observed_at", "")),
            "liquidity": lambda item: int(item.get("liquidity", 0)),
            "lifecycle_state": lambda item: str(item.get("lifecycle_state", "")),
            "wallet": lambda item: str(item.get("wallet", "")).lower(),
        }
        items = _sorted(items, keys, sort, direction, tie=lambda item: (str(item.get("wallet", "")).lower(), str(item.get("position_id", ""))))
        page, next_cursor = _page(items, cursor, limit)
        payload = _page_response(page, cursor, limit, len(items), next_cursor, {
            "wallet": wallet, "search": search or "", "lifecycle": lifecycle, "sort": sort, "direction": direction,
        })
        payload["observation_count"] = len(observations)
        return payload

    def training(self) -> dict[str, object]:
        return dict(self.training_state or {"status": "unknown", "reason": "training_state_unavailable"})

    def models(self) -> dict[str, object]:
        return dict(self.model_state or {"status": "unknown", "reason": "model_registry_unavailable"})

    def actions(self) -> dict[str, object]:
        links = {link.action_id: link.to_dict() for link in self.action_links}
        return {
            "items": [
                {"action": action.to_dict(), "link": links.get(action.action_id, {"status": "pending", "reason_flags": ["link_not_recorded"]})}
                for action in self.manual_actions
            ]
        }

    def list_actions(
        self,
        *,
        cursor: int,
        limit: int,
        search: str | None = None,
        execution_status: str | None = None,
        link_status: str | None = None,
        sort: str = "action_time",
        direction: str = "desc",
    ) -> dict[str, object]:
        _validate_page(cursor, limit)
        links = {link.action_id: link.to_dict() for link in self.action_links}
        items = [
            {"action": action.to_dict(), "link": links.get(action.action_id, {"status": "pending", "reason_flags": ["link_not_recorded"]})}
            for action in self.manual_actions
        ]
        if execution_status and execution_status not in {"reported", "matched", "ambiguous", "failed", "partial", "not_executed"}:
            raise ValueError("unsupported manual action execution filter")
        if link_status and link_status not in {"matched", "ambiguous", "pending"}:
            raise ValueError("unsupported manual action link filter")
        items = [
            item for item in items
            if (execution_status is None or item["action"].get("execution_status") == execution_status)
            and (link_status is None or item["link"].get("status") == link_status)
            and _matches(search, item)
        ]
        sorters: dict[str, Callable[[Mapping[str, object]], object]] = {
            "action_time": lambda item: str(item["action"].get("action_time", "")),
            "execution_status": lambda item: str(item["action"].get("execution_status", "")),
            "link_status": lambda item: str(item["link"].get("status", "")),
        }
        items = _sorted(items, sorters, sort, direction, tie=lambda item: str(item["action"].get("action_id", "")))
        page, next_cursor = _page(items, cursor, limit)
        return _page_response(page, cursor, limit, len(items), next_cursor, {
            "search": search or "", "execution_status": execution_status, "link_status": link_status,
            "sort": sort, "direction": direction,
        })

    def catalog(self) -> dict[str, object]:
        """Return a bounded first-page catalogue used by the browser shell."""

        health = self.health()
        details = health.get("details", {}) if isinstance(health, dict) else {}
        canonical_event_count = details.get(
            "canonical_event_count",
            self.discovery_snapshot.canonical_event_count if self.discovery_snapshot else 0,
        )
        return {
            "as_of_time": self._as_of_time(),
            "training": self.training(),
            "models": self.models(),
            "health": health,
            "counts": {
                "launches": len(self.launches), "pools": len(self.pools), "timelines": len(self.timelines),
                "exclusions": len(self.exclusions), "signals": len(self._signal_entries()),
                "positions": sum(len(item.positions) for item in self.wallet_observations),
                "actions": len(self.manual_actions),
                "canonical_events": canonical_event_count,
            },
        }

    def _signal_entries(self) -> tuple[object, ...]:
        as_of = self.signal_as_of_time or self._as_of_time()
        proposal_status = {action.proposal_id: next((link.status for link in self.action_links if link.action_id == action.action_id), "not_recorded") for action in self.manual_actions if action.proposal_id is not None}
        return build_signal_inbox(self.predictions, self.proposals, as_of_time=as_of, market_readiness=self.market_readiness, manual_status_by_proposal=proposal_status)

    def _as_of_time(self) -> str:
        return self.signal_as_of_time or (
            self.quality_details.get("as_of_time", "1970-01-01T00:00:00Z")
            if self.quality_details
            else (self.discovery_snapshot.as_of_time if self.discovery_snapshot else "1970-01-01T00:00:00Z")
        )

    def health(self) -> dict[str, object]:
        details = dict(self.quality_details or {})
        details.setdefault("as_of_time", self._as_of_time())
        if self.launches:
            details.setdefault("chain_id", self.launches[0].chain_id)
        elif self.pools:
            details.setdefault("chain_id", self.pools[0].identity.chain_id)
        details.setdefault("launch_count", len(self.launches)); details.setdefault("pool_count", len(self.pools)); details.setdefault("timeline_count", len(self.timelines))
        signal_entries = self._signal_entries()
        details.setdefault("exclusion_count", len(self.exclusions)); details["signal_count"] = len(signal_entries)
        details["current_signal_count"] = sum(entry.display_state != "expired" for entry in signal_entries)
        details["expired_signal_count"] = sum(entry.display_state == "expired" for entry in signal_entries)
        details["signal_monitor_state"] = (
            "waiting_no_published_signal"
            if not signal_entries
            else "historical_expired"
            if all(entry.display_state == "expired" for entry in signal_entries)
            else "current_research_only"
        )
        if self.signal_file is not None:
            details.setdefault("published_signal_file", self.signal_file)
        if self.signal_file_hash is not None:
            details.setdefault("published_signal_file_hash", self.signal_file_hash)
        details.setdefault("missingness", list(self.discovery_snapshot.missingness) if self.discovery_snapshot else ["persisted_projection_unavailable"])
        details.setdefault("lineage_count", len(self.discovery_snapshot.lineage) if self.discovery_snapshot else 0)
        details.setdefault("source_state", "attached" if self.discovery_snapshot else "empty")
        return {"status": "ok" if self.quality_state == "healthy" else self.quality_state, "quality_state": self.quality_state, "stale": self.quality_state in {"stale", "degraded"}, "details": details}

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
        if self.signal_as_of_time:
            snapshot = replace(snapshot, as_of_time=self.signal_as_of_time)
        signals = self._signal_entries()
        positions = [position.to_dict() | {"wallet": observation.wallet} for observation in self.wallet_observations for position in observation.positions]
        actions = tuple(self.actions()["items"])
        return render_dashboard(
            snapshot,
            self.timelines,
            self.exclusions,
            signals=signals,
            positions=tuple(positions),
            training_state=self.training_state,
            model_state=self.model_state,
            actions=actions,
            health_state=self.health(),
        )


def create_server(*, store: ReadOnlyStore, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a local-only-by-default server with GET endpoints only."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            try:
                current_store = store.refresh()
                if urlparse(self.path).path in {"/", "/dashboard"}:
                    body = current_store.dashboard().encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                payload, status = _route(current_store, self.path)
            except KeyError as exc:
                payload, status = {"status": "error", "error": str(exc)}, 404
            except ValueError as exc:
                payload, status = {"status": "error", "error": str(exc)}, 400
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
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
        return store.health(), 200
    if parts == ["catalog"]:
        return store.catalog(), 200
    if parts == ["launches"]:
        return store.list_launches(
            cursor=_int_param(params, "cursor", 0),
            limit=_int_param(params, "limit", 25),
            lifecycle=_single_param(params, "lifecycle"),
            search=_search_param(params),
            sort=_single_param(params, "sort") or "first_seen_at",
            direction=_single_param(params, "direction") or _single_param(params, "dir") or "asc",
        ), 200
    if parts == ["pools"]:
        return store.list_pools(
            cursor=_int_param(params, "cursor", 0),
            limit=_int_param(params, "limit", 25),
            protocol=_single_param(params, "protocol"),
            trading_status=_single_param(params, "trading_status") or _single_param(params, "state"),
            search=_search_param(params),
            sort=_single_param(params, "sort") or "first_observed_at",
            direction=_single_param(params, "direction") or _single_param(params, "dir") or "asc",
        ), 200
    if parts == ["timelines"]:
        return store.list_timelines(
            cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25),
            search=_search_param(params), quality_state=_single_param(params, "quality_state") or _single_param(params, "state"),
            sort=_single_param(params, "sort") or "as_of_time", direction=_single_param(params, "direction") or _single_param(params, "dir") or "desc",
        ), 200
    if len(parts) == 3 and parts[0] == "tokens" and parts[2] == "timeline":
        timeline = store.get_timeline(parts[1])
        return timeline.to_dict(), 200
    if len(parts) == 2 and parts[0] == "pools":
        pool = store.get_pool(parts[1])
        return pool.to_dict(), 200
    if parts == ["exclusions"]:
        return store.list_exclusions(
            cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25),
            search=_search_param(params), kind=_single_param(params, "kind"),
            sort=_single_param(params, "sort") or "kind", direction=_single_param(params, "direction") or _single_param(params, "dir") or "asc",
        ), 200
    if parts == ["signals"]:
        return store.list_signals(
            cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25), search=_search_param(params),
            market=_single_param(params, "market"), action=_single_param(params, "action"),
            state=_single_param(params, "state"), manual_status=_single_param(params, "manual_status"),
            sort=_single_param(params, "sort") or "created_at", direction=_single_param(params, "direction") or _single_param(params, "dir") or "desc",
        ), 200
    if parts == ["positions"]:
        return store.list_positions(
            wallet=_single_param(params, "wallet"), cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25),
            search=_search_param(params), lifecycle=_single_param(params, "lifecycle") or _single_param(params, "state"),
            sort=_single_param(params, "sort") or "last_observed_at", direction=_single_param(params, "direction") or _single_param(params, "dir") or "desc",
        ), 200
    if parts == ["training"]:
        return store.training(), 200
    if parts == ["models"]:
        return store.models(), 200
    if parts == ["actions"]:
        return store.list_actions(
            cursor=_int_param(params, "cursor", 0), limit=_int_param(params, "limit", 25), search=_search_param(params),
            execution_status=_single_param(params, "execution_status") or (_single_param(params, "state") if _single_param(params, "state") in {"reported", "matched", "ambiguous", "failed", "partial", "not_executed"} else None),
            link_status=_single_param(params, "link_status"), sort=_single_param(params, "sort") or "action_time",
            direction=_single_param(params, "direction") or _single_param(params, "dir") or "desc",
        ), 200
    if len(parts) >= 2 and parts[0] == "evidence":
        # Evidence references may contain slashes.  Join the decoded suffix so
        # encodeURIComponent(ref) round-trips through the local server.
        return dict(store.get_evidence("/".join(parts[1:]))), 200
    return {"status": "error", "error": "not found"}, 404


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = _single_param(params, name)
    return default if value is None else int(value)


def _single_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name, [])
    if len(values) > 1:
        raise ValueError(f"parameter {name} must occur once")
    return values[0] if values else None


def _search_param(params: dict[str, list[str]]) -> str | None:
    """Accept the UI's ``search`` name and the shorter API alias ``q``."""

    search = _single_param(params, "search")
    alias = _single_param(params, "q")
    if search is not None and alias is not None:
        raise ValueError("parameter search and q are mutually exclusive")
    return search if search is not None else alias


def _validate_page(cursor: int, limit: int) -> None:
    if cursor < 0 or limit <= 0 or limit > 100:
        raise ValueError("cursor must be non-negative and limit must be between 1 and 100")


def _page(records: list[Any], cursor: int, limit: int) -> tuple[list[Any], int | None]:
    page = records[cursor : cursor + limit]
    next_cursor = cursor + len(page)
    return page, None if next_cursor >= len(records) else next_cursor


def _page_response(items: list[Any], cursor: int, limit: int, total: int, next_cursor: int | None, filters: Mapping[str, object] | None = None) -> dict[str, object]:
    return {
        "items": items,
        "cursor": cursor,
        "limit": limit,
        "next_cursor": None if next_cursor is None else str(next_cursor),
        "total": total,
        "filters": dict(filters or {}),
    }


def _matches(query: str | None, value: object) -> bool:
    if not query:
        return True
    needle = query.strip().lower()
    if not needle:
        return True
    if isinstance(value, Mapping):
        return any(_matches(needle, item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_matches(needle, item) for item in value)
    return needle in str(value).lower()


def _sorted(records: list[Any], sorters: Mapping[str, Callable[[Any], object]], sort: str, direction: str, *, tie: Callable[[Any], object]) -> list[Any]:
    if sort not in sorters:
        raise ValueError(f"unsupported sort field: {sort}")
    if direction not in {"asc", "desc"}:
        raise ValueError("direction must be asc or desc")
    # Sort ties in ascending identity order before reversing the primary key;
    # this gives stable pages even when timestamps or states collide.
    result = sorted(records, key=tie)
    result.sort(key=sorters[sort], reverse=direction == "desc")
    return result
