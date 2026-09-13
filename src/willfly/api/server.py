"""A small local HTTP surface for inspection, never execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from willfly.domain import Launch, Observation
from willfly.domain.contracts import ADDRESS_RE, BYTES32_RE
from willfly.features.discovery import DiscoverySnapshot, PoolProjection


@dataclass(frozen=True)
class ReadOnlyStore:
    launches: tuple[Launch, ...] = ()
    pools: tuple[PoolProjection, ...] = ()
    timelines: tuple[Observation, ...] = ()
    quality_state: str = "unknown"
    quality_details: dict[str, object] | None = None

    @classmethod
    def from_discovery(
        cls,
        snapshot: DiscoverySnapshot,
        *,
        timelines: tuple[Observation, ...] = (),
        quality_details: dict[str, object] | None = None,
    ) -> "ReadOnlyStore":
        return cls(snapshot.launches, snapshot.pools, timelines, snapshot.quality_state, quality_details)

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


def create_server(*, store: ReadOnlyStore, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a local-only-by-default server with GET endpoints only."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
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
    return {"status": "error", "error": "not found"}, 404


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = _single_param(params, name)
    return default if value is None else int(value)


def _single_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name, [])
    if len(values) > 1:
        raise ValueError(f"parameter {name} must occur once")
    return values[0] if values else None
