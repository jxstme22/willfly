import pytest

from willfly.evaluation.neural import AblationResult, review_neural_progression, run_matched_comparisons
from willfly.models.connectome.graph import Edge, SparseGraph, build_graph, graph_hash
from willfly.models.connectome.ingest import (
    ConnectomeManifest,
    deterministic_row_range,
    load_connectome_graph,
    sha256_file,
    validate_connectome_records,
)
from willfly.models.readout import FrozenReadout, ReadoutRow
from willfly.models.ridge import fit_ridge
from willfly.models.reservoir import SparseReservoir
from willfly.models.package import load_neural_package, save_neural_package


def test_sparse_graph_reservoir_is_stable_and_resets_per_episode():
    graph = build_graph([Edge("a", "b", 0.5), Edge("b", "a", -0.25)])
    reservoir = SparseReservoir(graph, decay=0.8, input_scale=1.0)
    first = reservoir.run_episode("episode-a", [{"a": 1.0}] * 4)
    second = reservoir.run_episode("episode-b", [{"a": 1.0}] * 4)
    assert graph_hash(graph) == reservoir.graph_hash
    assert [state.values for state in first] == [state.values for state in second]
    assert all(abs(value) <= 1 for state in first for value in state.values)
    assert graph.shuffled_control(7).statistics == graph.statistics
    random_control = graph.random_weight_control(7)
    assert random_control.statistics == graph.statistics
    assert graph_hash(random_control) != graph_hash(graph)


def test_graph_orientation_changes_reservoir_dynamics_and_nonfinite_weights_are_rejected():
    forward = build_graph([Edge("a", "b", 1.0), Edge("b", "c", 1.0)], orientation="source_to_target")
    reverse = build_graph([Edge("a", "b", 1.0), Edge("b", "c", 1.0)], orientation="target_to_source")
    forward_state = SparseReservoir(forward, decay=0.0).run_episode("episode", [{"a": 1.0}, {}, {}])
    reverse_state = SparseReservoir(reverse, decay=0.0).run_episode("episode", [{"a": 1.0}, {}, {}])
    assert forward_state != reverse_state
    with pytest.raises(ValueError, match="invalid"):
        Edge("a", "b", float("nan"))


def test_large_graph_membership_validation_uses_node_identity_not_tuple_scans():
    nodes = tuple(str(index) for index in range(2_000))
    graph = SparseGraph(
        nodes,
        (Edge("0", "1", 1.0), Edge("1998", "1999", 1.0)),
        "source_to_target",
    )
    assert graph.nodes == nodes


def test_connectome_ids_remain_text_and_unverified_manifest_blocks_ingest():
    pending = ConnectomeManifest(None, None, None, None, "none", "pending_verification")
    with pytest.raises(ValueError, match="verified"):
        validate_connectome_records([{"source": "1", "target": "2", "weight": 1}], pending)
    verified = ConnectomeManifest("release", "https://source", "https://license", "a" * 64, "curated", "verified")
    records = validate_connectome_records([{"source": "001", "target": "2", "weight": 1, "included": False}], verified)
    assert records[0]["source"] == "001"
    assert records[0]["included"] is False
    with pytest.raises(ValueError, match="numeric"):
        validate_connectome_records([{"source": "1", "target": "2", "weight": float("nan")}], verified)


def test_verified_feather_loader_preserves_direction_and_reports_subset(tmp_path):
    pa = pytest.importorskip("pyarrow")
    feather = pytest.importorskip("pyarrow.feather")
    path = tmp_path / "edges.feather"
    feather.write_feather(
        pa.table({"body_pre": [101, 102, 103], "body_post": [102, 103, 101], "weight": [4, 9, 16]}),
        path,
    )
    manifest = ConnectomeManifest(
        "male-cns:v1.0", "https://source", "https://license", sha256_file(path),
        "minconf-0.5", "verified", "male-cns:v1.0", "presynaptic_to_postsynaptic",
        ("body_pre", "body_post", "weight"), path.stat().st_size, 3,
    )
    graph, report = load_connectome_graph(path, manifest, max_edges=2)
    assert graph.orientation == "source_to_target"
    assert [(edge.source, edge.target) for edge in graph.edges] == [("101", "102"), ("102", "103")]
    assert report["source_rows"] == 3
    assert report["selected_edges"] == 2
    assert report["coverage"] == "bounded subset; not whole-CNS coverage"


def test_connectome_loader_supports_deterministic_release_row_partitions(tmp_path):
    pa = pytest.importorskip("pyarrow")
    feather = pytest.importorskip("pyarrow.feather")
    path = tmp_path / "partitioned.feather"
    feather.write_feather(
        pa.table({"body_pre": [101, 102, 103, 104], "body_post": [102, 103, 104, 101], "weight": [4, 9, 16, 25]}),
        path,
    )
    manifest = ConnectomeManifest(
        "male-cns:v1.0", "https://source", "https://license", sha256_file(path),
        "minconf-0.5", "verified", "male-cns:v1.0", "presynaptic_to_postsynaptic",
        ("body_pre", "body_post", "weight"), path.stat().st_size, 4,
    )
    start, end = deterministic_row_range(4, partition_index=1, partition_count=2)
    graph, report = load_connectome_graph(path, manifest, max_edges=10, row_start=start, row_end=end)
    assert (start, end) == (2, 4)
    assert [(edge.source, edge.target) for edge in graph.edges] == [("103", "104"), ("104", "101")]
    assert report["selection"] == "release_rows_2_4"
    with pytest.raises(ValueError, match="partition"):
        deterministic_row_range(4, partition_index=2, partition_count=2)
    with pytest.raises(ValueError, match="partition"):
        deterministic_row_range(2, partition_index=0, partition_count=3)


def test_frozen_readout_and_neural_gate_are_traceable():
    readout = FrozenReadout.fit([ReadoutRow((1.0, 0.0), 1.0), ReadoutRow((0.0, 1.0), 2.0)], graph_hash_value="g" * 64)
    assert readout.graph_hash_before == readout.graph_hash_after
    assert readout.predict((1.0, 0.0)) != readout.predict((0.0, 1.0))
    comparisons = run_matched_comparisons(["fly", "ordinary"], [1, 2, 3, 4, 5], lambda name, seed: (seed, 0.1, "g" * 64))
    review = review_neural_progression(comparisons, [AblationResult("reset", 0, "state", None)])
    assert review.decision == "inconclusive"
    assert "insufficient_positive_test_windows" in review.reasons


def test_ridge_uses_dual_system_for_wide_connectome_states():
    weights, intercept = fit_ridge(
        [(1.0, 0.0, 0.5, -1.0), (0.0, 1.0, -0.5, 1.0)],
        [10.0, -5.0],
        l2=1.0,
    )
    assert len(weights) == 4
    assert all(value == value for value in (*weights, intercept))


def test_neural_package_reload_preserves_hashes_and_predictions(tmp_path):
    graph = build_graph([Edge("a", "b", 0.5)])
    readout = FrozenReadout.fit([ReadoutRow((1.0, 0.0), 1.0), ReadoutRow((0.0, 1.0), 2.0)], graph_hash_value=graph_hash(graph))
    package = save_neural_package(
        tmp_path / "package",
        graph=graph,
        reservoir_config={"decay": 0.9, "input_scale": 1.0},
        readout=readout,
        model_card={"decision": "inconclusive", "hypothesis": "topology"},
    )
    reloaded = load_neural_package(tmp_path / "package")
    assert package.readout.predict((0.25, 0.75)) == reloaded.readout.predict((0.25, 0.75))
    assert reloaded.manifest["graph_hash"] == graph_hash(reloaded.graph)
