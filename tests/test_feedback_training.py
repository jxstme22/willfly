import json
from pathlib import Path
import subprocess
import sys


def test_feedback_training_runner_waits_without_causal_labels(tmp_path: Path) -> None:
    features = tmp_path / "features.json"
    partitions = tmp_path / "partitions.json"
    features.write_text("{}", encoding="utf-8")
    partitions.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/train_malecns_feedback.py",
            "--feedback-dir",
            str(tmp_path / "feedback"),
            "--features",
            str(features),
            "--partitions",
            str(partitions),
            "--as-of-time",
            "2026-09-14T00:00:00Z",
        ],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["status"] == "waiting"
    assert report["experiment_results"] == []
    assert "insufficient_qualified_train_examples" in report["reasons"]
    assert report["signing"] is False and report["broadcast"] is False
    assert set(report["input_hashes"]) == {
        "manifest_sha256",
        "features_sha256",
        "partitions_sha256",
    }
    assert report["experiment_config"]["minimum_train_examples"] == 4
