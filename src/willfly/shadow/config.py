"""Freeze a prospective shadow configuration before the first observation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class FrozenShadowConfig:
    values: Mapping[str, Any]
    config_hash: str
    start_time: str


def freeze_shadow_config(path: str | Path, *, start_time: str) -> FrozenShadowConfig:
    """Record a canonical config hash and start time atomically enough for a local study.

    The caller must supply the planned start time explicitly. A populated hash
    or start time is rejected so a running study cannot be silently re-frozen.
    """

    parsed = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow start_time must include a timezone")
    target = Path(path)
    values = json.loads(target.read_text(encoding="utf-8"))
    if values.get("config_hash") or values.get("start_time"):
        raise ValueError("shadow configuration is already frozen")
    frozen = dict(values)
    frozen["start_time"] = start_time
    frozen["status"] = "frozen_observation_window"
    frozen.pop("config_hash", None)
    encoded = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
    config_hash = hashlib.sha256(encoded).hexdigest()
    frozen["config_hash"] = config_hash
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False, encoding="utf-8") as handle:
        temp_name = handle.name
        handle.write(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_name, target)
    return FrozenShadowConfig(frozen, config_hash, start_time)


def validate_frozen_shadow_config(values: Mapping[str, Any]) -> None:
    """Check contents rather than accepting a non-empty hash field as evidence."""
    if not values.get("start_time") or not values.get("config_hash"):
        raise ValueError("shadow configuration is not frozen")
    parsed = datetime.fromisoformat(values["start_time"].replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("shadow start_time must include a timezone")
    payload = dict(values)
    expected = payload.pop("config_hash")
    actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != actual:
        raise ValueError("shadow config hash mismatch")
