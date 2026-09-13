"""Portable, hash-checked package for a frozen neural experiment."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from willfly.models.connectome.graph import Edge, SparseGraph, graph_hash
from willfly.models.readout import FrozenReadout


@dataclass(frozen=True)
class NeuralPackage:
    manifest: Mapping[str, Any]
    graph: SparseGraph
    reservoir_config: Mapping[str, Any]
    readout: FrozenReadout
    model_card: Mapping[str, Any]


def save_neural_package(
    directory: str | Path,
    *,
    graph: SparseGraph,
    reservoir_config: Mapping[str, Any],
    readout: FrozenReadout,
    model_card: Mapping[str, Any],
) -> NeuralPackage:
    """Write model inputs and metadata, then return the reloaded package."""

    target = Path(directory)
    if readout.graph_hash_before != graph_hash(graph) or readout.graph_hash_after != graph_hash(graph):
        raise ValueError("readout does not belong to supplied graph")
    target.mkdir(parents=True, exist_ok=True)
    payloads = {
        "graph.json": {
            "nodes": list(graph.nodes),
            "edges": [edge.__dict__ for edge in graph.edges],
            "orientation": graph.orientation,
        },
        "reservoir.json": dict(reservoir_config),
        "readout.json": {
            "weights": list(readout.weights),
            "intercept": readout.intercept,
            "graph_hash_before": readout.graph_hash_before,
            "graph_hash_after": readout.graph_hash_after,
            "training_hash": readout.training_hash,
        },
        "model-card.json": dict(model_card),
    }
    hashes: dict[str, str] = {}
    for name, payload in payloads.items():
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        (target / name).write_bytes(encoded)
        hashes[name] = hashlib.sha256(encoded).hexdigest()
    manifest = {
        "schema_version": "neural-package-v1",
        "files": hashes,
        "graph_hash": readout.graph_hash_after,
        "readout_training_hash": readout.training_hash,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return load_neural_package(target)


def load_neural_package(directory: str | Path) -> NeuralPackage:
    target = Path(directory)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    required = {"graph.json", "reservoir.json", "readout.json", "model-card.json"}
    if manifest.get("schema_version") != "neural-package-v1" or set(manifest.get("files", {})) != required:
        raise ValueError("neural package requires hashes for exactly the expected files")
    for name, expected_hash in manifest.get("files", {}).items():
        actual = hashlib.sha256((target / name).read_bytes()).hexdigest()
        if actual != expected_hash:
            raise ValueError(f"neural package hash mismatch: {name}")
    graph_payload = json.loads((target / "graph.json").read_text(encoding="utf-8"))
    graph = SparseGraph(
        tuple(graph_payload["nodes"]),
        tuple(Edge(**edge) for edge in graph_payload["edges"]),
        graph_payload["orientation"],
    )
    readout_payload = json.loads((target / "readout.json").read_text(encoding="utf-8"))
    readout = FrozenReadout(
        tuple(readout_payload["weights"]),
        readout_payload["intercept"],
        readout_payload["graph_hash_before"],
        readout_payload["graph_hash_after"],
        readout_payload["training_hash"],
    )
    if manifest.get("graph_hash") != readout.graph_hash_after:
        raise ValueError("neural package graph hash metadata mismatch")
    if graph_hash(graph) != readout.graph_hash_after or readout.graph_hash_before != readout.graph_hash_after:
        raise ValueError("neural package graph content does not match readout")
    if manifest.get("readout_training_hash") != readout.training_hash:
        raise ValueError("neural package training hash metadata mismatch")
    return NeuralPackage(
        manifest,
        graph,
        json.loads((target / "reservoir.json").read_text(encoding="utf-8")),
        readout,
        json.loads((target / "model-card.json").read_text(encoding="utf-8")),
    )
