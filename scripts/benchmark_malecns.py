"""Measure bounded MaleCNS graph loading and reservoir resources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import time

from willfly.models.connectome import ConnectomeManifest, deterministic_row_range, load_connectome_graph
from willfly.models.reservoir import SparseReservoir


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    return int(value if sys.platform == "darwin" else value * 1024)


def benchmark(
    manifest_path: Path,
    data_root: Path,
    *,
    edge_budgets: tuple[int, ...],
    partition_index: int,
    partition_count: int,
) -> dict[str, object]:
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = ConnectomeManifest.from_dict(manifest_payload)
    graph_path = data_root / Path(str(manifest.source_url)).name
    if manifest.artifact_rows is None:
        raise ValueError("benchmark requires manifest artifact_rows")
    row_start, row_end = deterministic_row_range(
        manifest.artifact_rows,
        partition_index=partition_index,
        partition_count=partition_count,
    )
    results: list[dict[str, object]] = []
    for max_edges in edge_budgets:
        started = time.perf_counter()
        graph, report = load_connectome_graph(
            graph_path,
            manifest,
            max_edges=max_edges,
            row_start=row_start,
            row_end=row_end,
        )
        reservoir = SparseReservoir(graph, decay=0.9, input_scale=1.0)
        states = reservoir.run_episode(
            f"malecns-benchmark-{partition_index}-{max_edges}",
            [{graph.nodes[0]: 1.0}, {graph.nodes[0]: 0.0}, {graph.nodes[0]: 0.5}],
        )
        results.append(
            {
                "max_edges": max_edges,
                "selected_edges": report["selected_edges"],
                "selected_nodes": report["selected_nodes"],
                "rows_scanned": report["rows_scanned"],
                "graph_hash": reservoir.graph_hash,
                "reservoir_steps": len(states),
                "wall_seconds": time.perf_counter() - started,
            }
        )
    return {
        "release_id": manifest.release_id,
        "dataset_id": manifest.dataset_id,
        "artifact_rows": manifest.artifact_rows,
        "partition": {
            "index": partition_index,
            "count": partition_count,
            "row_start": row_start,
            "row_end": row_end,
            "policy": "contiguous_release_order_rows",
        },
        "runs": results,
        "process_peak_rss_bytes": _peak_rss_bytes(),
        "training": "not_run; benchmark measures verified graph loading and reservoir execution only",
        "coverage": "bounded deterministic partition; not whole-CNS coverage",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("configs/connectome/male-cns-v1.0.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data/connectome/male-cns-v1.0"))
    parser.add_argument("--max-edges", type=int, action="append", default=None)
    parser.add_argument("--partition-index", type=int, default=0)
    parser.add_argument("--partition-count", type=int, default=1)
    args = parser.parse_args()
    budgets = tuple(args.max_edges or (20_000, 100_000))
    if any(value <= 0 for value in budgets):
        raise SystemExit("--max-edges values must be positive")
    print(json.dumps(benchmark(
        args.manifest,
        args.data_root,
        edge_budgets=budgets,
        partition_index=args.partition_index,
        partition_count=args.partition_count,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
