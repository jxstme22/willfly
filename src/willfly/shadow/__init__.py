"""Prospective, read-only hypothetical decision loop."""

from willfly.shadow.config import FrozenShadowConfig, freeze_shadow_config
from willfly.shadow.health import ShadowHealth, assess_shadow_health, prescribed_management_action
from willfly.shadow.runner import (
    ShadowCheckpointStore,
    ShadowDecision,
    ShadowInput,
    ShadowObservation,
    ShadowRunner,
    ShadowRunSummary,
    ShadowStepResult,
)

__all__ = [
    "FrozenShadowConfig",
    "ShadowCheckpointStore",
    "ShadowDecision",
    "ShadowInput",
    "ShadowHealth",
    "ShadowObservation",
    "ShadowRunner",
    "ShadowRunSummary",
    "ShadowStepResult",
    "assess_shadow_health",
    "freeze_shadow_config",
    "prescribed_management_action",
]
