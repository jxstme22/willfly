"""Portable, provenance-carrying Parquet dataset export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


class ExportUnavailable(RuntimeError):
    """Raised when the optional Arrow runtime is not installed."""


@dataclass(frozen=True)
class ExportManifest:
    dataset_name: str
    schema_version: str
    parquet_path: str
    manifest_path: str
    row_count: int
    logical_keys: tuple[str, ...]
    record_hashes: tuple[str, ...]
    source_config_hashes: Mapping[str, str]
    gaps: tuple[tuple[int, int], ...]
    quality_report: Mapping[str, Any]
    record_encoding: str = "canonical_json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "schema_version": self.schema_version,
            "parquet_path": self.parquet_path,
            "manifest_path": self.manifest_path,
            "row_count": self.row_count,
            "logical_keys": list(self.logical_keys),
            "record_hashes": list(self.record_hashes),
            "source_config_hashes": dict(self.source_config_hashes),
            "gaps": [list(gap) for gap in self.gaps],
            "quality_report": dict(self.quality_report),
            "record_encoding": self.record_encoding,
        }


def export_records(
    records: Iterable[Any],
    *,
    output_dir: Path,
    dataset_name: str,
    source_config_paths: Sequence[Path] = (),
    gaps: Sequence[tuple[int, int]] = (),
    quality_report: Any = None,
    schema_version: str = "dataset.v0.1",
) -> ExportManifest:
    """Write deterministic rows and a sidecar manifest.

    ``pyarrow`` is deliberately optional for the read-only core. The function
    fails explicitly when export support is unavailable; it never substitutes
    JSON or CSV under a misleading Parquet name.
    """

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ExportUnavailable("Parquet export requires the optional 'pyarrow' dependency") from exc
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", dataset_name):
        raise ValueError("dataset_name must be a safe filename stem")
    rows = [_normalise_record(record) for record in records]
    if not rows:
        raise ValueError("cannot export an empty dataset")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / f"{dataset_name}.parquet"
    manifest_path = output_dir / f"{dataset_name}.manifest.json"
    # Vendor payloads are heterogeneous. Arrow's inferred struct schema can
    # discard later-only fields or insert null fields, breaking content hashes.
    # Preserve exact canonical records; typed analytical projections are separate.
    table = pa.table({"record_json": [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows]})
    pq.write_table(table, parquet_path, compression="zstd", use_dictionary=True)
    config_hashes = {
        str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for path in source_config_paths
    }
    logical_keys = tuple(_logical_key(row) for row in rows)
    record_hashes = tuple(_digest(row) for row in rows)
    manifest = ExportManifest(
        dataset_name=dataset_name,
        schema_version=schema_version,
        parquet_path=parquet_path.name,
        manifest_path=manifest_path.name,
        row_count=len(rows),
        logical_keys=logical_keys,
        record_hashes=record_hashes,
        source_config_hashes=config_hashes,
        gaps=tuple(gaps),
        quality_report=_normalise_metadata(quality_report),
    )
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_export(dataset_dir: Path, dataset_name: str) -> list[dict[str, Any]]:
    """Read an export and verify its row, key and content hashes."""

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ExportUnavailable("Parquet import requires the optional 'pyarrow' dependency") from exc
    dataset_dir = Path(dataset_dir)
    manifest_path = dataset_dir / f"{dataset_name}.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parquet_name = manifest["parquet_path"]
    if Path(parquet_name).name != parquet_name:
        raise ValueError("manifest parquet path must be a local filename")
    stored = pq.read_table(dataset_dir / parquet_name).to_pylist()
    rows = ([json.loads(row["record_json"]) for row in stored]
            if manifest.get("record_encoding") == "canonical_json"
            else [_normalise_record(row) for row in stored])
    if len(rows) != manifest["row_count"]:
        raise ValueError("export row count does not match its manifest")
    if tuple(_logical_key(row) for row in rows) != tuple(manifest["logical_keys"]):
        raise ValueError("export logical keys do not match its manifest")
    if tuple(_digest(row) for row in rows) != tuple(manifest["record_hashes"]):
        raise ValueError("export record hashes do not match its manifest")
    return rows


def _normalise_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        value = record.to_dict()
    elif is_dataclass(record):
        value = asdict(record)
    elif isinstance(record, Mapping):
        value = dict(record)
    else:
        raise TypeError("export records must be mappings or dataclass-like contracts")
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _normalise_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        value = asdict(value)
    if not isinstance(value, Mapping):
        raise TypeError("quality_report must be a mapping or dataclass")
    return json.loads(json.dumps(dict(value), sort_keys=True, separators=(",", ":")))


def _logical_key(row: Mapping[str, Any]) -> str:
    if {"chain_id", "block_hash", "transaction_hash", "log_index"}.issubset(row):
        value = [row["chain_id"], row["block_hash"], row["transaction_hash"], row["log_index"]]
    else:
        value = row
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
