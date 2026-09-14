import json

import pytest

from willfly.models.connectome.graph import Edge, build_graph
from willfly.features.feedback import FeedbackDataset, FeedbackExample
from willfly.models.laboratory import (
    ExperimentConfig,
    TrainingSample,
    build_training_samples_from_feedback,
    run_connectome_experiment,
)


def _samples() -> tuple[TrainingSample, ...]:
    return tuple(
        TrainingSample(
            f"sample-{index}",
            f"episode-{index}",
            f"2026-09-14T00:00:{index:02d}Z",
            {"a": 1.0 if index % 2 else 0.5, "b": 0.25},
            index * 10,
            "train" if index < 4 else "test",
            (f"market:{index}",),
        )
        for index in range(6)
    )


def test_fixed_connectome_runner_trains_controls_and_resumes_checkpoint(tmp_path) -> None:
    graph = build_graph([Edge("a", "b", 0.5), Edge("b", "a", -0.25)])
    config = ExperimentConfig("lab-1", minimum_train_examples=4)
    checkpoint = tmp_path / "checkpoint.json"
    first = run_connectome_experiment(graph, _samples(), config=config, checkpoint_path=checkpoint)
    resumed = run_connectome_experiment(graph, _samples(), config=config, checkpoint_path=checkpoint)
    assert first.status == "completed"
    assert first.graph_hash == resumed.graph_hash
    assert [metric.model_name for metric in first.models] == ["fly", "shuffled_wiring", "random_weights", "no_state", "ordinary"]
    assert first.models[0].graph_hash == first.graph_hash
    assert first.models[0].heldout_count == 2
    assert first.models[0].predictions == resumed.models[0].predictions
    assert json.loads(checkpoint.read_text())['schema_version'] == 'connectome-checkpoint.v0.1'


def test_connectome_runner_waits_without_enough_qualified_or_heldout_examples(tmp_path) -> None:
    graph = build_graph([Edge("a", "b", 0.5)])
    only_train = tuple(
        TrainingSample(f"sample-{i}", f"e-{i}", f"2026-09-14T00:00:0{i}Z", {"a": 1.0}, i, "train", (f"source:{i}",))
        for i in range(2)
    )
    result = run_connectome_experiment(graph, only_train, config=ExperimentConfig("waiting", minimum_train_examples=4))
    assert result.status == "waiting"
    assert "insufficient_qualified_train_examples" in result.reasons
    assert "no_heldout_examples" in result.reasons


def test_checkpoint_identity_cannot_cross_graph_or_dataset(tmp_path) -> None:
    graph = build_graph([Edge("a", "b", 0.5)])
    checkpoint = tmp_path / "checkpoint.json"
    config = ExperimentConfig("lab-1", minimum_train_examples=4)
    run_connectome_experiment(graph, _samples(), config=config, checkpoint_path=checkpoint)
    changed_graph = build_graph([Edge("a", "b", 0.25)])
    with pytest.raises(ValueError, match="checkpoint identity"):
        run_connectome_experiment(changed_graph, _samples(), config=config, checkpoint_path=checkpoint)


def test_feedback_adapter_requires_features_and_explicit_partition_without_leakage() -> None:
    dataset = FeedbackDataset(
        "2026-09-14T02:00:00Z",
        (
            FeedbackExample(
                "p1",
                "spot_entry_net_return",
                "token-1",
                "token",
                "2026-09-14T00:00:00Z",
                "2026-09-14T01:00:00Z",
                "market",
                "observed",
                25,
                True,
                (),
                ("prediction:p1", "outcome:o1"),
            ),
        ),
        (),
        (),
        ("feedback:test",),
    )
    built = build_training_samples_from_feedback(
        dataset,
        {"p1": {"node-a": 0.5}},
        partitions_by_prediction={"p1": "test"},
    )
    assert len(built.samples) == 1
    assert built.samples[0].partition == "test"
    assert built.samples[0].target_bps == 25
    assert built.samples[0].observed_at == "2026-09-14T00:00:00Z"

    missing = build_training_samples_from_feedback(dataset, {}, partitions_by_prediction={})
    assert missing.samples == ()
    assert missing.excluded == ({"prediction_id": "p1", "reason": "feature_inputs_missing"},)
