"""Reconstructible experiment run records and bounded search budgets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ExperimentRun:
    run_id: str
    source_hash: str
    code_hash: str
    data_hash: str
    config_hash: str
    seeds: tuple[int, ...]
    parameter_count: int
    training_seconds: float
    search_trials: int
    search_budget: int
    status: str
    failure: str | None
    started_at: str
    finished_at: str | None


class RunTracker:
    def __init__(self, *, search_budget: int = 20) -> None:
        if search_budget <= 0:
            raise ValueError("search budget must be positive")
        self.search_budget = search_budget
        self.runs: list[ExperimentRun] = []

    def start(self, *, source: Any, code: Any, data: Any, config: Any, seeds: tuple[int, ...], parameter_count: int) -> str:
        if not seeds or parameter_count < 0:
            raise ValueError("run metadata is invalid")
        hashes = [_hash(value) for value in (source, code, data, config)]
        run_id = "run-" + hashlib.sha256(("|".join(hashes) + str(seeds)).encode()).hexdigest()[:12]
        self.runs.append(ExperimentRun(run_id, hashes[0], hashes[1], hashes[2], hashes[3], seeds, parameter_count, 0.0, 0, self.search_budget, "running", None, datetime.now(timezone.utc).isoformat(), None))
        return run_id

    def trial(self, run_id: str) -> int:
        index = self._index(run_id)
        run = self.runs[index]
        trials = run.search_trials + 1
        if trials > run.search_budget:
            self.runs[index] = ExperimentRun(
                run.run_id,
                run.source_hash,
                run.code_hash,
                run.data_hash,
                run.config_hash,
                run.seeds,
                run.parameter_count,
                run.training_seconds,
                run.search_trials,
                run.search_budget,
                "failed",
                "search_budget_exceeded",
                run.started_at,
                datetime.now(timezone.utc).isoformat(),
            )
            raise BudgetExceeded(f"search budget exceeded for {run_id}")
        self.runs[index] = ExperimentRun(run.run_id, run.source_hash, run.code_hash, run.data_hash, run.config_hash, run.seeds, run.parameter_count, run.training_seconds, trials, run.search_budget, run.status, run.failure, run.started_at, run.finished_at)
        return trials

    def finish(self, run_id: str, *, training_seconds: float, status: str = "completed") -> ExperimentRun:
        if training_seconds < 0 or status not in {"completed", "failed"}:
            raise ValueError("run completion metadata is invalid")
        index = self._index(run_id)
        run = self.runs[index]
        updated = ExperimentRun(run.run_id, run.source_hash, run.code_hash, run.data_hash, run.config_hash, run.seeds, run.parameter_count, training_seconds, run.search_trials, run.search_budget, status, run.failure, run.started_at, datetime.now(timezone.utc).isoformat())
        self.runs[index] = updated
        return updated

    def fail(self, run_id: str, error: str) -> ExperimentRun:
        if not error:
            raise ValueError("failure must be recorded")
        index = self._index(run_id)
        run = self.runs[index]
        updated = ExperimentRun(run.run_id, run.source_hash, run.code_hash, run.data_hash, run.config_hash, run.seeds, run.parameter_count, run.training_seconds, run.search_trials, run.search_budget, "failed", error, run.started_at, datetime.now(timezone.utc).isoformat())
        self.runs[index] = updated
        return updated

    def _index(self, run_id: str) -> int:
        for index, run in enumerate(self.runs):
            if run.run_id == run_id:
                return index
        raise KeyError(run_id)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
