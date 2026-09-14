"""Evidence-preserving LP lifecycle accounting.

The replay engine models one owned position at a time. It is intentionally a
read-only ledger: a receipt can debit observed gas and settle observed token
flows, but no code here builds, signs or submits an LP transaction. Missing
receipt state, unknown hooks and unsupported tokens remain excluded from the
canonical lifecycle while their source references are retained.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from willfly.replay.lp_positions import (
    PositionState,
    UINT256_MODULUS,
    accrue_fee_growth,
    amounts_for_sqrt_price,
)


_ACTIONS = {
    "acquire", "open", "add", "add_liquidity", "collect", "resize",
    "remove", "remove_liquidity", "withdraw", "close", "convert",
    "failed", "unsupported",
}
_ACTION_ALIASES = {
    "acquire": "open", "add": "resize", "add_liquidity": "resize",
    "remove_liquidity": "remove", "withdraw": "remove", "close": "remove",
}
_RECEIPT_STATES = {"confirmed", "failed", "reverted", "pending", "unknown"}
_CANONICAL_STATES = {"canonical", "provisional", "orphaned", "unresolved"}
_EVIDENCE_STATES = {"fixture", "modeled", "verified", "inconclusive", "unavailable"}


def _atomic(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_int(value: object, field_name: str, *, allow_negative: bool = False) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or (not allow_negative and value < 0):
        raise ValueError(f"{field_name} must be an integer")
    return value


@dataclass(frozen=True)
class LPEvent:
    """One observed or fixture lifecycle receipt.

    ``token*_atomic`` are wallet-side amounts for this action. They are always
    unsigned; action direction supplies the meaning (open/resize debit the
    wallet, collect/remove/convert credit it). Optional checkpoint fields allow
    a caller to require exact V4 amounts and fee state when a receipt includes
    the corresponding protocol state.
    """

    action_id: str
    action: str
    token0_atomic: int
    token1_atomic: int
    gas_atomic: int = 0
    source_ref: str = ""
    position_id: str | None = None
    owner: str | None = None
    gas_asset: str | None = None
    pool_id: str | None = None
    hook: str | None = None
    hooks: str | None = None
    liquidity: int | None = None
    liquidity_delta: int | None = None
    tick_lower: int | None = None
    tick_upper: int | None = None
    tick_spacing: int | None = None
    current_tick: int | None = None
    current_sqrt_price_x96: int | None = None
    lower_sqrt_price_x96: int | None = None
    upper_sqrt_price_x96: int | None = None
    fee_growth_inside0: int | None = None
    fee_growth_inside1: int | None = None
    receipt_status: str = "confirmed"
    canonical_status: str = "canonical"
    reason_flags: tuple[str, ...] = ()
    # ``status`` is accepted as a compatibility alias for receipt adapters
    # that use the wallet-observation field name.
    status: str | None = None

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError("unsupported LP lifecycle action")
        if not isinstance(self.action_id, str) or not self.action_id:
            raise ValueError("LP action_id is invalid")
        if not isinstance(self.source_ref, str) or not self.source_ref:
            raise ValueError("LP source_ref is required")
        _atomic(self.token0_atomic, "token0_atomic")
        _atomic(self.token1_atomic, "token1_atomic")
        _atomic(self.gas_atomic, "gas_atomic")
        for value, field_name in (
            (self.liquidity, "liquidity"),
            (self.tick_spacing, "tick_spacing"),
            (self.current_sqrt_price_x96, "current_sqrt_price_x96"),
            (self.lower_sqrt_price_x96, "lower_sqrt_price_x96"),
            (self.upper_sqrt_price_x96, "upper_sqrt_price_x96"),
        ):
            _optional_int(value, field_name)
        _optional_int(self.liquidity_delta, "liquidity_delta", allow_negative=True)
        for value, field_name in (
            (self.tick_lower, "tick_lower"),
            (self.tick_upper, "tick_upper"),
            (self.current_tick, "current_tick"),
        ):
            _optional_int(value, field_name, allow_negative=True)
        for value, field_name in (
            (self.fee_growth_inside0, "fee_growth_inside0"),
            (self.fee_growth_inside1, "fee_growth_inside1"),
        ):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < UINT256_MODULUS):
                raise ValueError(f"{field_name} must be a uint256")
        for value, field_name in (
            (self.current_sqrt_price_x96, "current_sqrt_price_x96"),
            (self.lower_sqrt_price_x96, "lower_sqrt_price_x96"),
            (self.upper_sqrt_price_x96, "upper_sqrt_price_x96"),
        ):
            if value == 0:
                raise ValueError(f"{field_name} must be positive")
        if self.tick_spacing == 0:
            raise ValueError("tick_spacing must be positive")
        if self.tick_lower is not None and self.tick_upper is not None and self.tick_lower >= self.tick_upper:
            raise ValueError("LP event range is invalid")
        if self.position_id is not None and (not isinstance(self.position_id, str) or not self.position_id):
            raise ValueError("position_id must be non-empty text")
        if self.pool_id is not None and (not isinstance(self.pool_id, str) or not self.pool_id):
            raise ValueError("pool_id must be non-empty text")
        if self.owner is not None and (not isinstance(self.owner, str) or not self.owner):
            raise ValueError("owner must be non-empty text")
        if self.gas_asset is not None and (not isinstance(self.gas_asset, str) or not self.gas_asset):
            raise ValueError("gas_asset cannot be empty")
        if self.hook is not None and (not isinstance(self.hook, str) or not self.hook):
            raise ValueError("hook must be non-empty text")
        if self.hooks is not None and (not isinstance(self.hooks, str) or not self.hooks):
            raise ValueError("hooks must be non-empty text")
        if self.hook is not None and self.hooks is not None and self.hook.lower() != self.hooks.lower():
            raise ValueError("hook and hooks disagree")
        if self.receipt_status not in _RECEIPT_STATES:
            raise ValueError("unsupported LP receipt status")
        if self.status is not None and self.status not in _RECEIPT_STATES:
            raise ValueError("unsupported LP status")
        if self.status is not None and self.receipt_status != "confirmed" and self.status != self.receipt_status:
            raise ValueError("status and receipt_status disagree")
        if self.canonical_status not in _CANONICAL_STATES:
            raise ValueError("unsupported LP canonical status")
        if not isinstance(self.reason_flags, tuple) or not all(isinstance(flag, str) and flag for flag in self.reason_flags):
            raise ValueError("reason_flags must contain non-empty text")

    @property
    def canonical_action(self) -> str:
        return _ACTION_ALIASES.get(self.action, self.action)

    @property
    def event_hook(self) -> str | None:
        return self.hook or self.hooks

    @property
    def effective_receipt_status(self) -> str:
        return self.status or self.receipt_status


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
    active_position: PositionState | None = None
    position_history: tuple[PositionState, ...] = ()
    duplicate_action_ids: tuple[str, ...] = ()
    orphaned_action_ids: tuple[str, ...] = ()
    unresolved_action_ids: tuple[str, ...] = ()
    residual_assets_atomic: Mapping[str, int] = field(default_factory=dict)
    status: str = "modeled"
    evidence_state: str = "unavailable"


def _ownership_matches(position: PositionState, event: LPEvent) -> bool:
    # An observed owner cannot be replaced or omitted. If both sides are
    # unknown we retain the fixture behavior but the result remains modeled.
    if position.owner is None:
        return event.owner is None
    return event.owner == position.owner


def _identity_matches(position: PositionState, event: LPEvent) -> bool:
    if event.position_id is not None and event.position_id != position.position_id:
        return False
    if event.pool_id is not None and event.pool_id != position.pool_id:
        return False
    if event.tick_lower is not None and event.tick_lower != position.tick_lower:
        return False
    if event.tick_upper is not None and event.tick_upper != position.tick_upper:
        return False
    return _ownership_matches(position, event)


def _event_is_unsupported(
    event: LPEvent,
    *,
    token0: str,
    token1: str,
    supported_tokens: frozenset[str] | None,
    supported_hooks: frozenset[str] | None,
) -> bool:
    if supported_tokens is not None and {token0.lower(), token1.lower()} - {item.lower() for item in supported_tokens}:
        return True
    hook = event.event_hook
    if hook is None:
        return False
    # A zero hook has standard no-op behavior. Any nonzero hook needs an
    # explicit allowlist; treating an unknown hook as standard is unsafe.
    if hook.lower() in {"0x" + "0" * 40, "0"}:
        return False
    return supported_hooks is None or hook.lower() not in {item.lower() for item in supported_hooks}


def _range_matches_spacing(lower: int, upper: int, spacing: int | None) -> bool:
    return spacing is None or (spacing > 0 and lower % spacing == 0 and upper % spacing == 0)


def _debit_gas(
    balances: dict[str, int],
    gas_by_asset: dict[str, int],
    unreconciled_gas: dict[str, int],
    *,
    amount: int,
    gas_asset: str | None,
) -> None:
    if amount == 0:
        return
    asset = gas_asset or "unknown:gas"
    gas_by_asset[asset] = gas_by_asset.get(asset, 0) + amount
    available = balances.get(asset, 0)
    debited = min(available, amount)
    if debited:
        balances[asset] = available - debited
    remainder = amount - debited
    if remainder:
        unreconciled_gas[asset] = unreconciled_gas.get(asset, 0) + remainder


def _exact_amounts_match(event: LPEvent, position: PositionState, liquidity: int) -> bool:
    prices = (
        event.current_sqrt_price_x96,
        event.lower_sqrt_price_x96,
        event.upper_sqrt_price_x96,
    )
    if all(value is None for value in prices):
        return True
    if any(value is None for value in prices):
        return False
    expected = amounts_for_sqrt_price(
        replace(position, liquidity=liquidity),
        current_sqrt_price_x96=event.current_sqrt_price_x96,
        lower_sqrt_price_x96=event.lower_sqrt_price_x96,
        upper_sqrt_price_x96=event.upper_sqrt_price_x96,
    )
    return (event.token0_atomic, event.token1_atomic) == expected


def _settle_fee_checkpoint(position: PositionState, event: LPEvent, fallback_tick: int) -> PositionState:
    if event.fee_growth_inside0 is None and event.fee_growth_inside1 is None:
        if event.current_tick is None:
            return position
        return replace(position, current_tick=event.current_tick)
    if event.fee_growth_inside0 is None or event.fee_growth_inside1 is None:
        raise ValueError("both inside fee-growth assets are required")
    tick = fallback_tick if event.current_tick is None else event.current_tick
    return accrue_fee_growth(
        position,
        current_tick=tick,
        fee_growth_inside0=event.fee_growth_inside0,
        fee_growth_inside1=event.fee_growth_inside1,
    )


def replay_lp_lifecycle(
    events: Iterable[LPEvent],
    *,
    token0: str,
    token1: str,
    initial_balances: Mapping[str, int] | None = None,
    position: PositionState | None = None,
    current_tick: int = 0,
    supported_tokens: Iterable[str] | None = None,
    supported_hooks: Iterable[str] | None = None,
    evidence_state: str = "fixture",
) -> LPLifecycleResult:
    """Replay one position with exact optional protocol checkpoints.

    ``evidence_state="fixture"`` is the default because local mechanics are
    synthetic. This parameter never promotes LP recommendations; the policy
    layer requires an explicit verified evidence gate separately.
    """

    if not isinstance(token0, str) or not token0 or not isinstance(token1, str) or not token1 or token0 == token1:
        raise ValueError("LP token identities are invalid")
    if not isinstance(current_tick, int) or isinstance(current_tick, bool):
        raise ValueError("current_tick must be an integer")
    if evidence_state not in _EVIDENCE_STATES:
        raise ValueError("unsupported LP evidence state")
    balances = {asset: amount for asset, amount in (initial_balances or {}).items()}
    if any(not isinstance(asset, str) or not asset for asset in balances):
        raise ValueError("LP balance asset names must be non-empty text")
    if any(not isinstance(amount, int) or isinstance(amount, bool) or amount < 0 for amount in balances.values()):
        raise ValueError("LP balances must be non-negative integers")
    if position is not None and (position.token0 != token0 or position.token1 != token1):
        raise ValueError("initial position token order does not match the pool")
    active_position = position
    supported_token_set = None if supported_tokens is None else frozenset(supported_tokens)
    supported_hook_set = None if supported_hooks is None else frozenset(supported_hooks)
    if supported_token_set is not None and not all(isinstance(item, str) and item for item in supported_token_set):
        raise ValueError("supported_tokens must contain non-empty text")
    if supported_hook_set is not None and not all(isinstance(item, str) and item for item in supported_hook_set):
        raise ValueError("supported_hooks must contain non-empty text")

    failed: list[str] = []
    unsupported: list[str] = []
    orphaned: list[str] = []
    unresolved: list[str] = []
    duplicate: list[str] = []
    refs: list[str] = []
    history: list[PositionState] = []
    fees: dict[str, int] = {token0: 0, token1: 0}
    gas = 0
    gas_by_asset: dict[str, int] = {}
    unreconciled_gas: dict[str, int] = {}
    residual0 = residual1 = 0
    residual_assets: dict[str, int] = {}
    # Keep the delivery state so a later canonical receipt can supersede a
    # provisional/orphaned observation. Once a canonical receipt was settled,
    # later deliveries with the same action ID are idempotently ignored.
    seen_action_states: dict[str, str] = {}

    for event in events:
        refs.append(event.source_ref)
        prior_state = seen_action_states.get(event.action_id)
        receipt_status = event.effective_receipt_status
        event_state = "canonical" if event.canonical_status == "canonical" and receipt_status not in {"pending", "unknown"} else "unresolved"
        if prior_state is not None:
            if prior_state in {"orphaned", "unresolved"} and event_state == "canonical":
                if prior_state == "orphaned" and event.action_id in orphaned:
                    orphaned.remove(event.action_id)
                if event.action_id in unresolved:
                    unresolved.remove(event.action_id)
                seen_action_states[event.action_id] = event_state
            else:
                duplicate.append(event.action_id)
                continue
        else:
            seen_action_states[event.action_id] = "orphaned" if event.canonical_status == "orphaned" else event_state

        # A reorged receipt is useful raw evidence but cannot alter canonical
        # balances or gas. Pending/unresolved receipts likewise remain outside
        # the settled ledger until a canonical receipt arrives.
        if event.canonical_status == "orphaned":
            orphaned.append(event.action_id)
            continue
        if event.canonical_status != "canonical" or receipt_status in {"pending", "unknown"}:
            unresolved.append(event.action_id)
            continue

        gas += event.gas_atomic
        _debit_gas(
            balances,
            gas_by_asset,
            unreconciled_gas,
            amount=event.gas_atomic,
            gas_asset=event.gas_asset,
        )
        action = event.canonical_action
        if receipt_status in {"failed", "reverted"} or action == "failed":
            failed.append(event.action_id)
            continue
        if action == "unsupported" or _event_is_unsupported(
            event,
            token0=token0,
            token1=token1,
            supported_tokens=supported_token_set,
            supported_hooks=supported_hook_set,
        ):
            unsupported.append(event.action_id)
            continue

        if action == "open":
            if active_position is not None:
                failed.append(event.action_id)
                continue
            liquidity = event.liquidity if event.liquidity is not None else 1
            lower = event.tick_lower if event.tick_lower is not None else -1
            upper = event.tick_upper if event.tick_upper is not None else 1
            if liquidity <= 0 or lower >= upper:
                failed.append(event.action_id)
                continue
            if not _range_matches_spacing(lower, upper, event.tick_spacing):
                failed.append(event.action_id)
                continue
            candidate = PositionState(
                event.position_id or event.action_id,
                event.pool_id or "observed-pool",
                token0,
                token1,
                liquidity,
                lower,
                upper,
                event.fee_growth_inside0 or 0,
                event.fee_growth_inside1 or 0,
                owner=event.owner,
                tick_spacing=event.tick_spacing,
                current_tick=event.current_tick if event.current_tick is not None else current_tick,
                sqrt_price_x96=event.current_sqrt_price_x96,
                hooks=event.event_hook,
                current_sqrt_price_x96=event.current_sqrt_price_x96,
                hook=event.event_hook,
            )
            if not _exact_amounts_match(event, candidate, liquidity):
                failed.append(event.action_id)
                continue
            if balances.get(token0, 0) < event.token0_atomic or balances.get(token1, 0) < event.token1_atomic:
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) - event.token0_atomic
            balances[token1] = balances.get(token1, 0) - event.token1_atomic
            active_position = candidate
            history.append(active_position)
            continue

        if active_position is None or not _identity_matches(active_position, event):
            failed.append(event.action_id)
            continue

        try:
            checkpointed = _settle_fee_checkpoint(active_position, event, current_tick)
        except ValueError:
            failed.append(event.action_id)
            continue

        if action == "resize":
            delta = event.liquidity_delta
            if event.liquidity is not None and delta is None:
                delta = event.liquidity
            if delta is not None and checkpointed.liquidity + delta < 0:
                failed.append(event.action_id)
                continue
            amount_liquidity = abs(delta) if delta is not None else checkpointed.liquidity
            if delta is not None and not _exact_amounts_match(event, checkpointed, amount_liquidity):
                failed.append(event.action_id)
                continue
            if delta is not None and delta < 0:
                # Uniswap's signed ModifyLiquidity delta returns inventory for
                # a burn. Keep the position open at zero liquidity so a later
                # collect can still settle owed fees.
                balances[token0] = balances.get(token0, 0) + event.token0_atomic
                balances[token1] = balances.get(token1, 0) + event.token1_atomic
            else:
                if balances.get(token0, 0) < event.token0_atomic or balances.get(token1, 0) < event.token1_atomic:
                    failed.append(event.action_id)
                    continue
                balances[token0] = balances.get(token0, 0) - event.token0_atomic
                balances[token1] = balances.get(token1, 0) - event.token1_atomic
            active_position = replace(
                checkpointed,
                liquidity=checkpointed.liquidity + (delta or 0),
                current_tick=event.current_tick if event.current_tick is not None else checkpointed.current_tick,
                sqrt_price_x96=event.current_sqrt_price_x96 or checkpointed.sqrt_price_x96,
            )
            history.append(active_position)
            continue

        if action == "collect":
            # A receipt without a fee-growth checkpoint may still be an exact
            # observed payout. Once owed balances are known, over-collection is
            # rejected instead of manufacturing fees.
            if checkpointed.tokens_owed0 and event.token0_atomic > checkpointed.tokens_owed0:
                failed.append(event.action_id)
                continue
            if checkpointed.tokens_owed1 and event.token1_atomic > checkpointed.tokens_owed1:
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) + event.token0_atomic
            balances[token1] = balances.get(token1, 0) + event.token1_atomic
            fees[token0] += event.token0_atomic
            fees[token1] += event.token1_atomic
            active_position = replace(
                checkpointed,
                tokens_owed0=max(0, checkpointed.tokens_owed0 - event.token0_atomic),
                tokens_owed1=max(0, checkpointed.tokens_owed1 - event.token1_atomic),
            )
            history.append(active_position)
            continue

        if action in {"remove", "convert"}:
            if not _exact_amounts_match(event, checkpointed, checkpointed.liquidity):
                failed.append(event.action_id)
                continue
            balances[token0] = balances.get(token0, 0) + event.token0_atomic
            balances[token1] = balances.get(token1, 0) + event.token1_atomic
            residual0 += event.token0_atomic
            residual1 += event.token1_atomic
            residual_assets[token0] = residual_assets.get(token0, 0) + event.token0_atomic
            residual_assets[token1] = residual_assets.get(token1, 0) + event.token1_atomic
            history.append(checkpointed)
            active_position = None

    # Duplicate delivery is expected when providers overlap; it is recorded
    # for audit but does not degrade the canonical ledger after idempotent
    # suppression.
    anomalies = failed or unsupported or orphaned or unresolved or unreconciled_gas
    status = "degraded" if anomalies else "reconciled"
    return LPLifecycleResult(
        balances=balances,
        fees_paid_atomic=fees,
        gas_paid_atomic=gas,
        gas_paid_by_asset=gas_by_asset,
        unreconciled_gas_by_asset=unreconciled_gas,
        residual_token0_atomic=residual0,
        residual_token1_atomic=residual1,
        failed_actions=tuple(failed),
        unsupported_actions=tuple(unsupported),
        source_refs=tuple(refs),
        active_position=active_position,
        position_history=tuple(history),
        duplicate_action_ids=tuple(duplicate),
        orphaned_action_ids=tuple(orphaned),
        unresolved_action_ids=tuple(unresolved),
        residual_assets_atomic=residual_assets,
        status=status,
        evidence_state=evidence_state,
    )


__all__ = ["LPEvent", "LPLifecycleResult", "replay_lp_lifecycle"]
