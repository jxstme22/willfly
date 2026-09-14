import json
from pathlib import Path
import subprocess

from willfly.learning.pipeline import PipelineRunner


def _config(tmp_path: Path, *, observation: dict | None = None) -> Path:
    paths = {
        "source_config": str(tmp_path / "source.json"),
        "store_dir": str(tmp_path / "observatory"),
        "feedback_dir": str(tmp_path / "feedback"),
        "artifact_dir": str(tmp_path / "artifacts"),
        "observation_latest": str(tmp_path / "observation-latest.json"),
        "corpus_latest": str(tmp_path / "corpus-latest.json"),
        "training_latest": str(tmp_path / "training-latest.json"),
        "training_checkpoint_dir": str(tmp_path / "checkpoints"),
        "training_manifest": str(tmp_path / "manifest.json"),
        "training_data_root": str(tmp_path / "connectome"),
        "model_output_latest": str(tmp_path / "model-output-latest.json"),
        "signals_latest": str(tmp_path / "signals-latest.json"),
        "templates": str(tmp_path / "templates.json"),
        "actions": str(tmp_path / "actions.json"),
        "exit_kinds": str(tmp_path / "exit-kinds.json"),
        "evaluation_points": None,
    }
    payload = {
        "schema_version": "willfly.pipeline.v0.1",
        "project_dir": str(Path.cwd()),
        "execution_scope": "read_only_observation",
        "signing": False,
        "broadcast": False,
        "paths": paths,
        "observation": observation or {"mode": "backfill", "from_block": 10, "to_block": 10, "max_blocks": 10, "page_size": 10, "source": "fixture"},
        "training": {"max_edges": 10, "partition_index": 0, "partition_count": 1, "seeds": "7", "max_examples": 10},
        "model": {"model_id": "fixture", "model_version": "fixture-v1", "run_ref": "fixture"},
        "evaluation": {"candidate_version": "", "active_version": "", "dataset_hash": "", "minimum_forward_windows": 1, "minimum_points_per_window": 1},
        "budgets": {
            stage: {"timeout_seconds": 5, "memory_bytes": 128 * 1024 * 1024, "cpu_seconds": 5, "max_output_bytes": 100000}
            for stage in ("observation", "labels", "training", "evaluation")
        },
    }
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_pipeline_rolling_observation_command_is_bounded_and_checkpointed(monkeypatch, tmp_path):
    monkeypatch.delenv("WILLFLY_CAPTURE_START_BLOCK", raising=False)
    config = _config(
        tmp_path,
        observation={
            "mode": "rolling_backfill",
            "bootstrap_from_block": None,
            "confirmation_lag_blocks": 12,
            "max_blocks": 500,
            "page_size": 250,
            "source": "fixture",
        },
    )
    commands = []

    def command_runner(command, _budget, _cwd):
        commands.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, '{"status":"waiting","reason":"bootstrap_required"}', "")

    with PipelineRunner(config, tmp_path / "pipeline.sqlite3", command_runner=command_runner) as runner:
        payload, command = runner._observation("2026-09-14T06:00:00Z")
    assert payload["status"] == "waiting"
    assert tuple(command) == commands[0]
    assert command[3] == "rolling-backfill"
    assert "--confirmation-lag-blocks" in command and command[command.index("--confirmation-lag-blocks") + 1] == "12"
    assert "--max-blocks" in command and command[command.index("--max-blocks") + 1] == "500"
    assert "--page-size" in command and command[command.index("--page-size") + 1] == "250"
    assert "--bootstrap-from-block" not in command


