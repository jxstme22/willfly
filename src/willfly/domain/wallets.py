"""Read-only public-wallet activity and position contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Iterable, Mapping

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
BYTES32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SIGNED_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def _address(value: Any, field: str) -> str:
    if not isinstance(value, str) or ADDRESS_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be an EVM address")
    return value


def _optional_bytes32(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or BYTES32_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a 32-byte hex value")
    return value


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must include a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC-3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _signed_amount(value: Any, field: str) -> str:
    if not isinstance(value, str) or SIGNED_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical signed integer string")
    return value


@dataclass(frozen=True)
class WalletActivity:
    """One public-wallet action with explicit evidence and uncertainty."""

    activity_id: str
    wallet: str
    activity_type: str
    action: str
    status: str
    canonical_status: str
    event_time: str
    received_time: str
    transaction_hash: str | None
    pool_id: str | None
    position_id: str | None
    liquidity_delta: int | None
    asset_deltas_atomic: Mapping[str, str]
    route_status: str
    source_refs: tuple[str, ...]
    reason_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.activity_id, "activity_id")
        _address(self.wallet, "wallet")
        if self.activity_type not in {"swap", "lp"}:
            raise ValueError("unsupported wallet activity_type")
        if self.action not in {"swap", "open", "resize", "collect", "remove", "unknown"}:
            raise ValueError("unsupported wallet activity action")
        if self.status not in {"confirmed", "failed", "pending", "unknown"}:
            raise ValueError("unsupported wallet activity status")
        if self.canonical_status not in {"canonical", "provisional", "orphaned", "unresolved"}:
            raise ValueError("unsupported wallet activity canonical_status")
        event = _timestamp(self.event_time, "event_time")
        received = _timestamp(self.received_time, "received_time")
        if datetime.fromisoformat(received.replace("Z", "+00:00")) < datetime.fromisoformat(event.replace("Z", "+00:00")):
            raise ValueError("received_time cannot precede event_time")
        _optional_bytes32(self.transaction_hash, "transaction_hash")
        if self.activity_type == "swap" and self.action != "swap":
            raise ValueError("swap activity must use swap action")
        if self.activity_type == "lp":
            if self.pool_id is None or self.position_id is None:
                raise ValueError("LP activity requires pool_id and position_id")
            if self.action == "swap":
                raise ValueError("LP activity cannot use swap action")
        if self.pool_id is not None:
            _text(self.pool_id, "pool_id")
        if self.position_id is not None:
            _text(self.position_id, "position_id")
        if self.liquidity_delta is not None and (not isinstance(self.liquidity_delta, int) or isinstance(self.liquidity_delta, bool)):
            raise ValueError("liquidity_delta must be an integer")
        if self.route_status not in {"verified", "uncertain", "unsupported", "not_applicable"}:
            raise ValueError("unsupported wallet activity route_status")
        if self.activity_type == "swap" and self.route_status == "not_applicable":
            raise ValueError("swap route status cannot be not_applicable")
        if self.activity_type == "lp" and self.route_status != "not_applicable":
            raise ValueError("LP route status must be not_applicable")
        if not isinstance(self.asset_deltas_atomic, Mapping):
            raise ValueError("asset_deltas_atomic must be an object")
        for asset, amount in self.asset_deltas_atomic.items():
            _text(asset, "asset_deltas_atomic key")
            _signed_amount(amount, f"asset_deltas_atomic[{asset}]")
        if not self.source_refs or not all(isinstance(ref, str) and ref for ref in self.source_refs):
            raise ValueError("source_refs cannot be empty")
        if not all(isinstance(flag, str) and flag for flag in self.reason_flags):
            raise ValueError("reason_flags must contain text")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "wallet-activity.v0.1",
            "activity_id": self.activity_id,
            "wallet": self.wallet,
            "activity_type": self.activity_type,
            "action": self.action,
            "status": self.status,
            "canonical_status": self.canonical_status,
            "event_time": self.event_time,
            "received_time": self.received_time,
            "transaction_hash": self.transaction_hash,
            "pool_id": self.pool_id,
            "position_id": self.position_id,
            "liquidity_delta": self.liquidity_delta,
            "asset_deltas_atomic": dict(self.asset_deltas_atomic),
            "route_status": self.route_status,
            "source_refs": list(self.source_refs),
            "reason_flags": list(self.reason_flags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WalletActivity":
        if data.get("schema_version") != "wallet-activity.v0.1":
            raise ValueError("unsupported wallet activity schema")
        return cls(
            activity_id=_text(data.get("activity_id"), "activity_id"),
            wallet=_address(data.get("wallet"), "wallet"),
            activity_type=_text(data.get("activity_type"), "activity_type"),
            action=_text(data.get("action"), "action"),
            status=_text(data.get("status"), "status"),
            canonical_status=_text(data.get("canonical_status"), "canonical_status"),
            event_time=_timestamp(data.get("event_time"), "event_time"),
            received_time=_timestamp(data.get("received_time"), "received_time"),
            transaction_hash=_optional_bytes32(data.get("transaction_hash"), "transaction_hash"),
            pool_id=None if data.get("pool_id") is None else _text(data.get("pool_id"), "pool_id"),
            position_id=None if data.get("position_id") is None else _text(data.get("position_id"), "position_id"),
            liquidity_delta=data.get("liquidity_delta"),
            asset_deltas_atomic=dict(data.get("asset_deltas_atomic", {})),
            route_status=_text(data.get("route_status"), "route_status"),
            source_refs=tuple(data.get("source_refs", [])),
            reason_flags=tuple(data.get("reason_flags", [])),
        )


@dataclass(frozen=True)
class WalletPosition:
    wallet: str
    pool_id: str
    position_id: str
    liquidity: int
    lifecycle_state: str
    first_observed_at: str
    last_observed_at: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _address(self.wallet, "wallet")
        _text(self.pool_id, "pool_id")
        _text(self.position_id, "position_id")
        if not isinstance(self.liquidity, int) or isinstance(self.liquidity, bool) or self.liquidity < 0:
            raise ValueError("position liquidity must be a non-negative integer")
        if self.lifecycle_state not in {"open", "closed", "unknown"}:
            raise ValueError("unsupported position lifecycle_state")
        _timestamp(self.first_observed_at, "first_observed_at")
        _timestamp(self.last_observed_at, "last_observed_at")
        if not self.source_refs:
            raise ValueError("position source_refs cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "pool_id": self.pool_id,
            "position_id": self.position_id,
            "liquidity": self.liquidity,
            "lifecycle_state": self.lifecycle_state,
            "first_observed_at": self.first_observed_at,
            "last_observed_at": self.last_observed_at,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class WalletObservation:
    wallet: str
    as_of_time: str
    arrival_cutoff: str
    activities: tuple[WalletActivity, ...]
    positions: tuple[WalletPosition, ...]
    quality_state: str
    missingness: tuple[str, ...]
    lineage: tuple[str, ...]

    def __post_init__(self) -> None:
        _address(self.wallet, "wallet")
        _timestamp(self.as_of_time, "as_of_time")
        _timestamp(self.arrival_cutoff, "arrival_cutoff")
        if self.quality_state not in {"healthy", "degraded", "unknown"}:
            raise ValueError("unsupported wallet observation quality_state")
        if not self.lineage:
            raise ValueError("wallet observation lineage cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "wallet-observation.v0.1",
            "wallet": self.wallet,
            "as_of_time": self.as_of_time,
            "arrival_cutoff": self.arrival_cutoff,
            "activities": [activity.to_dict() for activity in self.activities],
            "positions": [position.to_dict() for position in self.positions],
            "quality_state": self.quality_state,
            "missingness": list(self.missingness),
            "lineage": list(self.lineage),
        }


def activity_from_trade(trade: Any, *, canonical_status: str = "provisional") -> WalletActivity:
    """Convert route-aware trade evidence without promoting an unknown route."""

    deltas: dict[str, int] = {}
    for leg in trade.payment_legs:
        deltas[leg.asset] = deltas.get(leg.asset, 0) - int(leg.amount_atomic)
    for leg in trade.receipt_legs:
        deltas[leg.asset] = deltas.get(leg.asset, 0) + int(leg.amount_atomic)
    for leg in trade.refund_legs:
        deltas[leg.asset] = deltas.get(leg.asset, 0) + int(leg.amount_atomic)
    normalized = {asset: str(amount) for asset, amount in deltas.items() if amount}
    status = "confirmed" if trade.classification == "genuine_swap" and trade.route_status == "verified" else "unknown"
    reasons = list(trade.reason_flags)
    if status == "unknown":
        reasons.append("trade_route_or_classification_unresolved")
    activity_id = "swap:" + trade.transaction_hash.lower() + ":" + trade.wallet.lower() + ":" + trade.trade_direction
    return WalletActivity(
        activity_id=activity_id,
        wallet=trade.wallet,
        activity_type="swap",
        action="swap",
        status=status,
        canonical_status=canonical_status,
        event_time=trade.as_of_time,
        received_time=trade.retrieved_time,
        transaction_hash=trade.transaction_hash,
        pool_id=None,
        position_id=None,
        liquidity_delta=None,
        asset_deltas_atomic=normalized,
        route_status=trade.route_status,
        source_refs=tuple(trade.raw_event_refs),
        reason_flags=tuple(dict.fromkeys(reasons)),
    )


def activity_from_lp(record: Any, *, canonical_status: str = "provisional") -> WalletActivity:
    """Convert a causal LP observation into a restart-safe wallet activity."""

    status = "confirmed" if record.action != "unknown" else "unknown"
    reasons = () if status == "confirmed" else ("lp_action_unresolved",)
    activity_id = f"lp:{record.source_ref}:{record.wallet.lower()}:{record.position_id}"
    return WalletActivity(
        activity_id=activity_id,
        wallet=record.wallet,
        activity_type="lp",
        action=record.action,
        status=status,
        canonical_status=canonical_status,
        event_time=record.event_time,
        received_time=record.received_time,
        transaction_hash=None,
        pool_id=record.pool_id,
        position_id=record.position_id,
        liquidity_delta=record.liquidity_delta,
        asset_deltas_atomic={},
        route_status="not_applicable",
        source_refs=(record.source_ref,),
        reason_flags=reasons,
    )


def build_wallet_observation(
    activities: Iterable[WalletActivity],
    *,
    wallet: str,
    as_of_time: str,
    arrival_cutoff: str,
) -> WalletObservation:
    """Build a causal, deterministic wallet/position view from current evidence."""

    _address(wallet, "wallet")
    as_of = datetime.fromisoformat(_timestamp(as_of_time, "as_of_time").replace("Z", "+00:00"))
    arrival = datetime.fromisoformat(_timestamp(arrival_cutoff, "arrival_cutoff").replace("Z", "+00:00"))
    wallet_key = wallet.lower()
    selected = tuple(
        sorted(
            (
                activity
                for activity in activities
                if activity.wallet.lower() == wallet_key
                and datetime.fromisoformat(activity.event_time.replace("Z", "+00:00")) <= as_of
                and datetime.fromisoformat(activity.received_time.replace("Z", "+00:00")) <= arrival
            ),
            key=lambda item: (item.event_time, item.received_time, item.activity_id),
        )
    )
    missing: list[str] = []
    if not selected:
        missing.append("no_wallet_activity_at_cutoff")
    positions: dict[tuple[str, str], dict[str, Any]] = {}
    for activity in selected:
        if activity.status == "failed":
            missing.append("failed_transaction_observed")
        if activity.activity_type == "swap":
            if activity.status == "unknown" or activity.route_status != "verified":
                missing.append("unknown_swap_route_excluded_from_position_state")
            continue
        key = (activity.pool_id or "", activity.position_id or "")
        state = positions.setdefault(
            key,
            {"liquidity": 0, "uncertain": False, "first": activity.event_time, "last": activity.event_time, "refs": []},
        )
        state["last"] = activity.event_time
        state["refs"].extend(activity.source_refs)
        if activity.canonical_status in {"orphaned", "unresolved"}:
            state["uncertain"] = True
            missing.append("position_canonicality_unresolved")
            continue
        if activity.status != "confirmed" or activity.action == "unknown":
            state["uncertain"] = True
            missing.append("position_action_unresolved")
            continue
        delta = activity.liquidity_delta or 0
        if activity.action == "remove":
            delta = -abs(delta)
        elif activity.action == "collect":
            delta = 0
        state["liquidity"] += delta
        if state["liquidity"] < 0:
            state["liquidity"] = 0
            state["uncertain"] = True
            missing.append("position_liquidity_underflow")
    for (pool_id, position_id), state in sorted(positions.items()):
        positions[(pool_id, position_id)] = state
    position_records = tuple(
        WalletPosition(
            wallet=wallet,
            pool_id=pool_id,
            position_id=position_id,
            liquidity=state["liquidity"],
            lifecycle_state="unknown" if state["uncertain"] else ("open" if state["liquidity"] > 0 else "closed"),
            first_observed_at=state["first"],
            last_observed_at=state["last"],
            source_refs=tuple(dict.fromkeys(state["refs"])),
        )
        for (pool_id, position_id), state in sorted(positions.items())
    )
    if any(activity.canonical_status != "canonical" for activity in selected):
        missing.append("canonicality_not_final_for_all_activity")
    if any(activity.status == "pending" for activity in selected):
        missing.append("pending_transaction_observed")
    unique_missing = tuple(dict.fromkeys(missing))
    lineage = tuple(dict.fromkeys(ref for activity in selected for ref in activity.source_refs))
    if not lineage:
        lineage = (f"wallet:{wallet.lower()}:{as_of_time}",)
    return WalletObservation(
        wallet=wallet,
        as_of_time=as_of_time,
        arrival_cutoff=arrival_cutoff,
        activities=selected,
        positions=position_records,
        quality_state="degraded" if unique_missing else "healthy",
        missingness=unique_missing,
        lineage=lineage,
    )


__all__ = [
    "WalletActivity",
    "WalletObservation",
    "WalletPosition",
    "activity_from_lp",
    "activity_from_trade",
    "build_wallet_observation",
]
