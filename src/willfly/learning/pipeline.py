"""Restart-safe, bounded research pipeline callbacks.

The watcher owns scheduling; this module owns the concrete local read-only
stage integrations. Every successful stage publishes an immutable JSON
artifact plus an atomic ``latest`` alias. Stage runs and artifact identities
are persisted in SQLite so a crash can be recovered without rerunning a
completed input, and no stage has a signing or broadcast surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("pipeline timestamps must include a timezone")
    return parsed


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical(value))


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class StageBudget:
    timeout_seconds: int
    memory_bytes: int
    cpu_seconds: int
    max_output_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if min(self.timeout_seconds, self.memory_bytes, self.cpu_seconds, self.max_output_bytes) <= 0:
            raise ValueError("pipeline stage budgets must be positive")


@dataclass(frozen=True)
class PipelineExecution:
    stage: str
    status: str
    reason: str | None
    run_id: str
    idempotency_key: str
    artifacts: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "reason": self.reason,
            "run_id": self.run_id,
            "idempotency_key": self.idempotency_key,
            "artifacts": [dict(item) for item in self.artifacts],
        }


CommandRunner = Callable[[Sequence[str], StageBudget, Path], subprocess.CompletedProcess[str]]


class PipelineConfig:
    """Validated path and budget view over ``pipeline-v0.1.json``."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.pipeline.v0.1":
            raise ValueError("pipeline config schema version is unsupported")
        if payload.get("execution_scope") != "read_only_observation":
            raise ValueError("pipeline execution scope must be read_only_observation")
        if payload.get("signing") is not False or payload.get("broadcast") is not False:
            raise ValueError("pipeline signing and broadcast must both be false")
        project = payload.get("project_dir", "../..")
        if not isinstance(project, str) or not project:
            raise ValueError("pipeline project_dir is required")
        project_path = Path(project)
        self.project_dir = (self.path.parent / project_path).resolve() if not project_path.is_absolute() else project_path
        self.payload = payload
        self.config_hash = _hash_file(self.path)
        paths = payload.get("paths", {})
        if not isinstance(paths, dict):
            raise ValueError("pipeline paths must be an object")
        self.paths = dict(paths)
        budgets = payload.get("budgets", {})
        if not isinstance(budgets, dict):
            raise ValueError("pipeline budgets must be an object")
        self.budgets = {
            stage: StageBudget(
                timeout_seconds=int(values["timeout_seconds"]),
                memory_bytes=int(values["memory_bytes"]),
                cpu_seconds=int(values["cpu_seconds"]),
                max_output_bytes=int(values.get("max_output_bytes", 8 * 1024 * 1024)),
            )
            for stage, values in budgets.items()
            if isinstance(values, dict)
        }
        required = {"observation", "labels", "training", "evaluation"}
        if set(self.budgets) != required:
            raise ValueError("pipeline budgets must define observation, labels, training and evaluation")

    def path_value(self, key: str, *, required: bool = True) -> Path | None:
        raw = self.paths.get(key)
        if raw is None:
            if required:
                raise ValueError(f"pipeline path is not configured: {key}")
            return None
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"pipeline path is invalid: {key}")
        value = Path(raw)
        return value if value.is_absolute() else (self.project_dir / value).resolve()

    def value(self, section: str, key: str, default: Any = None) -> Any:
        values = self.payload.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"pipeline section is not an object: {section}")
        return values.get(key, default)


