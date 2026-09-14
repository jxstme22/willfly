"""Restart-safe, read-only hypothetical decision runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import threading
from typing import Any, Iterable, Mapping, Sequence

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


@dataclass(frozen=True)
class ShadowInput:
    """One controlled-source observation and the prediction made at its arrival."""

    observation: ShadowObservation
    prediction: Prediction
    decision_time: str | None = None
    entry_quote: PoolQuote | None = None
    exit_quote: PoolQuote | None = None
    model_execution: bool = False
    execution_delay_seconds: int = 0

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ShadowInput":
        if not isinstance(payload, Mapping):
            raise ValueError("shadow input must be an object")
        observation_payload = payload.get("observation", payload)
        prediction_payload = payload.get("prediction")
        if not isinstance(observation_payload, Mapping) or not isinstance(prediction_payload, Mapping):
            raise ValueError("shadow input requires observation and prediction objects")
        observation = ShadowObservation(
            str(observation_payload["observation_id"]),
            str(observation_payload["asset"]),
            str(observation_payload["received_at"]),
            str(observation_payload["quality_state"]),
            bool(observation_payload.get("contradictory", False)),
            tuple(str(item) for item in observation_payload.get("source_refs", ())),
        )
        prediction = Prediction(
            str(prediction_payload["model_id"]),
            int(prediction_payload["expected_return_bps"]),
            int(prediction_payload["uncertainty_bps"]),
            str(prediction_payload["as_of_time"]),
        )
        return cls(
            observation=observation,
            prediction=prediction,
            decision_time=None if payload.get("decision_time") is None else str(payload["decision_time"]),
            entry_quote=_quote_from_dict(payload.get("entry_quote")),
            exit_quote=_quote_from_dict(payload.get("exit_quote")),
            model_execution=bool(payload.get("model_execution", False)),
            execution_delay_seconds=int(payload.get("execution_delay_seconds", 0)),
        )


@dataclass(frozen=True)
class ShadowRunSummary:
    """Auditable result for one controlled-source shadow replay/resume pass."""

    input_count: int
    processed_count: int
    duplicate_count: int
    health_counts: Mapping[str, int]
    missed_decision_count: int
    action_counts: Mapping[str, int]
    modeled_fill_counts: Mapping[str, int]
    run_identity: Mapping[str, str]
    last_received_at: str | None
    last_decision_id: str | None
    modeled_positions: Mapping[str, int]
    cumulative_counters: Mapping[str, int]
    status: str = "completed"
    operating_mode: str = "read_only"
    hypothetical_only: bool = True
    signing: bool = False
    broadcast: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "input_count": self.input_count,
            "processed_count": self.processed_count,
            "duplicate_count": self.duplicate_count,
            "health_counts": dict(self.health_counts),
            "missed_decision_count": self.missed_decision_count,
            "action_counts": dict(self.action_counts),
            "modeled_fill_counts": dict(self.modeled_fill_counts),
            "run_identity": dict(self.run_identity),
            "last_received_at": self.last_received_at,
            "last_decision_id": self.last_decision_id,
            "modeled_positions": dict(self.modeled_positions),
            "cumulative_counters": dict(self.cumulative_counters),
            "status": self.status,
            "operating_mode": self.operating_mode,
            "hypothetical_only": self.hypothetical_only,
            "signing": self.signing,
            "broadcast": self.broadcast,
        }


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
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)"
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

    def append_step(
        self,
        observation: ShadowObservation,
        decision: ShadowDecision,
        *,
        health_state: str | None = None,
        missed_deadline: bool = False,
    ) -> tuple[bool, ShadowDecision]:
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
                    increments = {
                        "observations": 1,
                        f"action:{decision.action}": 1,
                        f"modeled_fill:{decision.modeled_fill_status}": 1,
                    }
                    if health_state:
                        increments[f"health:{health_state}"] = 1
                    if missed_deadline:
                        increments["missed_decisions"] = 1
                    for name, amount in increments.items():
                        self._connection.execute(
                            "INSERT INTO shadow_counters(name, value) VALUES (?, ?) "
                            "ON CONFLICT(name) DO UPDATE SET value = value + excluded.value",
                            (name, amount),
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

    def counters(self) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT name, value FROM shadow_counters ORDER BY name"
        ).fetchall()
        return {str(name): int(value) for name, value in rows}

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
        inserted, record = self.store.append_step(
            observation,
            record,
            health_state=health.state,
            missed_deadline=health.missed_deadline,
        )
        return ShadowStepResult(record, not inserted, health, mapped)

    def run_sequence(self, inputs: Sequence[ShadowInput] | Iterable[ShadowInput]) -> ShadowRunSummary:
        """Consume a controlled source through ``step`` with restart-safe writes.

        The sequence is intentionally ordered by the source's arrival time. A
        resumed run can include the same prefix again: duplicate observations
        are returned from the durable ledger and do not create new actions.
        A newly delivered observation that moves backwards in time fails closed
        and must be handled as a separately identified replay.
        """

        entries = tuple(inputs)
        health_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        modeled_fill_counts: dict[str, int] = {}
        duplicate_count = 0
        missed_decision_count = 0
        for entry in entries:
            if not isinstance(entry, ShadowInput):
                raise ValueError("shadow sequence contains an unsupported input")
            result = self.step(
                entry.observation,
                entry.prediction,
                decision_time=entry.decision_time,
                entry_quote=entry.entry_quote,
                exit_quote=entry.exit_quote,
                model_execution=entry.model_execution,
                execution_delay_seconds=entry.execution_delay_seconds,
            )
            health_counts[result.health.state] = health_counts.get(result.health.state, 0) + 1
            action_counts[result.decision.action] = action_counts.get(result.decision.action, 0) + 1
            modeled_fill_counts[result.decision.modeled_fill_status] = modeled_fill_counts.get(
                result.decision.modeled_fill_status, 0
            ) + 1
            duplicate_count += int(result.duplicate)
            missed_decision_count += int(result.health.missed_deadline)
        return ShadowRunSummary(
            input_count=len(entries),
            processed_count=len(entries) - duplicate_count,
            duplicate_count=duplicate_count,
            health_counts=health_counts,
            missed_decision_count=missed_decision_count,
            action_counts=action_counts,
            modeled_fill_counts=modeled_fill_counts,
            run_identity=self.store.run_identity,
            last_received_at=self.store.checkpoint_value("last_received_at"),
            last_decision_id=self.store.checkpoint_value("last_decision_id"),
            modeled_positions=self.store.modeled_positions(),
            cumulative_counters=self.store.counters(),
        )

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


def _quote_from_dict(payload: object) -> PoolQuote | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("shadow quote must be an object")
    return PoolQuote(
        str(payload["pool_id"]),
        str(payload["input_asset"]),
        str(payload["output_asset"]),
        int(payload["reserve_input_atomic"]),
        int(payload["reserve_output_atomic"]),
        int(payload["fee_bps"]),
        str(payload["observed_at"]),
        bool(payload.get("hook_supported", True)),
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow timestamps must include a timezone")
    return parsed
