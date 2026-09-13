from dataclasses import replace

import pytest

from willfly.domain import OutcomeRecord
from willfly.domain.signal_contracts import Confidence, InstrumentIdentity, PortfolioContext, PredictionRecord
from willfly.features.feedback import build_feedback_dataset
from willfly.storage.feedback import FeedbackStore


TOKEN = InstrumentIdentity(4663, "token", "0x" + "1" * 40, "native:ETH")
CONTEXT = PortfolioContext(
    "2026-09-14T00:00:00Z", "flat", "public_only", "healthy", "100000", (), ("observation:1",)
)


def _prediction(prediction_id: str, created: str = "2026-09-14T00:00:00Z") -> PredictionRecord:
    return PredictionRecord(
        prediction_id,
        "signal-contract-v0.1.0",
        "spot_entry_net_return",
        300,
        TOKEN,
        created,
        "2026-09-13T23:59:59Z",
        "2026-09-14T00:00:15Z",
        "male-cns-readout",
        "candidate-1",
        125,
        250,
        Confidence("uncalibrated_score", score=7),
        CONTEXT,
        (f"feature:{prediction_id}",),
    )


def _outcome(
    outcome_id: str,
    prediction_id: str,
    *,
    status: str = "observed",
    kind: str = "observed_market",
    available: str | None = "2026-09-14T00:05:01Z",
    value: int | None = 80,
    target: str = "spot_entry_net_return",
    refs: tuple[str, ...] = ("market:price:1",),
) -> OutcomeRecord:
    return OutcomeRecord(
        outcome_id,
        prediction_id,
        target,
        kind,
        status,
        "2026-09-14T00:05:00Z",
        available,
        value,
        refs,
    )


def test_feedback_join_is_causal_and_retains_market_counterfactual_and_unresolved() -> None:
    prediction = _prediction("p1")
    unresolved = _outcome("o1", "p1", status="unresolved", kind="simulated_counterfactual", value=None)
    dataset = build_feedback_dataset([prediction], [unresolved], as_of_time="2026-09-14T00:06:00Z")
    assert len(dataset.examples) == 1
    assert dataset.examples[0].eligible_for_training is False
    assert "outcome_unresolved_or_invalidated" in dataset.examples[0].reason_flags
    assert dataset.eligible_examples == ()


def test_feedback_rejects_future_and_self_label_evidence() -> None:
    prediction = _prediction("p1")
    future = _outcome("future", "p1", available="2026-09-14T00:07:00Z")
    self_label = _outcome("self", "p1", refs=("p1", "market:price:2"))
    dataset = build_feedback_dataset([prediction], [future, self_label], as_of_time="2026-09-14T00:06:00Z")
    assert len(dataset.examples) == 1
    assert dataset.examples[0].eligible_for_training is False
    assert "prediction_self_label_reference" in dataset.examples[0].reason_flags
    assert "outcome_label_not_yet_available" in dataset.missingness


def test_feedback_store_matures_labels_and_revises_fork_outcomes(tmp_path) -> None:
    prediction = _prediction("p1")
    outcome = _outcome("o1", "p1")
    with FeedbackStore(tmp_path) as store:
        assert store.record_predictions([prediction, prediction]).duplicates == 1
        assert store.list_queue()[0].state == "waiting"
        assert store.mature(as_of_time="2026-09-14T00:02:00Z")[0].state == "waiting"
        assert store.record_outcomes([outcome]).inserted == 1
        assert store.mature(as_of_time="2026-09-14T00:06:00Z")[0].state == "ready"
        changed = replace(outcome, status="invalidated", net_return_bps=None, source_refs=("fork:replacement",))
        assert store.record_outcomes([changed]).revised == 1
        assert len(store.list_outcome_revisions("o1")) == 1
        assert store.mature(as_of_time="2026-09-14T00:06:00Z")[0].state == "unresolved"
        assert store.dataset(as_of_time="2026-09-14T00:06:00Z").eligible_examples == ()
    with FeedbackStore(tmp_path) as restarted:
        assert restarted.list_predictions()[0].prediction_id == "p1"
        assert restarted.list_outcomes()[0].status == "invalidated"


def test_prediction_payload_is_immutable(tmp_path) -> None:
    with FeedbackStore(tmp_path) as store:
        store.record_predictions([_prediction("p1")])
        with pytest.raises(ValueError, match="immutable"):
            store.record_predictions([replace(_prediction("p1"), model_version="different")])
