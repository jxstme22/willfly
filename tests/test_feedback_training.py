import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.train_malecns_feedback import train_feedback
from willfly.domain import Confidence, InstrumentIdentity, OutcomeRecord, PortfolioContext, PredictionRecord
from willfly.storage.feedback import FeedbackStore


TOKEN = InstrumentIdentity(4663, "token", "0x" + "2" * 40, "native:ETH")
CONTEXT = PortfolioContext("2026-01-01T00:00:00Z", "flat", "public_only", "healthy", "100", (), ("obs:1",))


def _prediction(prediction_id: str) -> PredictionRecord:
    return PredictionRecord(
        prediction_id,
        "signal-contract-v0.1.0",
        "spot_entry_net_return",
        300,
        TOKEN,
        "2026-01-01T00:00:00Z",
        "2025-12-31T23:59:59Z",
        "2026-01-01T00:10:00Z",
        "male-cns-readout",
        "candidate-v1",
        100,
        25,
        Confidence("uncalibrated_score", score=3),
        CONTEXT,
        (f"feature:{prediction_id}",),
    )


def _outcome(outcome_id: str, prediction_id: str) -> OutcomeRecord:
    return OutcomeRecord(
        outcome_id,
        prediction_id,
        "spot_entry_net_return",
        "observed_market",
        "observed",
        "2026-01-01T00:05:00Z",
        "2026-01-01T00:05:01Z",
        80,
        (f"market:{outcome_id}",),
    )

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
    assert report["training_budget"]["max_training_examples"] == 100_000


def test_feedback_training_runner_can_consume_market_corpus_maps(tmp_path: Path) -> None:
    corpus = tmp_path / "market-feedback.json"
    corpus.write_text(
        json.dumps(
            {
                "schema_version": "willfly.market-feedback-bundle.v0.1",
                "source": "fixture-source",
                "predictions": [],
                "outcomes": [],
                "features_by_prediction": {},
                "partitions_by_prediction": {},
            }
        ),
        encoding="utf-8",
    )
    report = train_feedback(
        Path("configs/connectome/male-cns-v1.0.json"),
        Path("data/connectome/male-cns-v1.0"),
        tmp_path / "feedback",
        None,
        None,
        as_of_time="2026-01-01T00:00:00Z",
        max_edges=20_000,
        partition_index=1,
        partition_count=4,
        seeds=(7, 17, 27),
        corpus_path=corpus,
    )
    assert report["status"] == "waiting"
    assert report["corpus"]["personal_trade_count"] == 0
    assert "corpus_sha256" in report["input_hashes"]


def test_feedback_training_runner_stops_before_graph_load_at_example_budget(tmp_path: Path) -> None:
    feedback_dir = tmp_path / "feedback"
    predictions = [_prediction("p1"), _prediction("p2")]
    outcomes = [_outcome("o1", "p1"), _outcome("o2", "p2")]
    with FeedbackStore(feedback_dir) as store:
        store.record_predictions(predictions)
        store.record_outcomes(outcomes)
    features = tmp_path / "features.json"
    features.write_text(json.dumps({"p1": {"1": 0.1}, "p2": {"1": 0.2}}), encoding="utf-8")
    partitions = tmp_path / "partitions.json"
    partitions.write_text(json.dumps({"p1": "train", "p2": "test"}), encoding="utf-8")
    report = train_feedback(
        Path("configs/connectome/male-cns-v1.0.json"),
        Path("data/connectome/male-cns-v1.0"),
        feedback_dir,
        features,
        partitions,
        as_of_time="2026-01-01T00:06:00Z",
        max_edges=20_000,
        partition_index=1,
        partition_count=4,
        seeds=(7,),
        max_training_examples=1,
    )
    assert report["status"] == "waiting"
    assert report["reasons"] == ["training_example_budget_exceeded"]
    assert report["experiment_results"] == []


def test_feedback_training_runner_rejects_unknown_partition_value(tmp_path: Path) -> None:
    features = tmp_path / "features.json"
    partitions = tmp_path / "partitions.json"
    features.write_text("{}", encoding="utf-8")
    partitions.write_text(json.dumps({"unused": "holdout"}), encoding="utf-8")
    with pytest.raises(ValueError, match="train, validation or test"):
        train_feedback(
            Path("configs/connectome/male-cns-v1.0.json"),
            Path("data/connectome/male-cns-v1.0"),
            tmp_path / "feedback",
            features,
            partitions,
            as_of_time="2026-01-01T00:00:00Z",
            max_edges=20_000,
            partition_index=1,
            partition_count=4,
            seeds=(7,),
        )
