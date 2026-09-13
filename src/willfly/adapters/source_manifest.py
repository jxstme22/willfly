"""Offline validation for the pinned Robinhood Chain source manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


EXPECTED_CHAIN_ID = 4663
EXPECTED_V4_EVENTS = {"Initialize", "Swap", "ModifyLiquidity"}
EXPECTED_PONS_EVENTS = {
    "TokenLaunched",
    "LaunchSwept",
    "GraduationTokensPermanentlyLocked",
    "PoolGraduated",
}


def _https_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an HTTPS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be a credential-free HTTPS URL")
    return value


def _wss_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a credential-free WSS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "wss" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be a credential-free WSS URL")
    return value


def _repository_root(manifest_path: Path) -> Path:
    """Resolve repository-relative artifact paths without assuming cwd."""

    resolved = manifest_path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == "configs":
            return parent.parent
    return Path.cwd().resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_abi(root: Path, name: str, payload: dict[str, Any], expected_events: set[str]) -> dict[str, Any]:
    relative = payload.get("abi_manifest")
    if not isinstance(relative, str):
        raise ValueError(f"{name} ABI manifest path is missing")
    abi_path = root / relative
    if not abi_path.is_file():
        raise ValueError(f"{name} ABI manifest is missing: {relative}")
    actual_hash = _sha256(abi_path)
    expected_hash = payload.get("abi_sha256")
    if actual_hash != expected_hash:
        raise ValueError(f"{name} ABI hash mismatch")
    abi = json.loads(abi_path.read_text(encoding="utf-8"))
    names = {item.get("name") for item in abi.get("events", []) if isinstance(item, dict)}
    if names != expected_events:
        raise ValueError(f"{name} ABI event families do not match the pinned manifest")
    _https_url(abi.get("source"), f"{name} ABI source")
    return {
        "manifest": relative,
        "sha256": actual_hash,
        "event_families": sorted(names),
        "source_commit": abi.get("source_commit"),
    }


def validate_source_manifest(path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Validate local declarations and return an honest bounded-readiness report."""

    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    repository_root = Path(root).resolve() if root is not None else _repository_root(manifest_path)
    if payload.get("operating_mode") != "read_only":
        raise ValueError("source manifest must be read_only")
    chain = payload.get("chain")
    if not isinstance(chain, dict) or chain.get("chain_id") != EXPECTED_CHAIN_ID:
        raise ValueError("source manifest chain identity is not Robinhood Chain 4663")
    endpoints = {
        name: _https_url(chain.get(name), f"chain.{name}")
        for name in ("rpc_url", "sequencer_url", "explorer_url")
    }
    _wss_url(chain.get("websocket_url"), "chain.websocket_url")
    protocols = payload.get("protocols")
    if not isinstance(protocols, dict):
        raise ValueError("protocols section is required")
    v4 = protocols.get("uniswap_v4")
    launch_sources = payload.get("launch_sources")
    pons = launch_sources.get("pons_v2") if isinstance(launch_sources, dict) else None
    if not isinstance(v4, dict) or not isinstance(pons, dict):
        raise ValueError("pinned V4 and Pons V2 manifests are required")
    abi_reports = {
        "uniswap_v4": _validate_abi(repository_root, "uniswap_v4", v4, EXPECTED_V4_EVENTS),
        "pons_v2": _validate_abi(repository_root, "pons_v2", pons, EXPECTED_PONS_EVENTS),
    }
    selection = payload.get("selection")
    if not isinstance(selection, dict) or not isinstance(selection.get("gate_failures"), list):
        raise ValueError("source selection must retain explicit gate failures")
    probe = payload.get("last_bounded_probe")
    if not isinstance(probe, dict) or probe.get("observed_chain_id") != EXPECTED_CHAIN_ID:
        raise ValueError("last bounded probe does not confirm the declared chain")
    return {
        "manifest": str(manifest_path),
        "chain_id": EXPECTED_CHAIN_ID,
        "operating_mode": payload["operating_mode"],
        "credential_free_endpoints": list(endpoints),
        "abi_reports": abi_reports,
        "observed_probe": {
            "date": probe.get("date"),
            "observed_head": probe.get("observed_head"),
        },
        "open_gates": list(selection["gate_failures"]),
        "status": "ready_with_open_gates" if selection["gate_failures"] else "verified",
        "note": "Manifest validation is offline; it does not measure current provider availability or completeness.",
    }


__all__ = ["validate_source_manifest"]
