"""Exact-atomic reconciliation for observed wallet activities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from willfly.domain.wallets import WalletObservation


@dataclass(frozen=True)
class AccountingLine:
    activity_id: str
    asset: str
    delta_atomic: int
    category: str
    status: str
    source_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "asset": self.asset,
            "delta_atomic": str(self.delta_atomic),
            "category": self.category,
            "status": self.status,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class AccountingReport:
    wallet: str
    as_of_time: str
    balances_delta_atomic: dict[str, str]
    lines: tuple[AccountingLine, ...]
    positions: tuple[dict[str, Any], ...]
    failed_activity_ids: tuple[str, ...]
    unresolved_activity_ids: tuple[str, ...]
    residual_assets_atomic: dict[str, str]
    status: str
    missingness: tuple[str, ...]
    lineage: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "wallet-accounting.v0.1",
            "wallet": self.wallet,
            "as_of_time": self.as_of_time,
            "balances_delta_atomic": dict(self.balances_delta_atomic),
            "lines": [line.to_dict() for line in self.lines],
            "positions": [dict(position) for position in self.positions],
            "failed_activity_ids": list(self.failed_activity_ids),
            "unresolved_activity_ids": list(self.unresolved_activity_ids),
            "residual_assets_atomic": dict(self.residual_assets_atomic),
            "status": self.status,
            "missingness": list(self.missingness),
            "lineage": list(self.lineage),
        }


def reconcile_wallet_observation(observation: WalletObservation) -> AccountingReport:
    """Reconcile only attributable confirmed swap deltas and LP ownership.

    Unknown, failed, pending, orphaned and unresolved activities are retained
    as audit references but do not alter the reconciled balance delta. Their
    asset deltas are reported as residuals when available.
    """

    balances: dict[str, int] = {}
    residuals: dict[str, int] = {}
    lines: list[AccountingLine] = []
    failed: list[str] = []
    unresolved: list[str] = []
    missing = list(observation.missingness)
    for activity in observation.activities:
        is_reconciled = (
            activity.status == "confirmed"
            and activity.canonical_status == "canonical"
            and (activity.activity_type == "lp" or activity.route_status == "verified")
        )
        if activity.status == "failed":
            failed.append(activity.activity_id)
        if not is_reconciled:
            unresolved.append(activity.activity_id)
        for asset, amount_text in activity.asset_deltas_atomic.items():
            amount = int(amount_text)
            if is_reconciled:
                balances[asset] = balances.get(asset, 0) + amount
                category = "spot_trade" if activity.activity_type == "swap" else "lp_cash_flow"
            else:
                residuals[asset] = residuals.get(asset, 0) + amount
                category = "unresolved_residual"
            lines.append(
                AccountingLine(activity.activity_id, asset, amount, category, activity.status, activity.source_refs)
            )
    if unresolved:
        missing.append("unresolved_activity_not_in_reconciled_balances")
    if failed:
        missing.append("failed_activity_costs_require_receipt_specific_evidence")
    return AccountingReport(
        wallet=observation.wallet,
        as_of_time=observation.as_of_time,
        balances_delta_atomic={asset: str(amount) for asset, amount in sorted(balances.items()) if amount},
        lines=tuple(lines),
        positions=tuple(position.to_dict() for position in observation.positions),
        failed_activity_ids=tuple(failed),
        unresolved_activity_ids=tuple(unresolved),
        residual_assets_atomic={asset: str(amount) for asset, amount in sorted(residuals.items()) if amount},
        status="reconciled" if not missing else "degraded",
        missingness=tuple(dict.fromkeys(missing)),
        lineage=observation.lineage,
    )


__all__ = ["AccountingLine", "AccountingReport", "reconcile_wallet_observation"]
