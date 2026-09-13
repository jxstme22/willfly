"""Restart-safe scheduler state for observation, labels, training and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from willfly.storage.feedback import FeedbackStore


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("watcher timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class WatcherConfig:
    observation_interval_seconds: int = 15
    label_interval_seconds: int = 60
    training_interval_seconds: int = 900
    evaluation_interval_seconds: int = 900
    max_training_seconds: int = 3600
    max_training_examples: int = 100_000

    def __post_init__(self) -> None:
        if min(
            self.observation_interval_seconds,
            self.label_interval_seconds,
            self.training_interval_seconds,
            self.evaluation_interval_seconds,
            self.max_training_seconds,
            self.max_training_examples,
        ) <= 0:
            raise ValueError("watcher limits and intervals must be positive")

    def to_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class WatcherSnapshot:
    observed_at: str
    status: str
    observation_state: str
    label_state: str
    training_state: str
    evaluation_state: str
    waiting_reason: str | None
    outage_seconds_since_previous_tick: int
    personal_trade_count: int
    mature_label_count: int
    eligible_label_count: int
    queued_task_count: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class LearningWatcher:
    """Persist scheduler state; callbacks remain explicit integration points.

    ``tick`` accepts an explicit wall-clock instant so deterministic fixtures
    can test scheduling, while reports retain whether a personal trade was
    present. A caller must supply real observation/training integrations; this
    class never fabricates observations or labels.
    """

    def __init__(self, path: str | Path, *, config: WatcherConfig = WatcherConfig()) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS watcher_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS watcher_tasks (
                task_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            """
        )
        self._connection.commit()

    def __enter__(self) -> "LearningWatcher":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def enqueue(self, *, task_id: str, kind: str, created_at: str) -> bool:
        if not task_id or kind not in {"observation", "labels", "training", "evaluation"}:
            raise ValueError("watcher task identity is invalid")
        _instant(created_at)
        with self._connection:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO watcher_tasks(task_id, kind, status, reason, created_at) VALUES (?, ?, 'queued', NULL, ?)",
                (task_id, kind, created_at),
            )
        return cursor.rowcount == 1

    def finish_task(self, *, task_id: str, status: str, finished_at: str, reason: str | None = None) -> None:
        if status not in {"completed", "waiting", "failed"}:
            raise ValueError("unsupported watcher task status")
        _instant(finished_at)
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE watcher_tasks SET status = ?, reason = ?, finished_at = ? WHERE task_id = ?",
                (status, reason, finished_at, task_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(task_id)

    def pending_tasks(self) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            "SELECT task_id, kind, status, reason, created_at, finished_at FROM watcher_tasks WHERE status IN ('queued', 'waiting') ORDER BY created_at, task_id"
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def tick(
        self,
        *,
        observed_at: str,
        feedback_store: FeedbackStore | None = None,
        personal_trade_count: int = 0,
        observation_state: str = "waiting",
        training_state: str = "waiting",
        evaluation_state: str = "waiting",
    ) -> WatcherSnapshot:
        """Record one scheduler heartbeat and reconcile mature labels."""

        current = _instant(observed_at)
        if personal_trade_count < 0:
            raise ValueError("personal_trade_count cannot be negative")
        if observation_state not in {"running", "waiting", "degraded", "failed"}:
            raise ValueError("unsupported observation state")
        if training_state not in {"running", "waiting", "degraded", "failed"}:
            raise ValueError("unsupported training state")
        if evaluation_state not in {"running", "waiting", "degraded", "failed"}:
            raise ValueError("unsupported evaluation state")
        previous_raw = self._get("last_tick")
        outage = 0
        if previous_raw is not None:
            previous = _instant(str(previous_raw))
            delta = int((current - previous).total_seconds())
            if delta < 0:
                raise ValueError("watcher ticks must be chronological")
            if delta > self.config.observation_interval_seconds * 2:
                outage = delta
        mature_count = eligible_count = 0
        label_state = "waiting"
        waiting_reason = "feedback_store_unavailable"
        if feedback_store is not None:
            queue = feedback_store.mature(as_of_time=observed_at)
            mature_count = sum(item.state in {"ready", "unresolved", "missing"} for item in queue)
            dataset = feedback_store.dataset(as_of_time=observed_at)
            eligible_count = len(dataset.eligible_examples)
            if eligible_count:
                label_state = "ready"
                waiting_reason = None
            elif mature_count:
                label_state = "degraded"
                waiting_reason = "mature_labels_not_training_eligible"
            else:
                label_state = "waiting"
                waiting_reason = "no_mature_labels"
        status = "healthy"
        if outage:
            status = "degraded"
            waiting_reason = "outage_since_previous_tick"
        elif observation_state in {"degraded", "failed"} or training_state in {"degraded", "failed"} or evaluation_state in {"degraded", "failed"}:
            status = "degraded"
        elif any(state == "waiting" for state in (observation_state, training_state, evaluation_state, label_state)):
            status = "waiting"
        self._set("last_tick", observed_at)
        self._set("last_snapshot", {
            "observed_at": observed_at,
            "status": status,
            "observation_state": observation_state,
            "label_state": label_state,
            "training_state": training_state,
            "evaluation_state": evaluation_state,
            "waiting_reason": waiting_reason,
            "outage_seconds_since_previous_tick": outage,
            "personal_trade_count": personal_trade_count,
            "mature_label_count": mature_count,
            "eligible_label_count": eligible_count,
            "queued_task_count": len(self.pending_tasks()),
        })
        return WatcherSnapshot(
            observed_at,
            status,
            observation_state,
            label_state,
            training_state,
            evaluation_state,
            waiting_reason,
            outage,
            personal_trade_count,
            mature_count,
            eligible_count,
            len(self.pending_tasks()),
        )

    def snapshot(self) -> WatcherSnapshot | None:
        value = self._get("last_snapshot")
        return None if value is None else WatcherSnapshot(**value)

    def _get(self, key: str) -> Any:
        row = self._connection.execute("SELECT value_json FROM watcher_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row["value_json"])

    def _set(self, key: str, value: Any) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO watcher_state(key, value_json) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (key, json.dumps(value, sort_keys=True)),
            )


__all__ = ["LearningWatcher", "WatcherConfig", "WatcherSnapshot"]
