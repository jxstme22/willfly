"""Dependency-free regularized prediction baselines."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable
from willfly.models.ridge import fit_ridge


@dataclass(frozen=True)
class FeatureRow:
    row_id: str
    episode_id: str
    features: tuple[float, ...]
    target_bps: int


@dataclass(frozen=True)
class LinearBaseline:
    weights: tuple[float, ...]
    intercept: float
    l2: float
    seed: int
    training_hash: str

    @classmethod
    def fit(cls, rows: Iterable[FeatureRow], *, l2: float = 1.0, seed: int = 0) -> "LinearBaseline":
        records = tuple(rows)
        if not records or l2 < 0:
            raise ValueError("linear training requires rows and non-negative regularization")
        width = len(records[0].features)
        if width == 0 or any(len(row.features) != width for row in records):
            raise ValueError("feature widths must match")
        weights, intercept = fit_ridge([row.features for row in records], [row.target_bps for row in records], l2)
        digest = _hash_rows(records)
        return cls(weights, intercept, l2, seed, digest)

    def predict(self, features: tuple[float, ...]) -> float:
        if len(features) != len(self.weights):
            raise ValueError("feature width does not match trained model")
        return self.intercept + sum(weight * feature for weight, feature in zip(self.weights, features))

    def to_dict(self) -> dict[str, object]:
        return {"kind": "linear", "weights": list(self.weights), "intercept": self.intercept, "l2": self.l2, "seed": self.seed, "training_hash": self.training_hash}


@dataclass(frozen=True)
class RecurrentBaseline:
    input_weights: tuple[float, ...]
    readout: float
    decay: float
    seed: int
    training_hash: str

    @classmethod
    def fit(cls, rows: Iterable[FeatureRow], *, decay: float = 0.8, seed: int = 0) -> "RecurrentBaseline":
        records = tuple(rows)
        if not records or not 0 <= decay < 1:
            raise ValueError("recurrent baseline requires rows and decay in [0,1)")
        width = len(records[0].features)
        if width == 0 or any(len(row.features) != width for row in records):
            raise ValueError("feature widths must match")
        # The state is trained from within-episode sequences only; there is no
        # hidden state carried across episode boundaries.
        states: list[float] = []
        current_episode: str | None = None
        state = 0.0
        for row in records:
            if row.episode_id != current_episode:
                state = 0.0
                current_episode = row.episode_id
            state = decay * state + sum(row.features) / width
            states.append(state)
        denominator = sum(state * state for state in states)
        readout = sum(state * row.target_bps for state, row in zip(states, records)) / denominator if denominator else 0.0
        return cls(tuple(1.0 / width for _ in range(width)), readout, decay, seed, _hash_rows(records))

    def predict_episode(self, rows: Iterable[FeatureRow]) -> tuple[float, ...]:
        predictions: list[float] = []
        current_episode: str | None = None
        state = 0.0
        width = len(self.input_weights)
        for row in rows:
            if row.episode_id != current_episode:
                state = 0.0
                current_episode = row.episode_id
            state = self.decay * state + sum(row.features) / width
            predictions.append(self.readout * state)
        return tuple(predictions)

    def to_dict(self) -> dict[str, object]:
        return {"kind": "recurrent", "input_weights": list(self.input_weights), "readout": self.readout, "decay": self.decay, "seed": self.seed, "training_hash": self.training_hash}


def _hash_rows(rows: tuple[FeatureRow, ...]) -> str:
    payload = [row.__dict__ for row in rows]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
