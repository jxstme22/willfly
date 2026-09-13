"""Frozen-reservoir linear readout."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable
from willfly.models.ridge import fit_ridge


@dataclass(frozen=True)
class ReadoutRow:
    features: tuple[float, ...]
    target: float


@dataclass(frozen=True)
class FrozenReadout:
    weights: tuple[float, ...]
    intercept: float
    graph_hash_before: str
    graph_hash_after: str
    training_hash: str

    @classmethod
    def fit(cls, rows: Iterable[ReadoutRow], *, graph_hash_value: str, l2: float = 1.0) -> "FrozenReadout":
        records = tuple(rows)
        if not records or l2 < 0:
            raise ValueError("readout requires rows and non-negative regularization")
        width = len(records[0].features)
        if width == 0 or any(len(row.features) != width for row in records):
            raise ValueError("readout feature widths must match")
        weights, intercept = fit_ridge([row.features for row in records], [row.target for row in records], l2)
        payload = [row.__dict__ for row in records]
        training_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(weights, intercept, graph_hash_value, graph_hash_value, training_hash)

    def predict(self, features: tuple[float, ...]) -> float:
        if len(features) != len(self.weights):
            raise ValueError("readout feature width mismatch")
        return self.intercept + sum(weight * feature for weight, feature in zip(self.weights, features))
