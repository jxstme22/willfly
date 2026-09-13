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

    def __post_init__(self) -> None:
        if self.action not in {"acquire", "open", "collect", "resize", "remove", "convert", "failed", "unsupported"}:
            raise ValueError("unsupported LP lifecycle action")
        if min(self.token0_atomic, self.token1_atomic, self.gas_atomic) < 0 or not self.action_id or not self.source_ref:
            raise ValueError("LP event is invalid")


@dataclass(frozen=True)
class LPLifecycleResult:
    balances: Mapping[str, int]
    fees_paid_atomic: int
    gas_paid_atomic: int
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
    fees = gas = 0
    residual0 = residual1 = 0
    for event in events:
        refs.append(event.source_ref)
        gas += event.gas_atomic
        if event.action == "unsupported":
            unsupported.append(event.action_id)
            continue
        if event.action == "failed":
            failed.append(event.action_id)
            continue
        if event.action in {"acquire", "open", "resize"}:
            if balances.get(token0, 0) < event.token0_atomic or balances.get(token1, 0) < event.token1_atomic:
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) - event.token0_atomic
            balances[token1] = balances.get(token1, 0) - event.token1_atomic
        elif event.action in {"collect", "remove", "convert"}:
            balances[token0] = balances.get(token0, 0) + event.token0_atomic
            balances[token1] = balances.get(token1, 0) + event.token1_atomic
            residual0 += event.token0_atomic
            residual1 += event.token1_atomic
        fees += event.token0_atomic + event.token1_atomic if event.action == "collect" else 0
    return LPLifecycleResult(balances, fees, gas, residual0, residual1, tuple(failed), tuple(unsupported), tuple(refs))
