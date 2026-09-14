import json
from dataclasses import replace

from willfly.cli import _load_signal_store, main
from willfly.domain import Confidence, InstrumentIdentity, PortfolioContext, PredictionRecord
from willfly.features.signal_generation import build_research_signals


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


def test_model_outputs_become_uncalibrated_research_prediction_and_manual_proposal():
    built = build_research_signals(
        [_template()],
        [("feedback:prediction-1", 123.4), ("feedback:missing", 5.0)],
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:candidate-v2",
        actions_by_prediction={"prediction-1": "enter"},
    )
    assert len(built.predictions) == 1
    assert built.predictions[0].expected_value_bps == 123
    assert built.predictions[0].confidence.kind == "unavailable"
    assert len(built.proposals) == 1
    assert built.proposals[0].proposal_state == "research_only"
    assert {item["reason"] for item in built.excluded} == {"prediction_template_missing"}


def test_missing_action_mapping_keeps_prediction_but_does_not_create_proposal():
    built = build_research_signals(
        [_template()],
        [("prediction-1", 50.0)],
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:candidate-v2",
    )
    assert len(built.predictions) == 1
    assert built.proposals == ()
    assert built.excluded == ({"sample_id": "prediction-1", "reason": "proposal_action_mapping_missing"},)


def test_invalid_action_is_excluded_by_frozen_signal_contract():
    built = build_research_signals(
        [_template()],
        [("prediction-1", 50.0)],
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:candidate-v2",
        actions_by_prediction={"prediction-1": "exit"},
        exit_kinds_by_prediction={"prediction-1": "sell_token"},
    )
    assert len(built.predictions) == 1
    assert built.proposals == ()
    assert built.excluded == ({"sample_id": "prediction-1", "reason": "proposal_contract_invalid"},)


def test_proposal_ttl_is_capped_for_long_horizon_prediction_templates():
    built = build_research_signals(
        [replace(_template(), expires_at="2026-09-14T00:05:00Z")],
        [("prediction-1", 50.0)],
        model_id="male-cns-readout",
        model_version="candidate-v2",
        run_ref="run:candidate-v2",
        actions_by_prediction={"prediction-1": "enter"},
    )
    assert len(built.proposals) == 1
    assert built.proposals[0].expires_at == "2026-09-14T00:00:15+00:00"


def test_signal_build_cli_writes_bundle_consumable_by_server_loader(tmp_path, capsys):
    input_path = tmp_path / "model-output.json"
    output_path = tmp_path / "signals.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "willfly.model-output-bundle.v0.1",
                "as_of_time": "2026-01-01T00:00:10Z",
                "model_id": "male-cns-readout",
                "model_version": "candidate-v2",
                "run_ref": "run:candidate-v2",
                "templates": [_template().to_dict()],
                "outputs": [{"sample_id": "feedback:prediction-1", "predicted_bps": 123.4}],
                "actions_by_prediction": {"prediction-1": "enter"},
                "market_readiness": {"spot": "research_only", "lp": "research_only"},
                "training_state": {"status": "completed", "candidate_version": "candidate-v2"},
            }
        ),
        encoding="utf-8",
    )
    assert main(["signal-build", "--input", str(input_path), "--output", str(output_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready"
    assert result["proposal_count"] == 1
    bundle = _load_signal_store(output_path)
    assert bundle["predictions"][0].model_version == "candidate-v2"
    assert bundle["proposals"][0].proposal_state == "research_only"
