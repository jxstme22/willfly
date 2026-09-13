"""One prediction-to-action map shared by ordinary model families."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prediction:
    model_id: str
    expected_return_bps: int
    uncertainty_bps: int
    as_of_time: str


@dataclass(frozen=True)
class ActionMappingConfig:
    enter_threshold_bps: int = 100
    exit_threshold_bps: int = -100
    max_uncertainty_bps: int = 500


@dataclass(frozen=True)
class MappedAction:
    action: str
    reason: str
    model_id: str


def map_prediction(prediction: Prediction, config: ActionMappingConfig = ActionMappingConfig(), *, position_open: bool = False) -> MappedAction:
    if prediction.uncertainty_bps > config.max_uncertainty_bps:
        return MappedAction("watch", "uncertainty_above_threshold", prediction.model_id)
    if position_open and prediction.expected_return_bps <= config.exit_threshold_bps:
        return MappedAction("exit", "expected_return_below_exit_threshold", prediction.model_id)
    if not position_open and prediction.expected_return_bps >= config.enter_threshold_bps:
        return MappedAction("enter", "expected_return_above_entry_threshold", prediction.model_id)
    return MappedAction("hold" if position_open else "watch", "threshold_not_met", prediction.model_id)
