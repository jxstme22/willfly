"""Durable prediction and outcome maturation queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from willfly.domain import OutcomeRecord, PredictionRecord
from willfly.features.feedback import FeedbackDataset, build_feedback_dataset


@dataclass(frozen=True)
class QueueItem:
    prediction_id: str
    due_at: str
    state: str
    reason: str | None


@dataclass(frozen=True)
class FeedbackWriteResult:
    inserted: int
    duplicates: int
    revised: int


class FeedbackStore:
    """Persist immutable predictions and revisable, evidence-backed outcomes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "feedback.sqlite3"
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def __enter__(self) -> "FeedbackStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                outcome_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                label_available_at TEXT
            );
            CREATE TABLE IF NOT EXISTS outcome_revisions (
                revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                outcome_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE(outcome_id, payload_sha256)
            );
            CREATE TABLE IF NOT EXISTS maturation_queue (
                prediction_id TEXT PRIMARY KEY,
                due_at TEXT NOT NULL,
                state TEXT NOT NULL,
                reason TEXT,
                checked_at TEXT
            );
            """
        )
        self._connection.commit()

    @staticmethod
    def _encoded(record: PredictionRecord | OutcomeRecord) -> tuple[str, str]:
        encoded = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def record_predictions(self, predictions: Iterable[PredictionRecord]) -> FeedbackWriteResult:
        records = tuple(predictions)
        inserted = duplicates = revised = 0
        with self._connection:
            for prediction in records:
                encoded, digest = self._encoded(prediction)
                existing = self._connection.execute(
                    "SELECT payload_sha256 FROM predictions WHERE prediction_id = ?", (prediction.prediction_id,)
                ).fetchone()
                if existing is not None:
                    if existing["payload_sha256"] != digest:
                        raise ValueError("predictions are immutable; conflicting payload")
                    duplicates += 1
                    continue
                due = (
                    datetime.fromisoformat(prediction.created_at.replace("Z", "+00:00"))
                    + timedelta(seconds=prediction.horizon_seconds)
                ).isoformat()
                self._connection.execute(
                    "INSERT INTO predictions(prediction_id, payload_json, payload_sha256, created_at) VALUES (?, ?, ?, ?)",
                    (prediction.prediction_id, encoded, digest, prediction.created_at),
                )
                self._connection.execute(
                    "INSERT INTO maturation_queue(prediction_id, due_at, state, reason) VALUES (?, ?, 'waiting', NULL)",
                    (prediction.prediction_id, due),
                )
                inserted += 1
        return FeedbackWriteResult(inserted, duplicates, revised)

    def record_outcomes(self, outcomes: Iterable[OutcomeRecord]) -> FeedbackWriteResult:
        records = tuple(outcomes)
        inserted = duplicates = revised = 0
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            for outcome in records:
                encoded, digest = self._encoded(outcome)
                existing = self._connection.execute(
                    "SELECT payload_json, payload_sha256 FROM outcomes WHERE outcome_id = ?", (outcome.outcome_id,)
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        "INSERT INTO outcomes(outcome_id, payload_json, payload_sha256, observed_at, label_available_at) VALUES (?, ?, ?, ?, ?)",
                        (outcome.outcome_id, encoded, digest, outcome.observed_at, outcome.label_available_at),
                    )
                    inserted += 1
                    continue
                if existing["payload_sha256"] == digest:
                    duplicates += 1
                    continue
                self._connection.execute(
                    "INSERT OR IGNORE INTO outcome_revisions(outcome_id, payload_json, payload_sha256, recorded_at) VALUES (?, ?, ?, ?)",
                    (outcome.outcome_id, existing["payload_json"], existing["payload_sha256"], now),
                )
                self._connection.execute(
                    "UPDATE outcomes SET payload_json = ?, payload_sha256 = ?, observed_at = ?, label_available_at = ? WHERE outcome_id = ?",
                    (encoded, digest, outcome.observed_at, outcome.label_available_at, outcome.outcome_id),
                )
                revised += 1
        return FeedbackWriteResult(inserted, duplicates, revised)

    def list_predictions(self) -> tuple[PredictionRecord, ...]:
        rows = self._connection.execute("SELECT payload_json FROM predictions ORDER BY created_at, prediction_id").fetchall()
        return tuple(PredictionRecord.from_dict(json.loads(row["payload_json"])) for row in rows)

    def list_outcomes(self) -> tuple[OutcomeRecord, ...]:
        rows = self._connection.execute("SELECT payload_json FROM outcomes ORDER BY label_available_at, outcome_id").fetchall()
        return tuple(OutcomeRecord.from_dict(json.loads(row["payload_json"])) for row in rows)

    def list_outcome_revisions(self, outcome_id: str) -> tuple[OutcomeRecord, ...]:
        rows = self._connection.execute(
            "SELECT payload_json FROM outcome_revisions WHERE outcome_id = ? ORDER BY revision_id", (outcome_id,)
        ).fetchall()
        return tuple(OutcomeRecord.from_dict(json.loads(row["payload_json"])) for row in rows)

    def mature(self, *, as_of_time: str) -> tuple[QueueItem, ...]:
        """Reconcile waiting labels without declaring missing data as success."""

        cutoff = datetime.fromisoformat(as_of_time.replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            raise ValueError("as_of_time must include a timezone")
        outcomes = self.list_outcomes()
        by_prediction: dict[str, list[OutcomeRecord]] = {}
        for outcome in outcomes:
            available = (
                datetime.fromisoformat(outcome.label_available_at.replace("Z", "+00:00"))
                if outcome.label_available_at is not None
                else None
            )
            if available is not None and available <= cutoff:
                by_prediction.setdefault(outcome.prediction_id, []).append(outcome)
        rows = self._connection.execute("SELECT * FROM maturation_queue ORDER BY due_at, prediction_id").fetchall()
        updated: list[QueueItem] = []
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            for row in rows:
                due = datetime.fromisoformat(row["due_at"].replace("Z", "+00:00"))
                available_outcomes = by_prediction.get(row["prediction_id"], [])
                if available_outcomes:
                    # A prediction may have an observed-market label and a
                    # separately recorded manual/counterfactual outcome. The
                    # queue is ready when any available outcome is trainable;
                    # the dataset keeps each outcome distinct for review.
                    state = (
                        "ready"
                        if any(outcome.status in {"observed", "censored"} for outcome in available_outcomes)
                        else "unresolved"
                    )
                    reason = None if state == "ready" else "outcome_unresolved_or_invalidated"
                elif due <= cutoff:
                    state, reason = "missing", "label_due_without_available_outcome"
                else:
                    state, reason = "waiting", None
                self._connection.execute(
                    "UPDATE maturation_queue SET state = ?, reason = ?, checked_at = ? WHERE prediction_id = ?",
                    (state, reason, now, row["prediction_id"]),
                )
                updated.append(QueueItem(row["prediction_id"], row["due_at"], state, reason))
        return tuple(updated)

    def list_queue(self) -> tuple[QueueItem, ...]:
        rows = self._connection.execute("SELECT * FROM maturation_queue ORDER BY due_at, prediction_id").fetchall()
        return tuple(QueueItem(row["prediction_id"], row["due_at"], row["state"], row["reason"]) for row in rows)

    def dataset(self, *, as_of_time: str) -> FeedbackDataset:
        return build_feedback_dataset(self.list_predictions(), self.list_outcomes(), as_of_time=as_of_time)


__all__ = ["FeedbackStore", "FeedbackWriteResult", "QueueItem"]
