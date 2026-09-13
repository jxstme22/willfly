"""Compact rate-based sparse reservoir with explicit episode resets."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from willfly.models.connectome.graph import SparseGraph, graph_hash


@dataclass(frozen=True)
class ReservoirState:
    episode_id: str
    values: tuple[float, ...]


class SparseReservoir:
    def __init__(self, graph: SparseGraph, *, decay: float = 0.9, input_scale: float = 1.0) -> None:
        if not 0 <= decay < 1 or input_scale < 0:
            raise ValueError("reservoir controls are invalid")
        self.graph = graph
        self.decay = decay
        self.input_scale = input_scale
        self._index = {node: index for index, node in enumerate(graph.nodes)}

    @property
    def graph_hash(self) -> str:
        return graph_hash(self.graph)

    def reset(self, episode_id: str) -> ReservoirState:
        if not episode_id:
            raise ValueError("episode_id is required")
        return ReservoirState(episode_id, (0.0,) * len(self.graph.nodes))

    def step(self, state: ReservoirState, inputs: Mapping[str, float]) -> ReservoirState:
        values = list(state.values)
        incoming = [0.0] * len(values)
        for edge in self.graph.edges:
            incoming[self._index[edge.target]] += values[self._index[edge.source]] * edge.weight * edge.sign
        for node, value in inputs.items():
            if node in self._index:
                incoming[self._index[node]] += self.input_scale * value
        next_values = tuple(self.decay * old + (1 - self.decay) * math.tanh(new) for old, new in zip(values, incoming))
        if not all(math.isfinite(value) for value in next_values):
            raise FloatingPointError("reservoir state became non-finite")
        return ReservoirState(state.episode_id, next_values)

    def run_episode(self, episode_id: str, inputs: list[Mapping[str, float]]) -> tuple[ReservoirState, ...]:
        state = self.reset(episode_id)
        states: list[ReservoirState] = []
        for item in inputs:
            state = self.step(state, item)
            states.append(state)
        return tuple(states)
