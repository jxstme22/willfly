"""Train the bounded MaleCNS laboratory from durable causal feedback rows.

The feedback store supplies labels, while the feature and partition files are
explicit operator inputs. This script never derives features from outcomes,
assigns a holdout automatically, or treats a waiting run as trained.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import time

from willfly.models.connectome import ConnectomeManifest, deterministic_row_range, load_connectome_graph, sha256_file
from willfly.models.laboratory import (
    ExperimentConfig,
    build_training_samples_from_feedback,
    run_connectome_experiment,
)
from willfly.storage.feedback import FeedbackStore


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _load_mapping(path: Path, name: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(key): value for key, value in payload.items()}


def train_feedback(
    manifest_path: Path,
    data_root: Path,
    feedback_dir: Path,
    features_path: Path,
    partitions_path: Path,
    *,
    as_of_time: str,
    max_edges: int,
    partition_index: int,
    partition_count: int,
    seeds: tuple[int, ...],
    checkpoint_dir: Path | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a non-empty unique list")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = ConnectomeManifest.from_dict(manifest_payload)
    with FeedbackStore(feedback_dir) as store:
        dataset = store.dataset(as_of_time=as_of_time)
    feature_values = _load_mapping(features_path, "features")
    partition_values = _load_mapping(partitions_path, "partitions")
    if any(not isinstance(value, dict) for value in feature_values.values()):
        raise ValueError("features values must be prediction-to-node maps")
    if any(not isinstance(value, str) for value in partition_values.values()):
        raise ValueError("partitions values must be train, validation or test strings")
    build = build_training_samples_from_feedback(
        dataset,
        {key: value for key, value in feature_values.items() if isinstance(value, dict)},
        partitions_by_prediction={key: value for key, value in partition_values.items() if isinstance(value, str)},
    )
    minimum_train_examples = 4
    report: dict[str, object] = {
        "as_of_time": as_of_time,
        "feedback_dir": str(feedback_dir),
        "feedback_dataset": {
            "eligible_count": len(dataset.eligible_examples),
            "example_count": len(dataset.examples),
            "missingness": list(dataset.missingness),
            "lineage": list(dataset.lineage),
        },
        "training_input": {
            "sample_count": len(build.samples),
            "excluded": [dict(item) for item in build.excluded],
        },
        "seeds": list(seeds),
        "input_hashes": {
            "manifest_sha256": sha256_file(manifest_path),
            "features_sha256": sha256_file(features_path),
            "partitions_sha256": sha256_file(partitions_path),
        },
        "experiment_config": {
            "decay": 0.9,
            "input_scale": 1.0,
            "l2": 1.0,
            "minimum_train_examples": minimum_train_examples,
        },
        "operating_mode": "local_research_only",
        "execution_scope": "manual_only",
        "signing": False,
        "broadcast": False,
    }
    if len(build.samples) < minimum_train_examples or not any(sample.partition != "train" for sample in build.samples):
        reasons = []
        if len(build.samples) < minimum_train_examples:
            reasons.append("insufficient_qualified_train_examples")
        if not any(sample.partition != "train" for sample in build.samples):
            reasons.append("no_explicit_heldout_examples")
        report.update(
            {
                "status": "waiting",
                "reasons": reasons,
                "experiment_results": [],
                "boundary": "no graph load or training occurred; causal evidence or explicit heldout assignment is insufficient",
            }
        )
        report["wall_seconds"] = time.perf_counter() - started
        report["process_peak_rss_bytes"] = _peak_rss_bytes()
        return report
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
    results = []
    for seed in seeds:
        checkpoint = None
        if checkpoint_dir is not None:
            checkpoint = checkpoint_dir / f"malecns-feedback-{partition_index}-{max_edges}-seed-{seed}.json"
        result = run_connectome_experiment(
            graph,
            build.samples,
            config=ExperimentConfig(
                run_id=f"malecns-feedback-{partition_index}-{max_edges}-seed-{seed}",
                seed=seed,
                minimum_train_examples=minimum_train_examples,
            ),
            checkpoint_path=checkpoint,
        )
        results.append(result.to_dict())
    report.update(
        {
            "status": "completed" if all(result["status"] == "completed" for result in results) else "waiting",
            "partition": {
                "index": partition_index,
                "count": partition_count,
                "row_start": row_start,
                "row_end": row_end,
            },
            "graph": graph_report,
            "experiment_results": results,
            "boundary": "causal feedback labels and operator-supplied features/partitions; no synthetic labels",
        }
    )
    report["wall_seconds"] = time.perf_counter() - started
    report["process_peak_rss_bytes"] = _peak_rss_bytes()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("configs/connectome/male-cns-v1.0.json"))
    parser.add_argument("--data-root", type=Path, default=Path("data/connectome/male-cns-v1.0"))
    parser.add_argument("--feedback-dir", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--as-of-time", required=True)
    parser.add_argument("--max-edges", type=int, default=100_000)
    parser.add_argument("--partition-index", type=int, default=1)
    parser.add_argument("--partition-count", type=int, default=4)
    parser.add_argument("--seeds", default="7,17,27")
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    args = parser.parse_args()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    print(
        json.dumps(
            train_feedback(
                args.manifest,
                args.data_root,
                args.feedback_dir,
                args.features,
                args.partitions,
                as_of_time=args.as_of_time,
                max_edges=args.max_edges,
                partition_index=args.partition_index,
                partition_count=args.partition_count,
                seeds=seeds,
                checkpoint_dir=args.checkpoint_dir,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