def test_pipeline_rolling_observation_uses_operator_bootstrap_and_tick_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLFLY_CAPTURE_START_BLOCK", "61692800")
    config = _config(
        tmp_path,
        observation={
            "mode": "rolling_backfill",
            "bootstrap_from_block": None,
            "confirmation_lag_blocks": 12,
            "max_blocks": 500,
            "page_size": 250,
            "source": "fixture",
        },
    )
    commands = []

    def command_runner(command, _budget, _cwd):
        commands.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, '{"status":"waiting","reason":"bootstrap_required"}', "")

    with PipelineRunner(config, tmp_path / "pipeline.sqlite3", command_runner=command_runner) as runner:
        first = runner.run("observation", observed_at="2026-09-14T06:00:00Z")
        second = runner.run("observation", observed_at="2026-09-14T06:00:15Z")
    assert first.idempotency_key != second.idempotency_key
    assert all("--bootstrap-from-block" in command for command in commands)
    assert all(command[command.index("--bootstrap-from-block") + 1] == "61692800" for command in commands)


def test_pipeline_labels_use_filter_bound_checkpoint_source(tmp_path):
    config = _config(
        tmp_path,
        observation={
            "mode": "rolling_backfill",
            "bootstrap_from_block": 10,
            "confirmation_lag_blocks": 12,
            "max_blocks": 500,
            "page_size": 250,
            "source": "bare-config-source",
        },
    )
    commands = []

    def command_runner(command, _budget, _cwd):
        commands.append(tuple(command))
        if "rolling-backfill" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                '{"status":"executed","checkpoint_source":"pipeline-live-readonly:4663:hash"}',
                "",
            )
        return subprocess.CompletedProcess(command, 0, '{"status":"waiting","reason":"no_canonical_checkpoint"}', "")

    with PipelineRunner(config, tmp_path / "pipeline.sqlite3", command_runner=command_runner) as runner:
        assert runner.run("observation", observed_at="2026-09-14T06:00:00Z").status == "completed"
        assert runner.run("labels", observed_at="2026-09-14T06:00:00Z").status == "waiting"
    labels_command = next(command for command in commands if "market-feedback-build" in command)
    assert labels_command[labels_command.index("--source") + 1] == "pipeline-live-readonly:4663:hash"


