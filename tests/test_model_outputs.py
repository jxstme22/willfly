import json
from pathlib import Path
import subprocess
import sys

from willfly.cli import main
from willfly.domain import Confidence, InstrumentIdentity, PortfolioContext, PredictionRecord
from willfly.features.model_outputs import build_model_output_bundle


TOKEN = InstrumentIdentity(4663, "token", "0x" + "1" * 40, "native:ETH")
CONTEXT = PortfolioContext("2026-09-14T00:00:00Z", "flat", "public_only", "healthy", "100", (), ("obs:1",))


def _template() -> PredictionRecord:
    return PredictionRecord(
        "prediction-1",
        "signal-contract-v0.1.0",
        "spot_entry_net_return",
        300,
        TOKEN,
        "2026-09-14T00:00:00Z",
        "2026-09-13T23:59:59Z",
        "2026-09-14T00:00:15Z",
        "ordinary-template",
        "template-v1",
        100,
        200,
        Confidence("uncalibrated_score", score=5),
        CONTEXT,
        ("feature:1",),
    )


def _experiment(status: str = "completed") -> dict[str, object]:
    return {
        "schema_version": "connectome-experiment.v0.1",
        "run_id": "malecns-feedback-seed-7",
        "status": status,
        "graph_hash": "a" * 64,
        "train_count": 4,
        "heldout_count": 1,
        "resource_seconds": 0.25,
        "checkpoint_path": None,
        "reasons": [] if status == "completed" else ["insufficient_qualified_train_examples"],
        "models": [
            {
                "model_name": "fly",
                "predictions": [["feedback:prediction-1", 123.4, 110, "validation"]],
            }
        ]
        if status == "completed"
        else [],
    }


def test_completed_experiment_metric_becomes_lineaged_model_output_bundle():
    bundle = build_model_output_bundle(
        _experiment(),
        [_template()],
        model_name="fly",
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:malecns-feedback-seed-7",
        as_of_time="2026-09-14T00:01:00Z",
        actions_by_prediction={"prediction-1": "enter"},
        source_hash="b" * 64,
    )
    assert bundle["outputs"] == [{"sample_id": "feedback:prediction-1", "predicted_bps": 123.4}]
    assert bundle["training_state"]["graph_hash"] == "a" * 64
    assert bundle["training_state"]["experiment_report_hash"] == "b" * 64
    assert bundle["actions_by_prediction"] == {"prediction-1": "enter"}
    assert bundle["market_readiness"] == {"spot": "research_only", "lp": "research_only"}


def test_final_test_rows_are_not_exported_as_signal_outputs():
    experiment = _experiment()
    experiment["models"][0]["predictions"].append(["feedback:final", 90.0, 80, "test"])
    bundle = build_model_output_bundle(
        experiment,
        [_template()],
        model_name="fly",
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:seed-7",
        as_of_time="2026-09-14T00:01:00Z",
    )
    assert bundle["outputs"] == [{"sample_id": "feedback:prediction-1", "predicted_bps": 123.4}]
    assert bundle["training_state"]["excluded_final_test_output_count"] == 1


def test_waiting_experiment_exports_no_predictions_and_preserves_reason():
    bundle = build_model_output_bundle(
        _experiment("waiting"),
        [_template()],
        model_name="fly",
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:waiting",
        as_of_time="2026-09-14T00:01:00Z",
    )
    assert bundle["outputs"] == []
    assert bundle["training_state"]["status"] == "waiting"
    assert bundle["training_state"]["reasons"] == ["insufficient_qualified_train_examples"]


def test_model_output_cli_selects_one_seed_and_writes_typed_bundle(tmp_path: Path, capsys):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"experiment_results": [_experiment()]}), encoding="utf-8")
    templates = tmp_path / "templates.json"
    templates.write_text(
        json.dumps({"schema_version": "willfly.prediction-template-bundle.v0.1", "predictions": [_template().to_dict()]}),
        encoding="utf-8",
    )
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({"prediction-1": "enter"}), encoding="utf-8")
    output = tmp_path / "model-output.json"
    assert main(
        [
            "model-output",
            "--experiment-report",
            str(report),
            "--templates",
            str(templates),
            "--output",
            str(output),
            "--model-id",
            "male-cns-readout",
            "--model-version",
            "candidate-v2",
            "--run-ref",
            "run:seed-7",
            "--as-of-time",
            "2026-09-14T00:01:00Z",
            "--actions",
            str(actions),
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready"
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "willfly.model-output-bundle.v0.1"


def test_fresh_process_model_output_to_signal_build_to_signal_loader(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"experiment_results": [_experiment()]}), encoding="utf-8")
    templates = tmp_path / "templates.json"
    templates.write_text(
        json.dumps({"schema_version": "willfly.prediction-template-bundle.v0.1", "predictions": [_template().to_dict()]}),
        encoding="utf-8",
    )
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({"prediction-1": "enter"}), encoding="utf-8")
    model_output = tmp_path / "model-output.json"
    signals = tmp_path / "signals.json"
    root = Path(__file__).parents[1]
    model_command = [
        sys.executable,
        "-m",
        "willfly",
        "model-output",
        "--experiment-report",
        str(report),
        "--templates",
        str(templates),
        "--output",
        str(model_output),
        "--model-id",
        "male-cns-readout",
        "--model-version",
        "candidate-v2",
        "--run-ref",
        "run:seed-7",
        "--as-of-time",
        "2026-09-14T00:01:00Z",
        "--actions",
        str(actions),
    ]
    first = subprocess.run(model_command, cwd=root, check=True, capture_output=True, text=True)
    assert json.loads(first.stdout)["output_count"] == 1
    second = subprocess.run(
        [sys.executable, "-m", "willfly", "signal-build", "--input", str(model_output), "--output", str(signals)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(second.stdout)["proposal_count"] == 1
    third = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; from willfly.cli import _load_signal_store; print(len(_load_signal_store(Path(sys.argv[1]))['proposals']))",
            str(signals),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert third.stdout.strip() == "1"
