"""Restart-safe, read-only hypothetical decision runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from willfly.policies.constraints import Candidate, allocate_candidates
from willfly.policies.prediction import ActionMappingConfig, MappedAction, Prediction, map_prediction
from willfly.shadow.health import ShadowHealth, assess_shadow_health


@dataclass(frozen=True)
class ShadowObservation:
    observation_id: str
    asset: str
    received_at: str
    quality_state: str
    contradictory: bool = False
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id or not self.asset:
            raise ValueError("shadow observation identity is required")
        _parse(self.received_at)


@dataclass(frozen=True)
class ShadowDecision:
    decision_id: str
    observation_id: str
    asset: str
    received_at: str
    action: str
    reason: str
    model_id: str
    amount_atomic: int
    health_state: str
    source_refs: tuple[str, ...]
    hypothetical: bool = True
    execution_state: str = "not_submitted"

    def __post_init__(self) -> None:
        if not self.hypothetical or self.execution_state != "not_submitted":
            raise ValueError("shadow decisions must remain hypothetical and unsubmitted")
        if self.action not in {"enter", "exit", "hold", "watch"}:
            raise ValueError("unsupported shadow action")
        if self.amount_atomic < 0:
            raise ValueError("shadow amount cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "observation_id": self.observation_id,
            "asset": self.asset,
            "received_at": self.received_at,
            "action": self.action,
            "reason": self.reason,
            "model_id": self.model_id,
            "amount_atomic": self.amount_atomic,
            "health_state": self.health_state,
            "source_refs": list(self.source_refs),
            "hypothetical": self.hypothetical,
            "execution_state": self.execution_state,
        }


@dataclass(frozen=True)
class ShadowStepResult:
    decision: ShadowDecision
    duplicate: bool
    health: ShadowHealth
    mapped_action: MappedAction


class ShadowCheckpointStore:
    """SQLite checkpoint store with decision-ID uniqueness across restarts."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_decisions (decision_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_checkpoints (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._connection.commit()

    def append(self, decision: ShadowDecision) -> bool:
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO shadow_decisions(decision_id, payload) VALUES (?, ?)",
            (decision.decision_id, json.dumps(decision.to_dict(), sort_keys=True)),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def get(self, decision_id: str) -> ShadowDecision | None:
        row = self._connection.execute(
            "SELECT payload FROM shadow_decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return None if row is None else _decision_from_dict(json.loads(row[0]))

    def decisions(self) -> tuple[ShadowDecision, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM shadow_decisions ORDER BY rowid"
        ).fetchall()
        return tuple(_decision_from_dict(json.loads(row[0])) for row in rows)

    def checkpoint(self, name: str, value: str) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO shadow_checkpoints(name, value) VALUES (?, ?)", (name, value)
        )
        self._connection.commit()

    def checkpoint_value(self, name: str) -> str | None:
        row = self._connection.execute(
            "SELECT value FROM shadow_checkpoints WHERE name = ?", (name,)
        ).fetchone()
        return None if row is None else str(row[0])

    def close(self) -> None:
        self._connection.close()


