from dataclasses import replace

from willfly.adapters.protocols.v4 import INITIALIZE_TOPIC, SWAP_TOPIC
from willfly.domain import RawEvent
from willfly.features.market_feedback import build_market_feedback_corpus
from willfly.storage.feedback import FeedbackStore
from willfly.storage.raw import AncestryAnchor, BlockHeader, RawBatchStore, anchor_evidence_record


MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
TOKEN = "0x1111111111111111111111111111111111111111"
POOL_ID = "0x" + "11" * 32
ZERO = "0x" + "0" * 40


def _word(value: int) -> str:
    if value < 0:
        value = (1 << 256) + value
    return f"{value:064x}"


def _address_word(address: str) -> str:
    return address[2:].rjust(64, "0")


def _event(topic: str, topics: list[str], words: list[str], *, block: int, index: int, second: int) -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": "fixture.rpc",
            "source_schema_version": "rpc-log.v0.1",
            "block_number": block,
            "block_hash": "0x" + f"{block:064x}",
            "parent_hash": "0x" + f"{max(0, block - 1):064x}",
            "transaction_hash": "0x" + f"{block + 100:064x}",
            "log_index": index,
            "event_time": f"2026-01-01T00:{second // 60:02d}:{second % 60:02d}Z",
            "received_time": f"2026-01-01T00:{(second + 1) // 60:02d}:{(second + 1) % 60:02d}Z",
            "payload": {
                "address": MANAGER,
                "topics": [topic, *topics],
                "data": "0x" + "".join(words),
            },
            "ingestion_run": "market-feedback-test",
            "canonical_status": "canonical",
        }
    )


def _initialize() -> RawEvent:
    return _event(
        INITIALIZE_TOPIC,
        [POOL_ID, _address_word(ZERO), _address_word(TOKEN)],
        [_word(3000), _word(10), _address_word(ZERO), _word(1 << 96), _word(0)],
        block=100,
        index=0,
        second=0,
    )


def _swap(second: int, block: int, sqrt_price: int) -> RawEvent:
    return _event(
        SWAP_TOPIC,
        [POOL_ID, _address_word(MANAGER)],
        [_word(-1000), _word(2500), _word(sqrt_price), _word(123456), _word(-5), _word(3000)],
        block=block,
        index=0,
        second=second,
    )


def test_market_feedback_uses_canonical_v4_swaps_and_delayed_forward_labels() -> None:
    events = [
        _initialize(),
        _swap(1, 101, 1 << 96),
        _swap(61, 161, 2 << 96),
        _swap(301, 401, 1 << 96),
        _swap(901, 1001, 4 << 96),
    ]
    corpus = build_market_feedback_corpus(
        events,
        as_of_time="2026-01-01T00:16:40Z",
        source="fixture-source",
        max_label_delay_seconds=0,
    )

    assert len(corpus.points) == 4
    assert len(corpus.predictions) == 12
    first_point_id = corpus.points[0].point_id
    first = [prediction for prediction in corpus.predictions if prediction.prediction_id.startswith(first_point_id + "|")]
    outcomes = {outcome.prediction_id: outcome for outcome in corpus.outcomes}
    assert all(outcomes[prediction.prediction_id].status == "observed" for prediction in first)
    assert all(prediction.prediction_id not in outcomes[prediction.prediction_id].source_refs for prediction in first)
    assert corpus.predictions[0].portfolio_context.wallet_scope == "none"
    assert corpus.to_bundle()["personal_trade_count"] == 0
    assert set(corpus.partitions_by_prediction.values()) == {"train", "validation", "test"}


def test_market_feedback_excludes_noncanonical_and_future_arrivals() -> None:
    noncanonical = replace(_swap(61, 161, 2 << 96), canonical_status="provisional")
    future = replace(_swap(301, 401, 1 << 96), received_time="2026-01-01T00:20:00Z")
    corpus = build_market_feedback_corpus(
        [_initialize(), _swap(1, 101, 1 << 96), noncanonical, future],
        as_of_time="2026-01-01T00:10:00Z",
        source="fixture-source",
    )

    assert len(corpus.points) == 1
    reasons = {row["reason"] for row in corpus.excluded}
    assert "noncanonical_raw_evidence" in reasons
    assert "event_or_arrival_after_cutoff" in reasons


