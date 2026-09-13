"""LP lifecycle accounting with explicit residuals and unsupported outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from willfly.replay.lp_positions import PositionState, amounts_for_liquidity


@dataclass(frozen=True)
class LPEvent:
    action_id: str
    action: str
    token0_atomic: int
    token1_atomic: int
    gas_atomic: int = 0
    source_ref: str = ""
    position_id: str | None = None
    owner: str | None = None
    gas_asset: str | None = None

    def __post_init__(self) -> None:
        if self.action not in {"acquire", "open", "collect", "resize", "remove", "convert", "failed", "unsupported"}:
            raise ValueError("unsupported LP lifecycle action")
        if min(self.token0_atomic, self.token1_atomic, self.gas_atomic) < 0 or not self.action_id or not self.source_ref:
            raise ValueError("LP event is invalid")
        if self.gas_asset is not None and not self.gas_asset:
            raise ValueError("gas_asset cannot be empty")


@dataclass(frozen=True)
class LPLifecycleResult:
    balances: Mapping[str, int]
    fees_paid_atomic: Mapping[str, int]
    gas_paid_atomic: int
    gas_paid_by_asset: Mapping[str, int]
    unreconciled_gas_by_asset: Mapping[str, int]
    residual_token0_atomic: int
    residual_token1_atomic: int
    failed_actions: tuple[str, ...]
    unsupported_actions: tuple[str, ...]
    source_refs: tuple[str, ...]


def replay_lp_lifecycle(
    events: Iterable[LPEvent],
    *,
    token0: str,
    token1: str,
    initial_balances: Mapping[str, int] | None = None,
    position: PositionState | None = None,
    current_tick: int = 0,
) -> LPLifecycleResult:
    balances = {asset: amount for asset, amount in (initial_balances or {}).items()}
    if any(not isinstance(amount, int) or amount < 0 for amount in balances.values()):
        raise ValueError("LP balances must be non-negative integers")
    failed: list[str] = []
    unsupported: list[str] = []
    refs: list[str] = []
    fees: dict[str, int] = {token0: 0, token1: 0}
    gas = 0
    gas_by_asset: dict[str, int] = {}
    unreconciled_gas: dict[str, int] = {}
    residual0 = residual1 = 0
    active_position = position
    seen_action_ids: set[str] = set()
    for event in events:
        if event.action_id in seen_action_ids:
            failed.append(event.action_id)
            continue
        seen_action_ids.add(event.action_id)
        refs.append(event.source_ref)
        gas += event.gas_atomic
        if event.gas_atomic:
            gas_asset = event.gas_asset or "unknown:gas"
            gas_by_asset[gas_asset] = gas_by_asset.get(gas_asset, 0) + event.gas_atomic
            if gas_asset in balances and balances[gas_asset] >= event.gas_atomic:
                balances[gas_asset] -= event.gas_atomic
            else:
                # A denomination without a supplied starting balance is a
                # liability, not free performance. Preserve it explicitly
                # rather than creating a negative or invented balance.
                unreconciled_gas[gas_asset] = unreconciled_gas.get(gas_asset, 0) + event.gas_atomic
        if event.action == "unsupported":
            unsupported.append(event.action_id)
            continue
        if event.action == "failed":
            failed.append(event.action_id)
            continue
        if event.action in {"acquire", "open"}:
            if active_position is not None:
                failed.append(event.action_id)
                continue
            if balances.get(token0, 0) < event.token0_atomic or balances.get(token1, 0) < event.token1_atomic:
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) - event.token0_atomic
            balances[token1] = balances.get(token1, 0) - event.token1_atomic
            active_position = PositionState(
                event.position_id or event.action_id,
                "observed-pool",
                token0,
                token1,
                1,
                -1,
                1,
                owner=event.owner,
            )
        elif event.action == "resize":
            if active_position is None:
                failed.append(event.action_id)
                continue
            if event.position_id is not None and event.position_id != active_position.position_id:
                failed.append(event.action_id)
                continue
            if active_position.owner is not None and event.owner != active_position.owner:
                failed.append(event.action_id)
                continue
            if balances.get(token0, 0) < event.token0_atomic or balances.get(token1, 0) < event.token1_atomic:
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) - event.token0_atomic
            balances[token1] = balances.get(token1, 0) - event.token1_atomic
        elif event.action in {"collect", "remove", "convert"}:
            if active_position is None:
                failed.append(event.action_id)
                continue
            if event.position_id is not None and event.position_id != active_position.position_id:
                failed.append(event.action_id)
                continue
            if active_position.owner is not None and event.owner != active_position.owner:
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) + event.token0_atomic
            balances[token1] = balances.get(token1, 0) + event.token1_atomic
            if event.action in {"remove", "convert"}:
                residual0 += event.token0_atomic
                residual1 += event.token1_atomic
                active_position = None
        if event.action == "collect":
            fees[token0] += event.token0_atomic
            fees[token1] += event.token1_atomic
    return LPLifecycleResult(
        balances,
        fees,
        gas,
        gas_by_asset,
        unreconciled_gas,
        residual0,
        residual1,
        tuple(failed),
        tuple(unsupported),
        tuple(refs),
    )
