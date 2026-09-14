"""Run a bounded MaleCNS partition through the fixed graph/control laboratory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import time

from willfly.models.connectome import ConnectomeManifest, deterministic_row_range, load_connectome_graph
from willfly.models.laboratory import ExperimentConfig, TrainingSample, run_connectome_experiment


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def train_partition(
    manifest_path: Path,
    data_root: Path,
    *,
    max_edges: int,
    partition_index: int,
    partition_count: int,
    sample_count: int,
) -> dict[str, object]:
    started = time.perf_counter()
    if sample_count < 4:
        raise ValueError("sample_count must provide at least four training rows")
    manifest = ConnectomeManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    if manifest.artifact_rows is None or manifest.source_url is None:
        raise ValueError("training requires a complete connectome manifest")
    row_start, row_end = deterministic_row_range(
        manifest.artifact_rows,
        partition_index=partition_index,
        partition_count=partition_count,
    )
    graph, graph_report = load_connectome_graph(
        data_root / Path(manifest.source_url).name,
        manifest,
        max_edges=max_edges,
        row_start=row_start,
        row_end=row_end,
    )
    nodes = graph.nodes
    samples = tuple(
        TrainingSample(
            sample_id=f"controlled-{index}",
            episode_id=f"controlled-episode-{index}",
            observed_at=f"2026-09-14T00:00:{index:02d}Z",
            inputs={nodes[index % len(nodes)]: 1.0},
            target_bps=(index - sample_count // 2) * 25,
            partition="train" if index < sample_count - 2 else "test",
            source_refs=(f"controlled-connectome-input:{index}",),
        )
        for index in range(sample_count)
    )
    result = run_connectome_experiment(
        graph,
        samples,
        config=ExperimentConfig(
            run_id=f"malecns-partition-{partition_index}-{max_edges}",
            seed=7,
            minimum_train_examples=sample_count - 2,
        ),
    )
    return {
        "manifest": manifest.release_id,
        "dataset": manifest.dataset_id,
        "partition": {
            "index": partition_index,
            "count": partition_count,
            "row_start": row_start,
            "row_end": row_end,
        },
        "graph": graph_report,
        "experiment": result.to_dict(),
        "wall_seconds": time.perf_counter() - started,
        "process_peak_rss_bytes": _peak_rss_bytes(),
        "sample_boundary": "controlled synthetic inputs and targets; graph/control path only, no market labels",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("configs/connectome/male-cns-v1.0.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data/connectome/male-cns-v1.0"))
    parser.add_argument("--max-edges", type=int, default=100_000)
    parser.add_argument("--partition-index", type=int, default=1)
    parser.add_argument("--partition-count", type=int, default=4)
    parser.add_argument("--sample-count", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(train_partition(
        args.manifest,
        args.data_root,
        max_edges=args.max_edges,
        partition_index=args.partition_index,
        partition_count=args.partition_count,
        sample_count=args.sample_count,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