def test_market_feedback_preserves_censored_windows_without_numeric_targets() -> None:
    corpus = build_market_feedback_corpus(
        [_initialize(), _swap(1, 101, 1 << 96)],
        as_of_time="2026-01-01T00:02:00Z",
        source="fixture-source",
        max_label_delay_seconds=0,
    )
    outcomes = {outcome_id: outcome for outcome_id, outcome in ((item.outcome_id, item) for item in corpus.outcomes)}
    assert outcomes["outcome:" + corpus.predictions[0].prediction_id].status == "censored"
    assert outcomes["outcome:" + corpus.predictions[0].prediction_id].net_return_bps is None


def test_market_feedback_revises_unresolved_label_when_later_endpoint_arrives(tmp_path) -> None:
    early_events = [_initialize(), _swap(1, 101, 1 << 96)]
    late_events = [*early_events, _swap(61, 161, 2 << 96)]
    early = build_market_feedback_corpus(
        early_events,
        as_of_time="2026-01-01T00:00:30Z",
        source="fixture-source",
        max_label_delay_seconds=0,
    )
    late = build_market_feedback_corpus(
        late_events,
        as_of_time="2026-01-01T00:02:00Z",
        source="fixture-source",
        max_label_delay_seconds=0,
    )
    first_prediction_id = next(
        prediction.prediction_id
        for prediction in early.predictions
        if prediction.horizon_seconds == 60
    )
    early_outcome = next(outcome for outcome in early.outcomes if outcome.prediction_id == first_prediction_id)
    late_outcome = next(outcome for outcome in late.outcomes if outcome.prediction_id == first_prediction_id)
    assert early_outcome.outcome_id == late_outcome.outcome_id
    assert early_outcome.status == "unresolved"
    assert late_outcome.status == "observed"

    with FeedbackStore(tmp_path) as store:
        assert store.record_predictions(early.predictions).inserted == len(early.predictions)
        assert store.record_outcomes(early.outcomes).inserted == len(early.outcomes)
        assert store.mature(as_of_time="2026-01-01T00:00:30Z")[0].state == "waiting"
        prediction_write = store.record_predictions(late.predictions)
        assert prediction_write.duplicates == 3
        assert prediction_write.inserted == 3
        assert store.record_outcomes(late.outcomes).revised == 1
        assert len(store.list_outcome_revisions(early_outcome.outcome_id)) == 1
        assert store.mature(as_of_time="2026-01-01T00:02:00Z")[0].state == "ready"
        dataset = store.dataset(as_of_time="2026-01-01T00:02:00Z")
        assert [example.outcome_id for example in dataset.eligible_examples] == [early_outcome.outcome_id]


def test_raw_store_exposes_only_resolved_canonical_events(tmp_path) -> None:
    event = _swap(1, 101, 1 << 96)
    # A one-block genesis window gives the canonicalizer a real trusted
    # boundary without reaching outside the test's read-only evidence.
    genesis_hash = "0x" + "aa" * 32
    event = replace(event, block_number=0, block_hash=genesis_hash, parent_hash=None)
    source = "fixture-source"
    anchor = AncestryAnchor(
        chain_id=4663,
        height=0,
        block_hash=genesis_hash,
        qualification="genesis",
        evidence=(anchor_evidence_record(
            "genesis_header",
            chain_id=4663,
            config_identity="fixture-config",
            height=0,
            block_hash=genesis_hash,
        ),),
        config_identity="fixture-config",
        source=source,
        recorded_at="2026-01-01T00:00:00Z",
    )
    with RawBatchStore(tmp_path / "store") as store:
        store.publish([event], source=source, partition_date="2026-01-01")
        store.persist_headers([BlockHeader(0, genesis_hash, None, parent_known=True)])
        store.save_ancestry_anchor(anchor)
        store.rebuild_canonical_projection(
            source=source,
            tip_hash=genesis_hash,
            chain_id=4663,
            config_identity="fixture-config",
        )
        canonical = store.canonical_events_for_source(source)
    assert len(canonical) == 1
    assert canonical[0].canonical_status == "canonical"
