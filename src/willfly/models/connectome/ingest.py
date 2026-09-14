"""License- and ID-safe boundary for a verified MaleCNS graph artifact."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from willfly.models.connectome.graph import Edge, SparseGraph, build_graph


SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
CONNECTOME_EDGE_COLUMNS = ("body_pre", "body_post", "weight")
CONNECTOME_ANNOTATION_COLUMNS = ("bodyId", "type", "status", "somaSide")
WEIGHT_NORMALIZER = 10_000.0


@dataclass(frozen=True)
class ConnectomeManifest:
    release_id: str | None
    source_url: str | None
    license_url: str | None
    source_sha256: str | None
    curated_filter: str
    status: str
    dataset_id: str | None = None
    orientation: str | None = None
    schema_columns: tuple[str, ...] = ()
    artifact_bytes: int | None = None
    artifact_rows: int | None = None

    def __post_init__(self) -> None:
        if self.status not in {"verified", "pending_verification", "unavailable"}:
            raise ValueError("unsupported connectome manifest status")
        if self.status == "verified" and not all((self.release_id, self.source_url, self.license_url, self.source_sha256)):
            raise ValueError("verified connectome manifests require source and license metadata")
        if self.source_sha256 is not None and SHA256_RE.fullmatch(self.source_sha256) is None:
            raise ValueError("connectome source_sha256 must be a 64-character hexadecimal digest")
        if self.orientation is not None and self.orientation != "presynaptic_to_postsynaptic":
            raise ValueError("unsupported connectome orientation")
        if self.artifact_bytes is not None and (not isinstance(self.artifact_bytes, int) or self.artifact_bytes <= 0):
            raise ValueError("connectome artifact_bytes must be positive")
        if self.artifact_rows is not None and (not isinstance(self.artifact_rows, int) or self.artifact_rows <= 0):
            raise ValueError("connectome artifact_rows must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "dataset_id": self.dataset_id,
            "source_url": self.source_url,
            "license_url": self.license_url,
            "source_sha256": self.source_sha256,
            "curated_filter": self.curated_filter,
            "status": self.status,
            "orientation": self.orientation,
            "schema_columns": list(self.schema_columns),
            "artifact_bytes": self.artifact_bytes,
            "artifact_rows": self.artifact_rows,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConnectomeManifest":
        schema_columns = data.get("schema_columns", [])
        if not isinstance(schema_columns, list):
            raise ValueError("connectome schema_columns must be a list")
        return cls(
            data.get("release_id"),
            data.get("source_url"),
            data.get("license_url"),
            data.get("source_sha256"),
            data.get("curated_filter", "not_selected"),
            data.get("status"),
            data.get("dataset_id"),
            data.get("orientation"),
            tuple(schema_columns),
            data.get("artifact_bytes"),
            data.get("artifact_rows"),
        )


def validate_connectome_records(records: Iterable[Mapping[str, Any]], manifest: ConnectomeManifest) -> tuple[dict[str, Any], ...]:
    """Validate node IDs as text and preserve excluded records for accounting."""

    if manifest.status != "verified":
        raise ValueError("connectome manifest must be verified before records enter a claimed experiment")
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record.get("source"), str) or not isinstance(record.get("target"), str):
            raise ValueError("connectome IDs must remain strings")
        weight = record.get("weight")
        if "weight" not in record or isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(float(weight)):
            raise ValueError("connectome edge weight must be numeric")
        item = dict(record)
        item["included"] = bool(record.get("included", True))
        item["exclusion_reason"] = None if item["included"] else str(record.get("exclusion_reason", "filtered"))
        normalized.append(item)
    return tuple(normalized)


def sha256_file(path: str | Path) -> str:
    """Hash an artifact in bounded memory before it can enter the model path."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_feather_reader(path: str | Path, manifest: ConnectomeManifest):
    if manifest.status != "verified":
        raise ValueError("connectome manifest must be verified before artifact loading")
    if manifest.orientation != "presynaptic_to_postsynaptic":
        raise ValueError("connectome manifest must declare presynaptic_to_postsynaptic orientation")
    if tuple(manifest.schema_columns) != CONNECTOME_EDGE_COLUMNS:
        raise ValueError("connectome manifest schema does not match the directed edge table")
    artifact = Path(path)
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    if manifest.artifact_bytes is None or artifact.stat().st_size != manifest.artifact_bytes:
        raise ValueError("connectome artifact byte count does not match the manifest")
    actual_sha256 = sha256_file(artifact)
    if actual_sha256.lower() != str(manifest.source_sha256).lower():
        raise ValueError("connectome artifact SHA-256 does not match the manifest")
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover - exercised only without export extras
        raise RuntimeError("pyarrow is required to load Feather connectome artifacts") from exc
    source = pa.memory_map(str(artifact), "r")
    reader = pa.ipc.open_file(source)
    actual_columns = tuple(field.name for field in reader.schema)
    if actual_columns != CONNECTOME_EDGE_COLUMNS:
        source.close()
        raise ValueError(f"connectome edge schema mismatch: {actual_columns}")
    return source, reader, actual_sha256


