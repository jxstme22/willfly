"""Exact-atomic portfolio ledger for replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LedgerEntry:
    action_id: str
    entry_type: str
    asset: str
    delta_atomic: int
    source_ref: str
    failed: bool = False


class PortfolioLedger:
    """Track balances and accounting categories without floating point values."""

    def __init__(self, initial_balances: Mapping[str, int] | None = None) -> None:
        self._balances = {asset: _amount(value) for asset, value in (initial_balances or {}).items()}
        self._entries: list[LedgerEntry] = []
        self._deposits: dict[str, int] = {}
        self._fees: dict[str, int] = {}

    @property
    def balances(self) -> dict[str, int]:
        return dict(self._balances)

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def deposit(self, action_id: str, asset: str, amount_atomic: int, source_ref: str) -> None:
        amount = _positive(amount_atomic)
        self._balances[asset] = self._balances.get(asset, 0) + amount
        self._deposits[asset] = self._deposits.get(asset, 0) + amount
        self._entries.append(LedgerEntry(action_id, "deposit", asset, amount, source_ref))

    def apply_fee(self, action_id: str, asset: str, amount_atomic: int, source_ref: str) -> None:
        amount = _positive(amount_atomic)
        self._spend(asset, amount, action_id, "fee", source_ref)
        self._fees[asset] = self._fees.get(asset, 0) + amount

    def apply_trade(
        self,
        action_id: str,
        *,
        spend_asset: str,
        spend_atomic: int,
        receive_asset: str,
        receive_atomic: int,
        source_ref: str,
        fee_asset: str | None = None,
        fee_atomic: int = 0,
    ) -> None:
        spend = _positive(spend_atomic)
        receive = _positive(receive_atomic)
        fee = _amount(fee_atomic)
        if fee_asset is not None and fee <= 0:
            raise ValueError("fee_asset requires a positive fee")
        if fee_asset is None and fee:
            raise ValueError("fee_atomic requires fee_asset")
        outgoing: dict[str, int] = {spend_asset: spend}
        if fee_asset is not None:
            outgoing[fee_asset] = outgoing.get(fee_asset, 0) + fee
        for asset, amount in outgoing.items():
            if self._balances.get(asset, 0) < amount:
                self._entries.append(LedgerEntry(action_id, "trade", asset, 0, source_ref, failed=True))
                raise ValueError("insufficient balance for trade")
        for asset, amount in outgoing.items():
            self._balances[asset] -= amount
        self._balances[receive_asset] = self._balances.get(receive_asset, 0) + receive
        self._entries.append(LedgerEntry(action_id, "trade", spend_asset, -spend, source_ref))
        self._entries.append(LedgerEntry(action_id, "trade", receive_asset, receive, source_ref))
        if fee_asset is not None:
            self._fees[fee_asset] = self._fees.get(fee_asset, 0) + fee
            self._entries.append(LedgerEntry(action_id, "fee", fee_asset, -fee, source_ref))

    def mark(self, action_id: str, asset: str, price_numerator: int, price_denominator: int, source_ref: str) -> None:
        _positive(price_numerator)
        _positive(price_denominator)
        self._entries.append(LedgerEntry(action_id, "mark", asset, 0, source_ref))

    def accounting_summary(self) -> dict[str, dict[str, int]]:
        return {
            "balances": dict(self._balances),
            "deposits": dict(self._deposits),
            "fees": dict(self._fees),
        }

    def _spend(self, asset: str, amount: int, action_id: str, entry_type: str, source_ref: str) -> None:
        if self._balances.get(asset, 0) < amount:
            self._entries.append(LedgerEntry(action_id, entry_type, asset, 0, source_ref, failed=True))
            raise ValueError("insufficient balance")
        self._balances[asset] -= amount
        self._entries.append(LedgerEntry(action_id, entry_type, asset, -amount, source_ref))


def _amount(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("atomic amount must be a non-negative integer")
    return value


def _positive(value: int) -> int:
    amount = _amount(value)
    if amount == 0:
        raise ValueError("atomic amount must be positive")
    return amount