def test_pipeline_runs_bounded_chain_and_reuses_completed_artifacts(tmp_path):
    config = _config(tmp_path)
    calls = []

    def command_runner(command, _budget, _cwd):
        calls.append(tuple(command))
        if "market-feedback-build" in command:
            output = Path(command[command.index("--output") + 1])
            output.write_text(
                json.dumps(
                    {
                        "schema_version": "willfly.market-feedback-bundle.v0.1",
                        "as_of_time": "2026-09-14T06:00:00Z",
                        "predictions": [],
                        "outcomes": [],
                        "provenance": {"source": "fixture", "config_hash": "fixture", "canonical_tip_hash": "tip", "canonical_event_set_hash": "events", "canonical_checkpoint_hash": "checkpoint"},
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, '{"status":"ready"}', "")
        if "model-output" in command:
            output = Path(command[command.index("--output") + 1])
            output.write_text(
                json.dumps(
                    {
                        "schema_version": "willfly.model-output-bundle.v0.1",
                        "as_of_time": "2026-09-14T06:00:00Z",
                        "model_id": "fixture",
                        "model_version": "fixture-v1",
                        "run_ref": "fixture",
                        "templates": [],
                        "outputs": [],
                        "training_state": {
                            "status": "completed",
                            "provenance": {
                                "source": "fixture",
                                "config_hash": "fixture",
                                "canonical_tip_hash": "tip",
                                "canonical_event_set_hash": "events",
                                "canonical_checkpoint_hash": "checkpoint",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, '{"status":"ready"}', "")
        if any("train_malecns_feedback.py" in item for item in command):
            return subprocess.CompletedProcess(
                command,
                0,
                '{"status":"completed","provenance":{"source":"fixture","config_hash":"fixture","canonical_tip_hash":"tip","canonical_event_set_hash":"events","canonical_checkpoint_hash":"checkpoint"}}',
                "",
            )
        if "signal-build" in command:
            output = Path(command[command.index("--output") + 1])
            output.write_text(
                json.dumps(
                    {
                        "schema_version": "willfly.signal-snapshot.v0.1",
                        "as_of_time": "2026-09-14T06:00:00Z",
                        "predictions": [],
                        "proposals": [],
                        "market_readiness": {"spot": "research_only", "lp": "research_only"},
                        "training_state": {"status": "completed"},
                        "excluded": [],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, '{"status":"ready"}', "")
        return subprocess.CompletedProcess(command, 0, '{"status":"executed","event_count":1}', "")

    with PipelineRunner(config, tmp_path / "pipeline.sqlite3", command_runner=command_runner) as runner:
        observed_at = "2026-09-14T06:00:00Z"
        assert runner.run("observation", observed_at=observed_at).status == "completed"
        assert runner.run("labels", observed_at=observed_at).status == "completed"
        assert runner.run("training", observed_at=observed_at).status == "completed"
        evaluation = runner.run("evaluation", observed_at=observed_at)
        assert evaluation.status == "completed"
        assert evaluation.reason == "published_research_only_evaluation_waiting"
        assert (tmp_path / "signals-latest.json").is_file()
        reused = runner.run("evaluation", observed_at="2026-09-14T06:01:00Z")
        assert reused.status == "completed"
        assert reused.reason == "idempotent_reuse"
        assert len([item for item in calls if "model-output" in item]) == 1
        assert all(item["signing"] is False for item in evaluation.artifacts)


def test_pipeline_requeues_running_stage_after_restart(tmp_path):
    config = _config(tmp_path)
    state_db = tmp_path / "pipeline.sqlite3"
    with PipelineRunner(config, state_db, command_runner=lambda *_: subprocess.CompletedProcess([], 0, '{"status":"executed"}', "")):
        pass
    import sqlite3

    with sqlite3.connect(state_db) as connection:
        connection.execute(
            "INSERT INTO pipeline_runs(run_id, stage, idempotency_key, status, started_at, input_artifact_ids_json, artifact_ids_json, command_json) VALUES (?, ?, ?, 'running', ?, '[]', '[]', '[]')",
            ("crashed", "observation", "crashed-key", "2026-09-14T06:00:00Z"),
        )
    with PipelineRunner(config, state_db) as runner:
        row = runner._connection.execute("SELECT status, reason FROM pipeline_runs WHERE run_id = 'crashed'").fetchone()
        assert tuple(row) == ("waiting", "interrupted_process_recovery")


def test_pipeline_reuses_provenance_bound_observation_corpus_and_training(tmp_path):
    config = _config(tmp_path)
    provenance = {
        "source": "bounded-live-v4-corpus:4663:test",
        "config_hash": "source-config",
        "canonical_tip_hash": "tip",
        "canonical_event_set_hash": "events",
        "canonical_checkpoint_hash": "checkpoint",
    }
    observation_input = tmp_path / "observation.json"
    observation_input.write_text(
        json.dumps({"status": "executed", "operating_mode": "read_only", "header_evidence": {"coverage_state": "complete"}}),
        encoding="utf-8",
    )
    corpus_input = tmp_path / "corpus.json"
    corpus_input.write_text(
        json.dumps({"schema_version": "willfly.market-feedback-bundle.v0.1", "provenance": provenance}),
        encoding="utf-8",
    )
    training_input = tmp_path / "training.json"
    training_input.write_text(json.dumps({"status": "completed", "provenance": provenance}), encoding="utf-8")
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["paths"].update(
        observation_input=str(observation_input), corpus_input=str(corpus_input), training_input=str(training_input)
    )
    payload["observation"]["mode"] = "reuse"
    payload["labels"] = {"mode": "reuse"}
    payload["training"]["mode"] = "reuse"
    config.write_text(json.dumps(payload), encoding="utf-8")

    with PipelineRunner(config, tmp_path / "pipeline.sqlite3") as runner:
        assert runner.run("observation", observed_at="2026-09-14T06:00:00Z").status == "completed"
        assert runner.run("labels", observed_at="2026-09-14T06:00:00Z").status == "completed"
        assert runner.run("training", observed_at="2026-09-14T06:00:00Z").status == "completed"
        artifact = runner.last_executions[-1].artifacts[0]
        published = json.loads(Path(artifact["path"]).read_text(encoding="utf-8"))
        assert published["pipeline_provenance"]["source_provenance"] == provenance
