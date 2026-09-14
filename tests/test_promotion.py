import json

import pytest

from willfly.cli import main
from willfly.evaluation.promotion import ModelRegistry, PredictionPoint, evaluate_candidate


def _points(candidate_error: float = 1.0):
    points = []
    for window in ("forward-1", "forward-2"):
        for index in range(2):
            points.append(PredictionPoint(f"{window}-{index}-c", "candidate-v2", "spot", window, "forward", f"2026-09-14T00:0{index}:00Z", 10 + candidate_error, 10, (f"market:{window}:{index}",)))
            points.append(PredictionPoint(f"{window}-{index}-a", "active-v1", "spot", window, "forward", f"2026-09-14T00:0{index}:00Z", 14, 10, (f"market:{window}:{index}",)))
    for index in range(2):
        points.append(PredictionPoint(f"final-{index}-c", "candidate-v2", "spot", "final", "final_test", f"2026-09-14T01:0{index}:00Z", 10 + candidate_error, 10, (f"final:{index}",)))
        points.append(PredictionPoint(f"final-{index}-a", "active-v1", "spot", "final", "final_test", f"2026-09-14T01:0{index}:00Z", 14, 10, (f"final:{index}",)))
    return tuple(points)


def test_candidate_requires_paired_forward_and_untouched_final_test() -> None:
    report = evaluate_candidate(
        _points(),
        candidate_version="candidate-v2",
        active_version="active-v1",
        evaluated_at="2026-09-14T02:00:00Z",
        dataset_hash="dataset-1",
    )
    assert report.decision == "qualified"
    assert len(report.forward_scores) == 2
    assert len(report.final_test_scores) == 1
    assert len(report.active_forward_scores) == 2
    assert len(report.active_final_test_scores) == 1
    worse = evaluate_candidate(
        _points(candidate_error=6.0),
        candidate_version="candidate-v2",
        active_version="active-v1",
        evaluated_at="2026-09-14T02:00:00Z",
        dataset_hash="dataset-1",
    )
    assert worse.decision == "inconclusive"
    assert "candidate_forward_gate_not_met" in worse.reasons


def test_candidate_rejects_mismatched_evidence_grid() -> None:
    points = list(_points())
    points[0] = PredictionPoint(
        points[0].prediction_id,
        points[0].model_version,
        points[0].market,
        points[0].window_id,
        points[0].split,
        points[0].observed_at,
        points[0].predicted_bps,
        points[0].target_bps,
        ("different-source",),
    )
    report = evaluate_candidate(
        points,
        candidate_version="candidate-v2",
        active_version="active-v1",
        evaluated_at="2026-09-14T02:00:00Z",
        dataset_hash="dataset-1",
    )
    assert report.decision == "inconclusive"
    assert "candidate_forward_evidence_grid_mismatch" in report.reasons


def test_registry_consumes_final_test_and_records_promotion_rollback(tmp_path) -> None:
    report = evaluate_candidate(
        _points(),
        candidate_version="candidate-v2",
        active_version="active-v1",
        evaluated_at="2026-09-14T02:00:00Z",
        dataset_hash="dataset-1",
    )
    path = tmp_path / "models.sqlite3"
    with ModelRegistry(path, initial_active_version="active-v1") as registry:
        assert registry.promote_and_record(report) == "candidate-v2"
        assert registry.active_version == "candidate-v2"
        with pytest.raises(ValueError, match="final test"):
            registry.record_evaluation(report)
        assert registry.rollback("active-v1", reason="revert fixture", evaluated_at="2026-09-14T03:00:00Z") == "active-v1"
    with ModelRegistry(path, initial_active_version="ignored") as restarted:
        assert restarted.active_version == "active-v1"
        assert any(item["kind"] == "promotion" for item in restarted.history())


def test_inconclusive_report_cannot_promote(tmp_path) -> None:
    report = evaluate_candidate(
        _points(candidate_error=6.0),
        candidate_version="candidate-v2",
        active_version="active-v1",
        evaluated_at="2026-09-14T02:00:00Z",
        dataset_hash="dataset-1",
    )
    with ModelRegistry(tmp_path / "models.sqlite3", initial_active_version="active-v1") as registry:
        with pytest.raises(ValueError, match="qualified"):
            registry.promote(report)


def test_evaluation_round_trip_and_cli_promote_then_rollback(tmp_path, capsys) -> None:
    report = evaluate_candidate(
        _points(),
        candidate_version="candidate-v2",
        active_version="active-v1",
        evaluated_at="2026-09-14T02:00:00Z",
        dataset_hash="dataset-1",
    )
    evaluation_path = tmp_path / "evaluation.json"
    evaluation_path.write_text(json.dumps(report.to_dict()), encoding="utf-8")
    registry = tmp_path / "models.sqlite3"
    assert main(
        [
            "model-promote",
            "--evaluation",
            str(evaluation_path),
            "--registry",
            str(registry),
            "--initial-active-version",
            "active-v1",
        ]
    ) == 0
    promoted = json.loads(capsys.readouterr().out)
    assert promoted["status"] == "promoted"
    assert promoted["state"]["active_version"] == "candidate-v2"
    assert promoted["state"]["history"][-1]["kind"] == "promotion"

    assert main(
        [
            "model-rollback",
            "--registry",
            str(registry),
            "--initial-active-version",
            "active-v1",
            "--version",
            "active-v1",
            "--reason",
            "controlled rollback fixture",
            "--evaluated-at",
            "2026-09-14T03:00:00Z",
        ]
    ) == 0
    rolled_back = json.loads(capsys.readouterr().out)
    assert rolled_back["status"] == "rolled_back"
    assert rolled_back["state"]["active_version"] == "active-v1"
    assert rolled_back["state"]["history"][-1]["kind"] == "rollback"
