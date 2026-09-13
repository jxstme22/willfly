"""Conservative linkage between reported manual actions and public evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from willfly.domain import ManualAction
from willfly.domain.wallets import WalletActivity


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("action-link timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class ManualActionLink:
    action_id: str
    status: str
    activity_id: str | None
    reason_flags: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"matched", "ambiguous", "pending", "incompatible"}:
            raise ValueError("unsupported manual action link status")
        if self.status == "matched" and self.activity_id is None:
            raise ValueError("matched action links require an activity")
        if not self.reason_flags or not self.evidence_refs:
            raise ValueError("action link requires reasons and evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "status": self.status,
            "activity_id": self.activity_id,
            "reason_flags": list(self.reason_flags),
            "evidence_refs": list(self.evidence_refs),
        }


def link_manual_actions(
    actions: Iterable[ManualAction],
    activities: Iterable[WalletActivity],
    *,
    time_window_seconds: int = 120,
) -> tuple[ManualActionLink, ...]:
    """Link actions using exact identity first, then a narrow evidence window.

    A transaction hash is necessary for an automatic match when supplied. If
    it is absent, one and only one compatible activity in the declared time
    window may match. The function never links by amount alone and never
    changes the action's user-override or execution-status fields.
    """

    if time_window_seconds < 0:
        raise ValueError("time_window_seconds must be non-negative")
    evidence = tuple(activities)
    links: list[ManualActionLink] = []
    for action in actions:
        candidates = [activity for activity in evidence if _compatible(action, activity)]
        if action.transaction_hash:
            exact = [activity for activity in candidates if activity.transaction_hash and activity.transaction_hash.lower() == action.transaction_hash.lower()]
            if len(exact) == 1:
                activity = exact[0]
                links.append(ManualActionLink(action.action_id, "matched", activity.activity_id, ("exact_transaction_match",), activity.source_refs))
                continue
            if len(exact) > 1:
                links.append(_unresolved(action, "multiple_exact_transaction_candidates", exact))
                continue
            links.append(_unresolved(action, "transaction_identity_not_observed", candidates))
            continue
        window = [
            activity
            for activity in candidates
            if abs((_instant(activity.event_time) - _instant(action.action_time)).total_seconds()) <= time_window_seconds
        ]
        if len(window) == 1:
            activity = window[0]
            links.append(ManualActionLink(action.action_id, "matched", activity.activity_id, ("single_compatible_time_window_match",), activity.source_refs))
        elif len(window) > 1:
            links.append(_unresolved(action, "multiple_compatible_time_window_candidates", window))
        else:
            links.append(_unresolved(action, "manual_evidence_pending", candidates))
    return tuple(links)


def _compatible(action: ManualAction, activity: WalletActivity) -> bool:
    if action.wallet_ref and action.wallet_ref.lower() not in {activity.wallet.lower(), f"wallet:{activity.wallet.lower()}"}:
        return False
    if action.market == "spot":
        if activity.activity_type != "swap":
            return False
        if action.instrument.identifier.lower() not in {asset.lower() for asset in activity.asset_deltas_atomic}:
            return False
        token_delta = int(next(amount for asset, amount in activity.asset_deltas_atomic.items() if asset.lower() == action.instrument.identifier.lower()))
        if action.action == "enter" and token_delta <= 0:
            return False
        if action.action == "exit" and token_delta >= 0:
            return False
        return action.action in {"enter", "exit"}
    if activity.activity_type != "lp" or activity.pool_id is None:
        return False
    if activity.pool_id.lower() != action.instrument.identifier.lower():
        return False
    return action.action in {"enter", "exit", "hold"}


def _unresolved(action: ManualAction, reason: str, candidates: Iterable[WalletActivity]) -> ManualActionLink:
    candidate_refs = tuple(dict.fromkeys(ref for candidate in candidates for ref in candidate.source_refs))
    return ManualActionLink(
        action.action_id,
        "ambiguous" if reason.startswith("multiple_") else "pending",
        None,
        (reason,),
        candidate_refs or (f"action:{action.action_id}",),
    )


__all__ = ["ManualActionLink", "link_manual_actions"]