def validate_connectome_annotations(
    path: str | Path, *, expected_sha256: str, expected_bytes: int
) -> dict[str, Any]:
    """Verify the small annotation companion without treating labels as physiology."""

    artifact = Path(path)
    if not artifact.is_file() or artifact.stat().st_size != expected_bytes:
        raise ValueError("connectome annotation byte count does not match the manifest")
    actual_sha256 = sha256_file(artifact)
    if actual_sha256.lower() != expected_sha256.lower():
        raise ValueError("connectome annotation SHA-256 does not match the manifest")
    try:
        import pyarrow.feather as feather
    except ImportError as exc:  # pragma: no cover - exercised only without export extras
        raise RuntimeError("pyarrow is required to inspect Feather annotations") from exc
    table = feather.read_table(artifact, columns=list(CONNECTOME_ANNOTATION_COLUMNS))
    if tuple(table.column_names) != CONNECTOME_ANNOTATION_COLUMNS:
        raise ValueError("connectome annotation schema mismatch")
    return {
        "artifact_bytes": artifact.stat().st_size,
        "sha256": actual_sha256,
        "rows": table.num_rows,
        "columns": list(table.column_names),
        "note": "annotation status/type fields are metadata; neurotransmitter predictions are not measured physiology",
    }


def deterministic_row_range(total_rows: int, *, partition_index: int, partition_count: int) -> tuple[int, int]:
    """Return one contiguous, balanced release-order partition."""

    if not isinstance(total_rows, int) or isinstance(total_rows, bool) or total_rows <= 0:
        raise ValueError("total_rows must be a positive integer")
    if (
        not isinstance(partition_count, int)
        or isinstance(partition_count, bool)
        or partition_count <= 0
        or partition_count > total_rows
        or not isinstance(partition_index, int)
        or isinstance(partition_index, bool)
        or not 0 <= partition_index < partition_count
    ):
        raise ValueError("partition index/count is invalid")
    start = total_rows * partition_index // partition_count
    end = total_rows * (partition_index + 1) // partition_count
    return start, max(start + 1, end)


def load_connectome_graph(
    path: str | Path,
    manifest: ConnectomeManifest,
    *,
    max_edges: int = 20_000,
    body_ids: Iterable[int] | None = None,
    row_start: int = 0,
    row_end: int | None = None,
) -> tuple[SparseGraph, dict[str, Any]]:
    """Load a bounded, declared subset of the verified directed graph.

    The default smoke subset is the first ``max_edges`` rows in release order.
    ``row_start``/``row_end`` provide a deterministic contiguous release-order
    partition for bounded experiments that must not over-represent the first
    rows. A partition is still not whole-CNS coverage. Raw integer strengths are
    transformed with the fixed ``log1p(weight) / log1p(10000)`` rule; the
    release contains no measured sign column, so all loaded edges use the
    explicit positive sign assumption.
    """

    if not isinstance(max_edges, int) or isinstance(max_edges, bool) or max_edges <= 0:
        raise ValueError("max_edges must be a positive integer")
    if not isinstance(row_start, int) or isinstance(row_start, bool) or row_start < 0:
        raise ValueError("row_start must be a non-negative integer")
    if row_end is not None and (
        not isinstance(row_end, int)
        or isinstance(row_end, bool)
        or row_end <= row_start
    ):
        raise ValueError("row_end must be greater than row_start")
    if manifest.artifact_rows is not None and row_start >= manifest.artifact_rows:
        raise ValueError("row_start is outside the connectome artifact")
    if manifest.artifact_rows is not None and row_end is not None and row_end > manifest.artifact_rows:
        raise ValueError("row_end is outside the connectome artifact")
    allowed_ids = None if body_ids is None else {int(value) for value in body_ids}
    if allowed_ids is not None and not allowed_ids:
        raise ValueError("body_ids cannot be empty")
    source, reader, actual_sha256 = _verified_feather_reader(path, manifest)
    edges: list[Edge] = []
    rows_seen = 0
    source_row = 0
    window_end = row_end
    try:
        for batch_index in range(reader.num_record_batches):
            batch = reader.get_batch(batch_index)
            pre_values = batch.column(0).to_pylist()
            post_values = batch.column(1).to_pylist()
            weight_values = batch.column(2).to_pylist()
            for source_id, target_id, raw_weight in zip(pre_values, post_values, weight_values):
                if source_row < row_start:
                    source_row += 1
                    continue
                if window_end is not None and source_row >= window_end:
                    break
                source_row += 1
                rows_seen += 1
                if allowed_ids is not None and (source_id not in allowed_ids or target_id not in allowed_ids):
                    continue
                if not isinstance(source_id, int) or not isinstance(target_id, int) or isinstance(raw_weight, bool) or not isinstance(raw_weight, int) or raw_weight <= 0:
                    raise ValueError("connectome edge contains an ambiguous ID or non-positive weight")
                normalized_weight = math.log1p(raw_weight) / math.log1p(WEIGHT_NORMALIZER)
                if not math.isfinite(normalized_weight) or normalized_weight <= 0:
                    raise ValueError("connectome edge normalization is non-finite")
                edges.append(Edge(str(source_id), str(target_id), normalized_weight, 1))
                if len(edges) >= max_edges:
                    break
            if len(edges) >= max_edges or (window_end is not None and source_row >= window_end):
                break
    finally:
        source.close()
    if not edges:
        raise ValueError("connectome selection produced no edges")
    graph = build_graph(edges, orientation="source_to_target")
    return graph, {
        "release_id": manifest.release_id,
        "dataset_id": manifest.dataset_id,
        "artifact_bytes": manifest.artifact_bytes,
        "artifact_sha256": actual_sha256,
        "source_rows": manifest.artifact_rows,
        "rows_scanned": rows_seen,
        "selected_edges": len(edges),
        "selected_nodes": len(graph.nodes),
        "selection": (
            "body_ids_filter"
            if allowed_ids is not None and row_start == 0 and row_end is None
            else f"release_rows_{row_start}_{row_end if row_end is not None else row_start + rows_seen}"
        ),
        "orientation": manifest.orientation,
        "graph_orientation": graph.orientation,
        "weight_transform": "log1p(raw_weight)/log1p(10000)",
        "sign_source": "not_provided; explicit_positive_default",
        "coverage": "bounded subset; not whole-CNS coverage",
    }