class ShadowRunner:
    def __init__(
        self,
        store: ShadowCheckpointStore,
        *,
        fixed_entry_atomic: int,
        max_positions: int,
        initial_cash_atomic: int,
        mapping_config: ActionMappingConfig = ActionMappingConfig(),
        decision_deadline_seconds: int = 15,
    ) -> None:
        if min(fixed_entry_atomic, initial_cash_atomic) < 0 or fixed_entry_atomic == 0 or max_positions < 0:
            raise ValueError("shadow allocation constraints are invalid")
        self.store = store
        self.fixed_entry_atomic = fixed_entry_atomic
        self.max_positions = max_positions
        self.initial_cash_atomic = initial_cash_atomic
        self.mapping_config = mapping_config
        self.decision_deadline_seconds = decision_deadline_seconds

    def step(
        self,
        observation: ShadowObservation,
        prediction: Prediction,
        *,
        decision_time: str | None = None,
    ) -> ShadowStepResult:
        decision_time = decision_time or datetime.now(timezone.utc).isoformat()
        if _parse(prediction.as_of_time) > _parse(observation.received_at):
            raise ValueError("prediction as_of_time cannot be later than observation received_at")
        if _parse(decision_time) < _parse(observation.received_at):
            raise ValueError("decision cannot precede observation arrival")
        decision_id = _decision_id(observation, prediction)
        previous = self.store.get(decision_id)
        if previous is not None:
            health = assess_shadow_health(
                quality_state=observation.quality_state, contradictory=observation.contradictory,
                now=decision_time, latest_arrival=observation.received_at,
                decision_deadline_seconds=self.decision_deadline_seconds,
            )
            return ShadowStepResult(previous, True, health, MappedAction(previous.action, previous.reason, previous.model_id))
        last_arrival = self.store.checkpoint_value("last_received_at")
        if last_arrival and _parse(observation.received_at) < _parse(last_arrival):
            raise ValueError("out-of-order observation requires a separate replay")
        open_assets = self._open_assets()
        existing = observation.asset in open_assets
        health = assess_shadow_health(
            quality_state=observation.quality_state,
            contradictory=observation.contradictory,
            now=decision_time,
            latest_arrival=observation.received_at,
            existing_position=existing,
            decision_deadline_seconds=self.decision_deadline_seconds,
        )
        mapped = map_prediction(prediction, self.mapping_config, position_open=existing)
        action = mapped.action
        reason = mapped.reason
        amount = 0
        if action == "enter" and not health.can_enter:
            action = "watch"
            reason = f"shadow_{health.reason}_{health.management_action}"
        elif action == "exit" and existing and not health.can_enter:
            action = "hold"
            reason = f"shadow_{health.reason}_{health.management_action}"
        elif action == "enter":
            allocation = allocate_candidates(
                [Candidate(observation.observation_id, observation.asset, observation.received_at, prediction.expected_return_bps)],
                cash_atomic=self._available_cash(),
                fixed_entry_atomic=self.fixed_entry_atomic,
                max_positions=self.max_positions,
                existing_positions=open_assets,
            )
            decision = allocation.decisions[0]
            if not decision.accepted:
                action = "watch"
                reason = f"allocation_{decision.reason}"
            else:
                amount = decision.allocation_atomic
        elif action == "exit" and not existing:
            action = "watch"
            reason = "exit_without_open_position"
        elif action == "exit":
            # A proposal is not a liquidation. No execution ledger is wired here yet.
            action = "hold"
            reason = "exit_requires_modeled_execution_and_reconciliation"
        record = ShadowDecision(
            decision_id,
            observation.observation_id,
            observation.asset,
            observation.received_at,
            action,
            reason,
            prediction.model_id,
            amount,
            health.state,
            observation.source_refs,
        )
        inserted = self.store.append(record)
        if not inserted:
            record = self.store.get(decision_id) or record
        self.store.checkpoint("last_received_at", observation.received_at)
        self.store.checkpoint("last_decision_id", decision_id)
        return ShadowStepResult(record, not inserted, health, mapped)

    def _open_assets(self) -> tuple[str, ...]:
        positions: set[str] = set()
        for decision in self.store.decisions():
            if decision.action == "enter":
                positions.add(decision.asset)
            elif decision.action == "exit":
                positions.discard(decision.asset)
        return tuple(sorted(positions))

    def _available_cash(self) -> int:
        committed = sum(decision.amount_atomic for decision in self.store.decisions() if decision.action == "enter")
        released = sum(decision.amount_atomic for decision in self.store.decisions() if decision.action == "exit")
        return self.initial_cash_atomic - committed + released

    def _open_amount(self, asset: str) -> int:
        amount = 0
        for decision in self.store.decisions():
            if decision.asset != asset:
                continue
            if decision.action == "enter":
                amount = decision.amount_atomic
            elif decision.action == "exit":
                amount = 0
        return amount


def _decision_id(observation: ShadowObservation, prediction: Prediction) -> str:
    payload = {
        "observation_id": observation.observation_id,
        "asset": observation.asset,
        "received_at": observation.received_at,
        "model_id": prediction.model_id,
        "as_of_time": prediction.as_of_time,
        "expected_return_bps": prediction.expected_return_bps,
        "uncertainty_bps": prediction.uncertainty_bps,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decision_from_dict(payload: dict[str, object]) -> ShadowDecision:
    return ShadowDecision(
        str(payload["decision_id"]),
        str(payload["observation_id"]),
        str(payload["asset"]),
        str(payload["received_at"]),
        str(payload["action"]),
        str(payload["reason"]),
        str(payload["model_id"]),
        int(payload["amount_atomic"]),
        str(payload["health_state"]),
        tuple(str(item) for item in payload["source_refs"]),
        bool(payload["hypothetical"]),
        str(payload["execution_state"]),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow timestamps must include a timezone")
    return parsed
