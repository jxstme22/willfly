"""Adversarial cases discovered during Astra's implementation review."""

import json
from dataclasses import replace
import pytest

from willfly.cli import main
from willfly.domain import RawEvent
from willfly.storage.raw import RawBatchStore, BatchCorruptionError
from willfly.storage.export import export_records, verify_export
from willfly.replay.scheduler import ReplayEvent, ReplayScheduler, ReplayTick
from willfly.models.conventional import FeatureRow, LinearBaseline
from willfly.models.readout import FrozenReadout, ReadoutRow
from willfly.models.connectome.graph import Edge, build_graph, graph_hash
from willfly.models.package import save_neural_package, load_neural_package
from willfly.shadow.config import freeze_shadow_config, validate_frozen_shadow_config
from willfly.shadow.health import assess_shadow_health
from willfly.evaluation.coverage import audit_coverage
from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient, RpcLog, JsonRpcError, WrongChainError
from willfly.ingest.capture import capture_once
from willfly.ingest.backfill import backfill_range


def raw():
    return RawEvent(4663, "fixture", "test", 10, "0x" + "11" * 32, None,
                    "0x" + "22" * 32, 0, "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:01Z", {}, "test", "provisional")


def test_republish_preserves_bytes_checksum_and_acknowledgement(tmp_path):
    with RawBatchStore(tmp_path) as store:
        first = store.publish([raw()], source="rpc", partition_date="2026-01-01")
        before = first.path.read_bytes()
        store.acknowledge(first.batch_id, source="rpc", last_block_number=10, last_block_hash=raw().block_hash)
        second = store.publish([raw()], source="rpc", partition_date="2026-01-01")
        assert first.path.read_bytes() == before
        assert second.acknowledged and store.verify() == []
        first.path.write_bytes(b"corrupt")
        with pytest.raises(BatchCorruptionError):
            store.publish([raw()], source="rpc", partition_date="2026-01-01")


@pytest.mark.parametrize("source,date", [("..", "2026-01-01"), ("rpc", "2026-99-99")])
def test_raw_partition_validation(tmp_path, source, date):
    with RawBatchStore(tmp_path) as store:
        with pytest.raises(ValueError):
            store.publish([raw()], source=source, partition_date=date)


def test_export_heterogeneous_records_and_big_integers(tmp_path):
    pytest.importorskip("pyarrow")
    rows = [{"id": 1, "payload": {"a": 2**200}}, {"id": 2, "extra": True, "payload": {"b": "later"}}]
    export_records(rows, output_dir=tmp_path, dataset_name="mixed")
    assert verify_export(tmp_path, "mixed") == rows


def test_replay_orders_equivalent_timezones_by_instant():
    early = ReplayEvent("early", "2026-01-01T08:00:00+08:00", "2026-01-01T08:00:00+08:00", {})
    late = ReplayEvent("late", "2026-01-01T00:30:00Z", "2026-01-01T00:30:00Z", {})
    snapshots = ReplayScheduler([late, early]).run([ReplayTick("tick", "2026-01-01T00:15:00Z")])
    assert snapshots[0].newly_available == (early,)


def test_replay_rejects_availability_before_event():
    with pytest.raises(ValueError, match="availability"):
        ReplayEvent("bad", "2026-01-01T00:01:00Z", "2026-01-01T00:00:00Z", {})


def test_ridge_joint_fit_recovers_correlated_features_and_intercept():
    x = [(1., 2.), (2., 3.), (3., 5.), (4., 5.)]
    targets = [3 + 2*a - b for a, b in x]
    model = LinearBaseline.fit([FeatureRow(str(i), "e", row, y) for i, (row, y) in enumerate(zip(x, targets))], l2=0)
    assert model.weights == pytest.approx((2, -1))
    assert model.intercept == pytest.approx(3)
    readout = FrozenReadout.fit([ReadoutRow(row, y) for row, y in zip(x, targets)], graph_hash_value="test", l2=0)
    assert readout.predict((5., 8.)) == pytest.approx(5)


def test_ridge_rejects_nonfinite_and_singular_inputs():
    with pytest.raises(ValueError):
        LinearBaseline.fit([FeatureRow("a", "e", (float("nan"),), 1)])
    with pytest.raises(ValueError, match="singular"):
        FrozenReadout.fit([ReadoutRow((0.,), 1)], graph_hash_value="test", l2=0)


def test_neural_package_requires_complete_hash_manifest_and_matching_graph(tmp_path):
    graph = build_graph([Edge("a", "b", 1)])
    readout = FrozenReadout.fit([ReadoutRow((1., 0.), 1), ReadoutRow((0., 1.), 2)], graph_hash_value=graph_hash(graph))
    save_neural_package(tmp_path, graph=graph, readout=readout, reservoir_config={}, model_card={})
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["files"] = {}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hashes"):
        load_neural_package(tmp_path)
    with pytest.raises(ValueError, match="supplied graph"):
        save_neural_package(tmp_path, graph=build_graph([Edge("a", "b", 2)]), readout=readout, reservoir_config={}, model_card={})


