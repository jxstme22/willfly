"""Reproducible replay dataset and evidence bundle."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from willfly.evaluation.replay_audit import ReplayAudit
from willfly.evaluation.splits import SplitManifest


@dataclass(frozen=True)
class ReplayBundle:
    bundle_name: str
    dataset_path: str
    labels_path: str
    splits_path: str
    audit_path: str
    accounting_path: str
    manifest_path: str
    dataset_hash: str
    labels_hash: str
    splits_hash: str
    audit_hash: str
    accounting_hash: str
    minimum_sample_met: bool
    profitability_claim_status: str


def write_replay_bundle(
    *,
    output_dir: Path,
    bundle_name: str,
    dataset_rows: Iterable[Mapping[str, Any]],
    labels: Iterable[Any],
    split_manifest: SplitManifest,
    audit: ReplayAudit,
    accounting_summary: Mapping[str, Any] | None = None,
    minimum_sample_met: bool = False,
) -> ReplayBundle:
    """Write content-addressed JSON evidence and an explicit claim gate."""

    if not bundle_name or bundle_name in {".", ".."} or "/" in bundle_name or "\\" in bundle_name:
        raise ValueError("bundle_name must be a simple directory name")
    output = Path(output_dir) / bundle_name
    output.mkdir(parents=True, exist_ok=True)
    dataset_path = output / "dataset.json"
    labels_path = output / "labels.json"
    splits_path = output / "splits.json"
    audit_path = output / "audit.json"
    accounting_path = output / "accounting.json"
    _write(dataset_path, list(dataset_rows))
    _write(labels_path, [_to_dict(label) for label in labels])
    _write(splits_path, split_manifest.to_dict())
    _write(audit_path, audit.to_dict())
    _write(accounting_path, dict(accounting_summary or {"status": "unavailable"}))
    hashes = {path.name: _hash_file(path) for path in (dataset_path, labels_path, splits_path, audit_path, accounting_path)}
    manifest = {
        "bundle_name": bundle_name,
        "dataset_path": dataset_path.name,
        "labels_path": labels_path.name,
        "splits_path": splits_path.name,
        "audit_path": audit_path.name,
        "accounting_path": accounting_path.name,
        "hashes": hashes,
        "minimum_sample_met": minimum_sample_met,
        "profitability_claim_status": "inconclusive",
        "reproduction_command": "python -m willfly fixture-check && python -m pytest",
    }
    manifest_path = output / "manifest.json"
    _write(manifest_path, manifest)
    return ReplayBundle(
        bundle_name,
        str(dataset_path),
        str(labels_path),
        str(splits_path),
        str(audit_path),
        str(accounting_path),
        str(manifest_path),
        hashes[dataset_path.name],
        hashes[labels_path.name],
        hashes[splits_path.name],
        hashes[audit_path.name],
        hashes[accounting_path.name],
        minimum_sample_met,
        manifest["profitability_claim_status"],
    )


def _to_dict(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
