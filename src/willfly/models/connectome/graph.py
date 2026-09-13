"""Sparse directed graph construction and deterministic controls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random
from typing import Iterable


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    weight: float
    sign: int = 1

    def __post_init__(self) -> None:
        if not self.source or not self.target or not math.isfinite(self.weight) or self.weight == 0 or self.sign not in {-1, 1}:
            raise ValueError("graph edge is invalid")


@dataclass(frozen=True)
class SparseGraph:
    nodes: tuple[str, ...]
    edges: tuple[Edge, ...]
    orientation: str

    def __post_init__(self) -> None:
        if self.orientation not in {"source_to_target", "target_to_source"}:
            raise ValueError("unsupported graph orientation")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("graph nodes must be unique")
        if any(edge.source not in self.nodes or edge.target not in self.nodes for edge in self.edges):
            raise ValueError("graph edge references unknown node")

    @property
    def statistics(self) -> dict[str, int | float]:
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "positive_edges": sum(edge.sign > 0 for edge in self.edges),
            "negative_edges": sum(edge.sign < 0 for edge in self.edges),
        }

    def shuffled_control(self, seed: int) -> "SparseGraph":
        targets = [edge.target for edge in self.edges]
        random.Random(seed).shuffle(targets)
        return SparseGraph(self.nodes, tuple(Edge(edge.source, target, edge.weight, edge.sign) for edge, target in zip(self.edges, targets)), self.orientation)

    def random_weight_control(self, seed: int) -> "SparseGraph":
        weights = [edge.weight for edge in self.edges]
        random.Random(seed).shuffle(weights)
        return SparseGraph(self.nodes, tuple(Edge(edge.source, edge.target, weight, edge.sign) for edge, weight in zip(self.edges, weights)), self.orientation)


def build_graph(edges: Iterable[Edge], *, orientation: str = "source_to_target") -> SparseGraph:
    records = tuple(edges)
    nodes = tuple(sorted({node for edge in records for node in (edge.source, edge.target)}))
    return SparseGraph(nodes, records, orientation)


def graph_hash(graph: SparseGraph) -> str:
    payload = {"nodes": graph.nodes, "edges": [edge.__dict__ for edge in graph.edges], "orientation": graph.orientation}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
