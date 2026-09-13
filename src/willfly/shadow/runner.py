"""Restart-safe, read-only hypothetical decision runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import threading
from typing import Mapping

from willfly.policies.constraints import Candidate, allocate_candidates
from willfly.policies.prediction import ActionMappingConfig, MappedAction, Prediction, map_prediction
from willfly.replay.execution import PoolQuote, simulate_fill
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
    modeled_fill_status: str = "not_attempted"
    modeled_input_atomic: int = 0
    modeled_output_atomic: int = 0
    modeled_output_asset: str | None = None
    modeled_fill_source_ref: str = "quote:none"

    def __post_init__(self) -> None:
        if not self.hypothetical or self.execution_state != "not_submitted":
            raise ValueError("shadow decisions must remain hypothetical and unsubmitted")
        if self.action not in {"enter", "exit", "hold", "watch"}:
            raise ValueError("unsupported shadow action")
        if self.amount_atomic < 0 or min(self.modeled_input_atomic, self.modeled_output_atomic) < 0:
            raise ValueError("shadow amount cannot be negative")
        if self.modeled_fill_status not in {"not_attempted", "filled", "missing_state", "unsupported", "reverted"}:
            raise ValueError("unsupported modeled fill status")

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
            "modeled_fill_status": self.modeled_fill_status,
            "modeled_input_atomic": self.modeled_input_atomic,
            "modeled_output_atomic": self.modeled_output_atomic,
            "modeled_output_asset": self.modeled_output_asset,
            "modeled_fill_source_ref": self.modeled_fill_source_ref,
        }


@dataclass(frozen=True)
class ShadowStepResult:
    decision: ShadowDecision
    duplicate: bool
    health: ShadowHealth
    mapped_action: MappedAction


class ShadowCheckpointStore:
    """SQLite checkpoint store with decision-ID uniqueness across restarts."""

    def __init__(self, path: str = ":memory:", *, run_identity: Mapping[str, str] | None = None) -> None:
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_run_identity (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_observations (observation_id TEXT PRIMARY KEY, received_at TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_decisions (decision_id TEXT PRIMARY KEY, observation_id TEXT, payload TEXT NOT NULL)"
        )
        columns = {row[1] for row in self._connection.execute("PRAGMA table_info(shadow_decisions)").fetchall()}
        if "observation_id" not in columns:
            self._connection.execute("ALTER TABLE shadow_decisions ADD COLUMN observation_id TEXT")
        self._connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS shadow_decisions_observation_id ON shadow_decisions(observation_id)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_checkpoints (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._connection.commit()
        if run_identity:
            self.bind_identity(run_identity)

    @property
    def run_identity(self) -> dict[str, str]:
        rows = self._connection.execute(
            "SELECT key, value FROM shadow_run_identity ORDER BY key"
        ).fetchall()
        return {str(key): str(value) for key, value in rows}

    def bind_identity(self, identity: Mapping[str, str]) -> None:
        normalized = {str(key): str(value) for key, value in identity.items() if str(key) and str(value)}
        if not normalized:
            raise ValueError("run identity cannot be empty")
        existing = self.run_identity
        conflicts = {key for key in set(existing) & set(normalized) if existing[key] != normalized[key]}
        if conflicts:
            raise ValueError(f"shadow run identity mismatch: {', '.join(sorted(conflicts))}")
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT OR IGNORE INTO shadow_run_identity(key, value) VALUES (?, ?)",
                tuple(normalized.items()),
            )

    def append(self, decision: ShadowDecision) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO shadow_decisions(decision_id, observation_id, payload) VALUES (?, ?, ?)",
                (decision.decision_id, decision.observation_id, json.dumps(decision.to_dict(), sort_keys=True)),
            )
            self._connection.commit()
        return cursor.rowcount == 1

    def append_step(self, observation: ShadowObservation, decision: ShadowDecision) -> tuple[bool, ShadowDecision]:
        """Publish observation, decision and cursors in one SQLite transaction."""

        with self._lock:
            try:
                with self._connection:
                    existing = self._connection.execute(
                        "SELECT payload FROM shadow_decisions WHERE observation_id = ?",
                        (observation.observation_id,),
                    ).fetchone()
                    if existing is not None:
                        return False, _decision_from_dict(json.loads(existing[0]))
                    self._connection.execute(
                        "INSERT OR IGNORE INTO shadow_observations(observation_id, received_at, payload) VALUES (?, ?, ?)",
                        (observation.observation_id, observation.received_at, json.dumps(observation.__dict__, sort_keys=True)),
                    )
                    self._connection.execute(
                        "INSERT INTO shadow_decisions(decision_id, observation_id, payload) VALUES (?, ?, ?)",
                        (decision.decision_id, decision.observation_id, json.dumps(decision.to_dict(), sort_keys=True)),
                    )
                    self._connection.execute(
                        "INSERT OR REPLACE INTO shadow_checkpoints(name, value) VALUES ('last_received_at', ?)",
                        (observation.received_at,),
                    )
                    self._connection.execute(
                        "INSERT OR REPLACE INTO shadow_checkpoints(name, value) VALUES ('last_decision_id', ?)",
                        (decision.decision_id,),
                    )
                    return True, decision
            except sqlite3.IntegrityError:
                existing = self._connection.execute(
                    "SELECT payload FROM shadow_decisions WHERE observation_id = ?",
                    (observation.observation_id,),
                ).fetchone()
                if existing is None:
                    raise
                return False, _decision_from_dict(json.loads(existing[0]))

    def get(self, decision_id: str) -> ShadowDecision | None:
        row = self._connection.execute(
            "SELECT payload FROM shadow_decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return None if row is None else _decision_from_dict(json.loads(row[0]))

    def get_by_observation(self, observation_id: str) -> ShadowDecision | None:
        row = self._connection.execute(
            "SELECT payload FROM shadow_decisions WHERE observation_id = ?", (observation_id,)
        ).fetchone()
        return None if row is None else _decision_from_dict(json.loads(row[0]))

    def decisions(self) -> tuple[ShadowDecision, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM shadow_decisions ORDER BY rowid"
        ).fetchall()
        return tuple(_decision_from_dict(json.loads(row[0])) for row in rows)

    def observations(self) -> tuple[ShadowObservation, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM shadow_observations ORDER BY rowid"
        ).fetchall()
        return tuple(_observation_from_dict(json.loads(row[0])) for row in rows)

    def modeled_positions(self) -> dict[str, int]:
        positions: dict[str, int] = {}
        for decision in self.decisions():
            if decision.modeled_fill_status == "filled" and decision.action == "enter" and decision.modeled_output_asset:
                positions[decision.modeled_output_asset] = positions.get(decision.modeled_output_asset, 0) + decision.modeled_output_atomic
            elif decision.modeled_fill_status == "filled" and decision.action == "exit":
                positions.pop(decision.asset, None)
        return positions

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
        run_identity: Mapping[str, str] | None = None,
    ) -> None:
        if min(fixed_entry_atomic, initial_cash_atomic) < 0 or fixed_entry_atomic == 0 or max_positions < 0:
            raise ValueError("shadow allocation constraints are invalid")
        self.store = store
        self.fixed_entry_atomic = fixed_entry_atomic
        self.max_positions = max_positions
        self.initial_cash_atomic = initial_cash_atomic
        self.mapping_config = mapping_config
        self.decision_deadline_seconds = decision_deadline_seconds
        if run_identity:
            self.store.bind_identity(run_identity)
        elif self.store.run_identity:
            raise ValueError("existing shadow run identity must be supplied on restart")

    def step(
        self,
        observation: ShadowObservation,
        prediction: Prediction,
        *,
        decision_time: str | None = None,
        entry_quote: PoolQuote | None = None,
        exit_quote: PoolQuote | None = None,
        model_execution: bool = False,
        execution_delay_seconds: int = 0,
    ) -> ShadowStepResult:
        if execution_delay_seconds < 0:
            raise ValueError("modeled execution delay cannot be negative")
        decision_time = decision_time or datetime.now(timezone.utc).isoformat()
        if _parse(prediction.as_of_time) > _parse(observation.received_at):
            raise ValueError("prediction as_of_time cannot be later than observation received_at")
        if _parse(decision_time) < _parse(observation.received_at):
            raise ValueError("decision cannot precede observation arrival")
        decision_id = _decision_id(observation)
        previous = self.store.get_by_observation(observation.observation_id)
        if previous is not None:
            if previous.asset != observation.asset or previous.received_at != observation.received_at:
                raise ValueError("observation identity was reused with different content")
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
        modeled_fill_status = "not_attempted"
        modeled_input_atomic = 0
        modeled_output_atomic = 0
        modeled_output_asset: str | None = None
        modeled_fill_source_ref = "quote:none"
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
                if model_execution:
                    fill = simulate_fill(
                        entry_quote,
                        input_atomic=amount,
                        submitted_at=observation.received_at,
                        processing_delay_seconds=execution_delay_seconds,
                    )
                    modeled_fill_status = fill.status
                    modeled_input_atomic = fill.input_atomic
                    modeled_output_atomic = fill.output_atomic
                    modeled_output_asset = None if entry_quote is None else entry_quote.output_asset
                    modeled_fill_source_ref = fill.source_ref
        elif action == "exit" and not existing:
            action = "watch"
            reason = "exit_without_open_position"
        elif action == "exit":
            if not model_execution:
                # A proposal is not a liquidation.
                action = "hold"
                reason = "exit_requires_modeled_execution_and_reconciliation"
            else:
                amount = self._open_amount(observation.asset)
                if amount <= 0:
                    action = "watch"
                    reason = "exit_without_reconciled_inventory"
                else:
                    fill = simulate_fill(
                        exit_quote,
                        input_atomic=amount,
                        submitted_at=observation.received_at,
                        processing_delay_seconds=execution_delay_seconds,
                    )
                    modeled_fill_status = fill.status
                    modeled_input_atomic = fill.input_atomic
                    modeled_output_atomic = fill.output_atomic
                    modeled_output_asset = None if exit_quote is None else exit_quote.output_asset
                    modeled_fill_source_ref = fill.source_ref
                    if fill.status != "filled":
                        action = "hold"
                        reason = f"exit_modeled_fill_{fill.status}"
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
            True,
            "not_submitted",
            modeled_fill_status,
            modeled_input_atomic,
            modeled_output_atomic,
            modeled_output_asset,
            modeled_fill_source_ref,
        )
        inserted, record = self.store.append_step(observation, record)
        return ShadowStepResult(record, not inserted, health, mapped)

    def _open_assets(self) -> tuple[str, ...]:
        positions: set[str] = set()
        for decision in self.store.decisions():
            if decision.action == "enter" and decision.modeled_fill_status in {"not_attempted", "filled"}:
                positions.add(decision.asset)
            elif decision.action == "exit" and decision.modeled_fill_status == "filled":
                positions.discard(decision.asset)
        return tuple(sorted(positions))

    def _available_cash(self) -> int:
        committed = sum(
            decision.amount_atomic
            for decision in self.store.decisions()
            if decision.action == "enter" and decision.modeled_fill_status in {"not_attempted", "filled"}
        )
        released = sum(
            decision.modeled_output_atomic
            for decision in self.store.decisions()
            if decision.action == "exit" and decision.modeled_fill_status == "filled"
        )
        return self.initial_cash_atomic - committed + released

    def _open_amount(self, asset: str) -> int:
        amount = 0
        for decision in self.store.decisions():
            if decision.asset != asset:
                continue
            if decision.action == "enter":
                if decision.modeled_fill_status == "filled":
                    amount = decision.modeled_output_atomic
                elif decision.modeled_fill_status == "not_attempted":
                    amount = decision.amount_atomic
            elif decision.action == "exit" and decision.modeled_fill_status == "filled":
                amount = 0
        return amount


def _decision_id(observation: ShadowObservation) -> str:
    payload = {
        "observation_id": observation.observation_id,
        "asset": observation.asset,
        "received_at": observation.received_at,
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
        str(payload.get("modeled_fill_status", "not_attempted")),
        int(payload.get("modeled_input_atomic", 0)),
        int(payload.get("modeled_output_atomic", 0)),
        None if payload.get("modeled_output_asset") is None else str(payload["modeled_output_asset"]),
        str(payload.get("modeled_fill_source_ref", "quote:none")),
    )


def _observation_from_dict(payload: dict[str, object]) -> ShadowObservation:
    return ShadowObservation(
        str(payload["observation_id"]),
        str(payload["asset"]),
        str(payload["received_at"]),
        str(payload["quality_state"]),
        bool(payload.get("contradictory", False)),
        tuple(str(item) for item in payload.get("source_refs", ())),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow timestamps must include a timezone")
    return parsed