class PipelineRunner:
    """Execute one concrete watcher stage with durable artifact identity."""

    STAGES = frozenset({"observation", "labels", "training", "evaluation"})

    def __init__(
        self,
        config_path: str | Path,
        state_db: str | Path,
        *,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.config = PipelineConfig(config_path)
        self.state_db = Path(state_db)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.command_runner = command_runner or self._run_command
        self._last: list[PipelineExecution] = []
        self._connection = sqlite3.connect(self.state_db)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                reason TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                input_artifact_ids_json TEXT NOT NULL,
                artifact_ids_json TEXT NOT NULL,
                command_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pipeline_artifacts (
                artifact_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()
        with self._connection:
            self._connection.execute(
                "UPDATE pipeline_runs SET status = 'waiting', reason = 'interrupted_process_recovery', finished_at = NULL WHERE status = 'running'"
            )

    def __enter__(self) -> "PipelineRunner":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @property
    def last_executions(self) -> tuple[PipelineExecution, ...]:
        return tuple(self._last)

    def run(self, stage: str, *, observed_at: str) -> PipelineExecution:
        if stage not in self.STAGES:
            raise ValueError(f"unsupported pipeline stage: {stage}")
        _instant(observed_at)
        input_rows = self._input_artifacts(stage)
        input_ids = tuple(str(row["artifact_id"]) for row in input_rows)
        params = self._stage_parameters(stage, observed_at)
        idempotency_key = _hash_json(
            {
                "schema_version": "willfly.pipeline-run.v0.1",
                "stage": stage,
                "config_hash": self.config.config_hash,
                "input_artifact_ids": input_ids,
                "parameters": params,
            }
        )
        run_id = f"{stage}-{idempotency_key[:16]}"
        existing = self._connection.execute(
            "SELECT * FROM pipeline_runs WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing is not None and existing["status"] == "completed":
            artifacts = self._artifact_rows(json.loads(existing["artifact_ids_json"]))
            result = PipelineExecution(stage, "completed", "idempotent_reuse", run_id, idempotency_key, artifacts)
            self._last.append(result)
            return result
        if existing is None:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO pipeline_runs(run_id, stage, idempotency_key, status, reason, started_at, finished_at, input_artifact_ids_json, artifact_ids_json, command_json) VALUES (?, ?, ?, 'running', NULL, ?, NULL, ?, '[]', '[]')",
                    (run_id, stage, idempotency_key, observed_at, json.dumps(input_ids)),
                )
        else:
            with self._connection:
                self._connection.execute(
                    "UPDATE pipeline_runs SET run_id = ?, status = 'running', reason = NULL, started_at = ?, finished_at = NULL, input_artifact_ids_json = ?, artifact_ids_json = '[]', command_json = '[]' WHERE idempotency_key = ?",
                    (run_id, observed_at, json.dumps(input_ids), idempotency_key),
                )
        try:
            execution = self._dispatch(stage, observed_at, run_id, input_rows, params, idempotency_key)
        except Exception as exc:
            reason = f"stage_failed:{type(exc).__name__}"
            with self._connection:
                self._connection.execute(
                    "UPDATE pipeline_runs SET status = 'failed', reason = ?, finished_at = ? WHERE idempotency_key = ?",
                    (reason, observed_at, idempotency_key),
                )
            execution = PipelineExecution(stage, "failed", reason, run_id, idempotency_key)
        self._last.append(execution)
        return execution

    def _dispatch(
        self,
        stage: str,
        observed_at: str,
        run_id: str,
        input_rows: Sequence[sqlite3.Row],
        params: Mapping[str, Any],
        idempotency_key: str,
    ) -> PipelineExecution:
        if stage == "observation":
            result, command = self._observation(observed_at)
            if result is None:
                reason = str(command[-1]).removeprefix("waiting:") if command else "capture_not_configured"
                return self._finish_waiting(stage, run_id, idempotency_key, reason, command, observed_at)
            if result.get("status") == "waiting":
                return self._finish_waiting(
                    stage,
                    run_id,
                    idempotency_key,
                    str(result.get("reason", "capture_waiting")),
                    command,
                    observed_at,
                )
            artifact = self._publish(
                stage,
                result,
                observed_at=observed_at,
                input_artifact_ids=(),
                run_id=run_id,
                idempotency_key=idempotency_key,
                alias_key="observation_latest",
                summary={"command_result": result},
            )
            return self._finish_completed(stage, run_id, idempotency_key, (artifact,), command, observed_at)
        if not input_rows:
            return self._finish_waiting(stage, run_id, idempotency_key, "upstream_artifact_missing", (), observed_at)
        if stage == "labels":
            result, bundle, command = self._labels(observed_at, input_rows[0])
            if result is None or bundle is None:
                return self._finish_waiting(stage, run_id, idempotency_key, params.get("waiting_reason", "feedback_not_ready"), command, observed_at)
            artifact = self._publish(
                stage,
                bundle,
                observed_at=observed_at,
                input_artifact_ids=(str(input_rows[0]["artifact_id"]),),
                run_id=run_id,
                idempotency_key=idempotency_key,
                alias_key="corpus_latest",
                summary={"command_result": result},
            )
            return self._finish_completed(stage, run_id, idempotency_key, (artifact,), command, observed_at)
        if stage == "training":
            report, command = self._training(observed_at, input_rows[0])
            if report is None:
                return self._finish_waiting(stage, run_id, idempotency_key, params.get("waiting_reason", "training_not_ready"), command, observed_at)
            artifact = self._publish(
                stage,
                report,
                observed_at=observed_at,
                input_artifact_ids=(str(input_rows[0]["artifact_id"]),),
                run_id=run_id,
                idempotency_key=idempotency_key,
                alias_key="training_latest",
                summary={"training_status": report.get("status")},
            )
            return self._finish_completed(stage, run_id, idempotency_key, (artifact,), command, observed_at)
        artifacts, reason, commands = self._evaluation(observed_at, input_rows)
        status = "completed" if artifacts else "waiting"
        if status == "completed":
            return self._finish_completed(stage, run_id, idempotency_key, tuple(artifacts), commands, observed_at, reason=reason)
        return self._finish_waiting(stage, run_id, idempotency_key, reason or "evaluation_not_ready", commands, observed_at)

    def _stage_parameters(self, stage: str, observed_at: str) -> dict[str, Any]:
        if stage == "observation":
            values = self.config.payload.get("observation", {})
            parameters = dict(values) if isinstance(values, dict) else {}
        elif stage == "labels":
            parameters = {"as_of_time": observed_at}
        else:
            values = self.config.payload.get(stage, {})
            parameters = dict(values) if isinstance(values, dict) else {}
        if stage == "labels":
            parameters["as_of_time"] = observed_at
        return parameters

    def _input_artifacts(self, stage: str) -> tuple[sqlite3.Row, ...]:
        if stage == "observation":
            return ()
        upstream = "observation" if stage == "labels" else "labels"
        if stage == "evaluation":
            rows = self._latest_artifacts("training")
            rows += self._latest_artifacts("labels")
            return rows
        return self._latest_artifacts(upstream)

    def _latest_artifacts(self, stage: str) -> tuple[sqlite3.Row, ...]:
        row = self._connection.execute(
            "SELECT a.* FROM pipeline_artifacts a JOIN pipeline_runs r ON instr(r.artifact_ids_json, a.artifact_id) > 0 WHERE a.stage = ? AND r.status = 'completed' ORDER BY a.created_at DESC LIMIT 1",
            (stage,),
        ).fetchone()
        return () if row is None else (row,)

    def _artifact_rows(self, artifact_ids: Sequence[str]) -> tuple[dict[str, Any], ...]:
        result = []
        for artifact_id in artifact_ids:
            row = self._connection.execute(
                "SELECT artifact_id, stage, path, file_hash, metadata_json, created_at FROM pipeline_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            if row is not None:
                result.append({"artifact_id": row["artifact_id"], "stage": row["stage"], "path": row["path"], "file_hash": row["file_hash"], "created_at": row["created_at"], "metadata": json.loads(row["metadata_json"])})
        return tuple(result)

    def _finish_waiting(
        self,
        stage: str,
        run_id: str,
        idempotency_key: str,
        reason: str,
        command: Sequence[str] | str,
        observed_at: str,
    ) -> PipelineExecution:
        with self._connection:
            self._connection.execute(
                "UPDATE pipeline_runs SET status = 'waiting', reason = ?, finished_at = ?, command_json = ? WHERE idempotency_key = ?",
                (reason, observed_at, json.dumps(list(command) if not isinstance(command, str) else [command]), idempotency_key),
            )
        return PipelineExecution(stage, "waiting", reason, run_id, idempotency_key)

    def _finish_completed(
        self,
        stage: str,
        run_id: str,
        idempotency_key: str,
        artifacts: Sequence[dict[str, Any]],
        command: Sequence[str] | str,
        observed_at: str,
        *,
        reason: str | None = None,
    ) -> PipelineExecution:
        artifact_ids = [str(item["artifact_id"]) for item in artifacts]
        with self._connection:
            self._connection.execute(
                "UPDATE pipeline_runs SET status = 'completed', reason = ?, finished_at = ?, artifact_ids_json = ?, command_json = ? WHERE idempotency_key = ?",
                (reason, observed_at, json.dumps(artifact_ids), json.dumps(list(command) if not isinstance(command, str) else [command]), idempotency_key),
            )
        return PipelineExecution(stage, "completed", reason, run_id, idempotency_key, tuple(dict(item) for item in artifacts))

    def _observation(self, observed_at: str) -> tuple[dict[str, Any] | None, Sequence[str]]:
        mode = self.config.value("observation", "mode", "backfill")
        if mode == "reuse":
            input_path = self.config.path_value("observation_input")
            assert input_path is not None
            payload = self._load_reuse(input_path, "observation")
            header_evidence = payload.get("header_evidence")
            if payload.get("status") != "executed" or payload.get("operating_mode") != "read_only":
                raise ValueError("reused observation must be an executed read-only manifest")
            if not isinstance(header_evidence, dict) or header_evidence.get("coverage_state") != "complete":
                raise ValueError("reused observation must have complete header coverage")
            return {
                "status": "executed",
                "reused": True,
                "input": str(input_path),
                "manifest": payload,
            }, ("reuse", str(input_path))
        if mode == "rolling_backfill":
            bootstrap = self.config.value("observation", "bootstrap_from_block")
            if bootstrap is not None and (isinstance(bootstrap, bool) or not isinstance(bootstrap, int) or bootstrap < 0):
                return None, ("rolling-backfill", "waiting:rolling_bootstrap_from_block_invalid")
            config_path = self.config.path_value("source_config")
            store_dir = self.config.path_value("store_dir")
            assert config_path is not None and store_dir is not None
            command = [
                sys.executable,
                "-m",
                "willfly",
                "rolling-backfill",
                "--config",
                str(config_path),
                "--max-blocks",
                str(int(self.config.value("observation", "max_blocks", 500))),
                "--confirmation-lag-blocks",
                str(int(self.config.value("observation", "confirmation_lag_blocks", 12))),
                "--store-dir",
                str(store_dir),
                "--source",
                str(self.config.value("observation", "source", "pipeline-live-readonly")),
                "--page-size",
                str(int(self.config.value("observation", "page_size", 250))),
            ]
            if bootstrap is not None:
                command.extend(["--bootstrap-from-block", str(bootstrap)])
            result = self._run_json(command, "observation")
            return result, command
        start = self.config.value("observation", "from_block")
        finish = self.config.value("observation", "to_block")
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            return None, ("capture", "waiting:capture_from_block_not_configured")
        if isinstance(finish, bool) or not isinstance(finish, int) or finish < start:
            return None, ("capture", "waiting:capture_to_block_not_configured")
        max_blocks = int(self.config.value("observation", "max_blocks", 500))
        if finish - start + 1 > max_blocks:
            return None, ("capture", "waiting:capture_window_exceeds_bound")
        config_path = self.config.path_value("source_config")
        store_dir = self.config.path_value("store_dir")
        source = self.config.value("observation", "source", "pipeline-live-readonly")
        operation = "backfill" if mode == "backfill" else "capture"
        command = [
            sys.executable,
            "-m",
            "willfly",
            operation,
            "--config",
            str(config_path),
            "--from-block",
            str(start),
            "--to-block",
            str(finish),
            "--store-dir",
            str(store_dir),
            "--source",
            str(source),
        ]
        if operation == "backfill":
            command.extend(["--page-size", str(int(self.config.value("observation", "page_size", 2000)))])
        result = self._run_json(command, "observation")
        return result, command

    def _labels(self, observed_at: str, observation: sqlite3.Row) -> tuple[dict[str, Any] | None, dict[str, Any] | None, Sequence[str]]:
        if self.config.value("labels", "mode", "build") == "reuse":
            input_path = self.config.path_value("corpus_input")
            assert input_path is not None
            bundle = self._load_reuse(input_path, "labels")
            self._validate_source_provenance(bundle.get("provenance"), "reused corpus")
            return {"status": "ready", "reused": True, "input": str(input_path)}, bundle, ("reuse", str(input_path))
        source = self.config.value("observation", "source", "pipeline-live-readonly")
        config_path = self.config.path_value("source_config")
        store_dir = self.config.path_value("store_dir")
        feedback_dir = self.config.path_value("feedback_dir")
        latest = self.config.path_value("corpus_latest")
        assert config_path is not None and store_dir is not None and feedback_dir is not None and latest is not None
        latest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".market-feedback-", suffix=".json", dir=latest.parent, delete=False) as handle:
            temporary = Path(handle.name)
        command = [
            sys.executable,
            "-m",
            "willfly",
            "market-feedback-build",
            "--config",
            str(config_path),
            "--store-dir",
            str(store_dir),
            "--source",
            str(source),
            "--as-of-time",
            observed_at,
            "--output",
            str(temporary),
            "--feedback-dir",
            str(feedback_dir),
        ]
        try:
            result = self._run_json(command, "labels")
            if result.get("status") == "waiting":
                return result, None, command
            bundle = json.loads(temporary.read_text(encoding="utf-8"))
            if not isinstance(bundle, dict) or bundle.get("schema_version") != "willfly.market-feedback-bundle.v0.1":
                raise ValueError("market feedback command did not publish a typed bundle")
            return result, bundle, command
        finally:
            temporary.unlink(missing_ok=True)

    def _training(self, observed_at: str, labels: sqlite3.Row) -> tuple[dict[str, Any] | None, Sequence[str]]:
        if self.config.value("training", "mode", "train") == "reuse":
            input_path = self.config.path_value("training_input")
            assert input_path is not None
            report = self._load_reuse(input_path, "training")
            if report.get("status") != "completed":
                raise ValueError("reused training report must be completed")
            self._validate_source_provenance(report.get("provenance"), "reused training report")
            return report, ("reuse", str(input_path))
        manifest = self.config.path_value("training_manifest")
        data_root = self.config.path_value("training_data_root")
        feedback_dir = self.config.path_value("feedback_dir")
        assert manifest is not None and data_root is not None and feedback_dir is not None
        corpus = Path(labels["path"])
        report = self.config.path_value("training_latest")
        checkpoint_dir = self.config.path_value("training_checkpoint_dir")
        assert report is not None and checkpoint_dir is not None
        command = [
            sys.executable,
            str(self.config.project_dir / "scripts" / "train_malecns_feedback.py"),
            "--manifest",
            str(manifest),
            "--data-root",
            str(data_root),
            "--feedback-dir",
            str(feedback_dir),
            "--corpus",
            str(corpus),
            "--as-of-time",
            observed_at,
            "--max-edges",
            str(int(self.config.value("training", "max_edges", 100000))),
            "--partition-index",
            str(int(self.config.value("training", "partition_index", 0))),
            "--partition-count",
            str(int(self.config.value("training", "partition_count", 1))),
            "--seeds",
            str(self.config.value("training", "seeds", "7,17,27")),
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--max-training-examples",
            str(int(self.config.value("training", "max_examples", 100000))),
        ]
        report = self._run_json(command, "training")
        return (report if report.get("status") == "completed" else None), command

    def _evaluation(
        self,
        observed_at: str,
        inputs: Sequence[sqlite3.Row],
    ) -> tuple[list[dict[str, Any]], str | None, Sequence[str]]:
        training = next((row for row in inputs if row["stage"] == "training"), None)
        if training is None:
            return [], "training_artifact_missing", ()
        input_artifact_ids = tuple(str(row["artifact_id"]) for row in inputs)
        templates = self.config.path_value("templates", required=False)
        if templates is None:
            return [], "signal_templates_not_configured", ()
        actions = self.config.path_value("actions", required=False)
        exit_kinds = self.config.path_value("exit_kinds", required=False)
        if actions is None:
            return [], "signal_actions_not_configured", ()
        training_report = Path(training["path"])
        model_output = self.config.path_value("model_output_latest")
        signals = self.config.path_value("signals_latest")
        assert model_output is not None and signals is not None
        model_output.parent.mkdir(parents=True, exist_ok=True)
        signals.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".model-output-", suffix=".json", dir=model_output.parent, delete=False) as model_handle:
            model_temp = Path(model_handle.name)
        with tempfile.NamedTemporaryFile(prefix=".signals-", suffix=".json", dir=signals.parent, delete=False) as signal_handle:
            signal_temp = Path(signal_handle.name)
        model = self.config.payload.get("model", {})
        if not isinstance(model, dict):
            model = {}
        model_command = [
            sys.executable,
            "-m",
            "willfly",
            "model-output",
            "--experiment-report",
            str(training_report),
            "--templates",
            str(templates),
            "--output",
            str(model_temp),
            "--model-id",
            str(model.get("model_id", "willfly-malecns-readout")),
            "--model-version",
            str(model.get("model_version", "malecns-feedback-v0.1")),
            "--run-ref",
            str(model.get("run_ref", "pipeline")),
            "--as-of-time",
            observed_at,
            "--actions",
            str(actions),
        ]
        configured_run_id = model.get("run_id")
        if isinstance(configured_run_id, str) and configured_run_id:
            model_command[model_command.index("--actions"):model_command.index("--actions")] = ["--run-id", configured_run_id]
        if exit_kinds is not None:
            model_command.extend(["--exit-kinds", str(exit_kinds)])
        commands: list[str] = list(model_command)
        try:
            model_result = self._run_json(model_command, "evaluation")
            model_payload = json.loads(model_temp.read_text(encoding="utf-8"))
            training_state = model_payload.get("training_state")
            training_provenance = training_state.get("provenance") if isinstance(training_state, dict) else None
            required_provenance = (
                "source",
                "config_hash",
                "canonical_tip_hash",
                "canonical_event_set_hash",
                "canonical_checkpoint_hash",
            )
            if not isinstance(training_provenance, dict) or any(
                not isinstance(training_provenance.get(field), str) or not training_provenance[field]
                for field in required_provenance
            ):
                return [], "model_output_provenance_incomplete", list(model_command)
            signal_command = [sys.executable, "-m", "willfly", "signal-build", "--input", str(model_temp), "--output", str(signal_temp)]
            commands.extend(signal_command)
            self._run_json(signal_command, "evaluation")
            signal_payload = json.loads(signal_temp.read_text(encoding="utf-8"))
            proposals = signal_payload.get("proposals", [])
            if not isinstance(proposals, list) or any(
                not isinstance(item, dict) or item.get("action") != "abstain" or item.get("execution_scope") != "manual_only"
                for item in proposals
            ):
                return [], "research_only_publication_requires_abstain_manual_proposals", commands
            evaluation_status = "waiting"
            evaluation_payload: dict[str, Any] | None = None
            points = self.config.path_value("evaluation_points", required=False)
            candidate = self.config.value("evaluation", "candidate_version")
            active = self.config.value("evaluation", "active_version")
            dataset_hash = self.config.value("evaluation", "dataset_hash")
            if points is not None and all(isinstance(value, str) and value for value in (candidate, active, dataset_hash)):
                evaluation_command = [
                    sys.executable,
                    "-m",
                    "willfly",
                    "model-evaluate",
                    "--points",
                    str(points),
                    "--candidate-version",
                    str(candidate),
                    "--active-version",
                    str(active),
                    "--evaluated-at",
                    observed_at,
                    "--dataset-hash",
                    str(dataset_hash),
                    "--minimum-forward-windows",
                    str(int(self.config.value("evaluation", "minimum_forward_windows", 2))),
                    "--minimum-points-per-window",
                    str(int(self.config.value("evaluation", "minimum_points_per_window", 2))),
                ]
                commands.extend(evaluation_command)
                evaluation_payload = self._run_json(evaluation_command, "evaluation")
                evaluation_status = str(evaluation_payload.get("status", "inconclusive"))
            provenance = {
                "evaluation_status": evaluation_status,
                "evaluation_artifact_hash": None if evaluation_payload is None else _hash_json(evaluation_payload),
                "training_artifact_id": training["artifact_id"],
                "pipeline_config_hash": self.config.config_hash,
                "execution_scope": "research_only",
                "signing": False,
                "broadcast": False,
            }
            signal_payload = dict(signal_payload)
            signal_payload["pipeline_provenance"] = provenance
            model_payload = dict(model_payload)
            model_payload["pipeline_provenance"] = provenance
            artifacts = [
                self._publish(
                    "model_output",
                    model_payload,
                    observed_at=observed_at,
                    input_artifact_ids=input_artifact_ids,
                    run_id="evaluation",
                    idempotency_key=_hash_json({"model": model_payload.get("training_state"), "inputs": input_artifact_ids}),
                    alias_key="model_output_latest",
                    summary={"evaluation_status": evaluation_status, "command_result": model_result},
                ),
                self._publish(
                    "signal",
                    signal_payload,
                    observed_at=observed_at,
                    input_artifact_ids=input_artifact_ids,
                    run_id="evaluation",
                    idempotency_key=_hash_json({"signal": signal_payload.get("pipeline_provenance"), "inputs": input_artifact_ids}),
                    alias_key="signals_latest",
                    summary={"evaluation_status": evaluation_status, "proposal_count": len(proposals)},
                ),
            ]
            reason = "published_research_only_evaluation_waiting" if evaluation_status == "waiting" else f"published_research_only_evaluation_{evaluation_status}"
            return artifacts, reason, commands
        finally:
            model_temp.unlink(missing_ok=True)
            signal_temp.unlink(missing_ok=True)

    def _run_json(self, command: Sequence[str], stage: str) -> dict[str, Any]:
        completed = self.command_runner(command, self.config.budgets[stage], self.config.project_dir)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip().replace("\n", " ")[:500]
            raise RuntimeError(f"{stage} subprocess exited {completed.returncode}: {stderr}")
        stdout = completed.stdout or ""
        if len(stdout.encode("utf-8")) > self.config.budgets[stage].max_output_bytes:
            raise RuntimeError(f"{stage} subprocess output exceeded budget")
        payload = json.loads(stdout)
        if not isinstance(payload, dict):
            raise ValueError(f"{stage} subprocess did not return a JSON object")
        return payload

    @staticmethod
    def _load_reuse(path: Path, stage: str) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError(f"{stage} reuse input does not exist: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{stage} reuse input must be a JSON object")
        return payload

    @staticmethod
    def _validate_source_provenance(value: object, label: str) -> dict[str, Any]:
        required = (
            "source",
            "config_hash",
            "canonical_tip_hash",
            "canonical_event_set_hash",
            "canonical_checkpoint_hash",
        )
        if not isinstance(value, dict) or any(
            not isinstance(value.get(field), str) or not value[field] for field in required
        ):
            raise ValueError(f"{label} source provenance is incomplete")
        return dict(value)

    @staticmethod
    def _run_command(command: Sequence[str], budget: StageBudget, cwd: Path) -> subprocess.CompletedProcess[str]:
        preexec_fn = None
        if os.name == "posix":
            import resource

            def limit() -> None:
                os.setsid()
                resource.setrlimit(resource.RLIMIT_CPU, (budget.cpu_seconds, budget.cpu_seconds + 1))
                # macOS exposes RLIMIT_AS but rejects changing it. WSL/Linux
                # enforce the configured address-space budget; on Darwin the
                # timeout/CPU limits still apply and the memory budget remains
                # recorded in the run/artifact metadata.
                if sys.platform.startswith("linux"):
                    resource.setrlimit(resource.RLIMIT_AS, (budget.memory_bytes, budget.memory_bytes))

            preexec_fn = limit
        return subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=budget.timeout_seconds,
            check=False,
            preexec_fn=preexec_fn,
        )

    def _publish(
        self,
        stage: str,
        payload: Mapping[str, Any],
        *,
        observed_at: str,
        input_artifact_ids: Sequence[str],
        run_id: str,
        idempotency_key: str,
        alias_key: str,
        summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError(f"{stage} artifact payload must be an object")
        base = dict(payload)
        provenance = dict(base.get("pipeline_provenance", {})) if isinstance(base.get("pipeline_provenance"), dict) else {}
        source_provenance = base.get("provenance")
        if not isinstance(source_provenance, dict):
            training_state = base.get("training_state")
            source_provenance = training_state.get("provenance") if isinstance(training_state, dict) else None
        if source_provenance is not None:
            provenance["source_provenance"] = self._validate_source_provenance(
                source_provenance, f"{stage} artifact"
            )
        provenance.update(
            {
                "pipeline_schema_version": "willfly.pipeline-artifact.v0.1",
                "stage": stage,
                "pipeline_config_hash": self.config.config_hash,
                "input_artifact_ids": list(input_artifact_ids),
                "observed_at": observed_at,
                "execution_scope": "research_only",
                "signing": False,
                "broadcast": False,
            }
        )
        base["pipeline_provenance"] = provenance
        content_hash = _hash_json(base)
        artifact_id = _hash_json(
            {
                "stage": stage,
                "content_hash": content_hash,
                "input_artifact_ids": list(input_artifact_ids),
                "pipeline_config_hash": self.config.config_hash,
            }
        )
        provenance["content_hash"] = content_hash
        provenance["artifact_id"] = artifact_id
        base["pipeline_provenance"] = provenance
        artifact_dir = self.config.path_value("artifact_dir")
        assert artifact_dir is not None
        destination_dir = artifact_dir / stage
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{artifact_id}.json"
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(json.dumps(base, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
        file_hash = _hash_file(destination)
        metadata = {
            "artifact_id": artifact_id,
            "stage": stage,
            "path": str(destination),
            "file_hash": file_hash,
            "content_hash": content_hash,
            "input_artifact_ids": list(input_artifact_ids),
            "pipeline_config_hash": self.config.config_hash,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "summary": dict(summary),
            "execution_scope": "research_only",
            "signing": False,
            "broadcast": False,
        }
        sidecar = destination.with_suffix(".meta.json")
        sidecar_temp = sidecar.with_name(f".{sidecar.name}.tmp")
        sidecar_temp.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(sidecar_temp, sidecar)
        created_at = observed_at
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO pipeline_artifacts(artifact_id, stage, path, file_hash, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (artifact_id, stage, str(destination), file_hash, json.dumps(metadata, sort_keys=True), created_at),
            )
        alias = self.config.path_value(alias_key)
        assert alias is not None
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias_temp = alias.with_name(f".{alias.name}.tmp")
        alias_temp.write_bytes(destination.read_bytes())
        os.replace(alias_temp, alias)
        return metadata


__all__ = ["PipelineConfig", "PipelineExecution", "PipelineRunner", "StageBudget"]