def test_shadow_hash_tampering_rejected_and_frozen_config_does_not_claim_runtime(tmp_path, capsys):
    path = tmp_path / "shadow.json"
    path.write_text(json.dumps({"start_time": None, "config_hash": None, "lp_enabled": False}))
    frozen = freeze_shadow_config(path, start_time="2026-01-01T00:00:00Z")
    validate_frozen_shadow_config(frozen.values)
    assert main(["shadow", "--config", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "shadow_runtime_not_integrated"
    changed = dict(frozen.values, capital_scenario_usd=100000)
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_frozen_shadow_config(changed)


def test_future_shadow_observation_cannot_be_healthy():
    with pytest.raises(ValueError, match="future"):
        assess_shadow_health(quality_state="healthy", contradictory=False,
                             now="2026-01-01T00:00:00Z", latest_arrival="2026-01-01T00:01:00Z")


def test_empty_reference_does_not_pass_coverage():
    assert audit_coverage([], [], provider_independent=True).state != "pass"


def test_backfill_checks_chain_before_reading_logs():
    calls = []
    def transport(method, params):
        calls.append(method)
        return {"result": "0x1"}
    with pytest.raises(WrongChainError):
        backfill_range(ReadOnlyRpcClient("https://fixture.invalid", transport=transport),
                       address="0x" + "11" * 20, start_block=1, target_block=2)
    assert calls == ["eth_chainId"]


def test_capture_bounds_range_and_resolves_missing_log_time():
    event = raw()
    queried_ranges = []
    def transport(method, params):
        if method == "eth_chainId": return {"result": "0x1237"}
        if method == "eth_blockNumber": return {"result": hex(9000)}
        if method == "eth_getLogs":
            queried_ranges.append(params[0])
            return {"result": [{"blockNumber": hex(10), "blockHash": event.block_hash,
                                "transactionHash": event.transaction_hash, "logIndex": "0x0",
                                "blockTimestamp": "0x0"}]}
        if method == "eth_getBlockByNumber":
            return {"result": {"hash": event.block_hash, "timestamp": hex(1700000000)}}
        raise AssertionError(method)
    client = ReadOnlyRpcClient("https://fixture.invalid", transport=transport)
    result = capture_once(client, addresses=["0x" + "33" * 20], from_block=10, run_id="test",
                          clock=lambda: "2026-01-01T00:00:01Z")
    assert result.to_block == 2009
    assert result.events[0].event_time.startswith("2023-")
    assert result.events[0].event_time != result.events[0].received_time


def test_log_header_hash_mismatch_is_not_accepted():
    event = raw()
    log = RpcLog(10, event.block_hash, event.transaction_hash, 0, {}, None)
    client = ReadOnlyRpcClient("https://fixture.invalid", transport=lambda *_: {"result": {"hash": "different", "timestamp": "0x1"}})
    with pytest.raises(JsonRpcError, match="mismatched"):
        client.resolve_log_time(log, {})


def test_future_quotes_and_wrong_asset_routes_cannot_generate_labels():
    from willfly.replay.execution import PoolQuote, simulate_fill, simulate_follower_round_trip
    quote = PoolQuote("p", "ETH", "TOKEN", 1000, 2000, 30, "2026-01-02T00:00:00Z")
    assert simulate_fill(quote, input_atomic=10, submitted_at="2026-01-01T00:00:00Z").status == "missing_state"
    with pytest.raises(ValueError, match="asset pair"):
        simulate_follower_round_trip(quote, quote, quote_input_atomic=10, signal_received_at="2026-01-01T00:00:00Z")


def test_unverified_scalar_comparisons_cannot_pass_neural_gate():
    from willfly.evaluation.neural import ModelComparison, review_neural_progression
    report = review_neural_progression([ModelComparison("fly", i, 1, .1, "g") for i in range(5)],
                                       [], positive_windows=4, uncertainty_interval_positive=True)
    assert report.state == "inconclusive"


@pytest.mark.parametrize("claim", [{"claim_type": "profit_label", "evidence": "source"},
                                  {"claim_type": "risk", "evidence": "fabricated"}])
def test_llm_cannot_accept_unsupported_type_or_invented_span(claim):
    from willfly.features.llm import bounded_enrich, LLMBudget
    result = bounded_enrich("source text", call=lambda _: json.dumps([claim]),
                            budget=LLMBudget(1, 100), model_version="test", prompt_version="test")
    assert result.fallback_used
