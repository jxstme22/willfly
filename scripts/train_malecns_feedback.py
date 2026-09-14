"""Train the bounded MaleCNS laboratory from durable causal feedback rows.

The feedback store supplies labels, while the feature and partition files are
explicit operator inputs. A market-feedback corpus can supply those same
maps after its own declared chronological split. This script never derives
features from outcomes, or treats a waiting run as trained.
"""

from __future__ import annotations

import argparse
import hashlib
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
from willfly.features.market_feedback import MarketPoint, corpus_bundle_content_hash, corpus_content_hashes
from willfly.storage.feedback import FeedbackStore
from willfly.domain import OutcomeRecord, PredictionRecord


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _load_mapping(path: Path, name: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(key): value for key, value in payload.items()}


def _load_corpus(path: Path) -> tuple[dict[str, object], tuple[PredictionRecord, ...], tuple[OutcomeRecord, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.market-feedback-bundle.v0.1":
        raise ValueError("corpus must use willfly.market-feedback-bundle.v0.1")
    raw_predictions = payload.get("predictions")
    raw_outcomes = payload.get("outcomes")
    raw_observations = payload.get("market_observations", [])
    features = payload.get("features_by_prediction")
    partitions = payload.get("partitions_by_prediction")
    if not isinstance(raw_predictions, list) or not isinstance(raw_outcomes, list):
        raise ValueError("corpus predictions and outcomes must be arrays")
    if not isinstance(raw_observations, list):
        raise ValueError("corpus market_observations must be an array")
    if not isinstance(features, dict) or not isinstance(partitions, dict):
        raise ValueError("corpus must contain feature and partition maps")
    nonempty = bool(raw_predictions or raw_outcomes or raw_observations)
    if nonempty:
        if payload.get("canonical_projection_required") is not True:
            raise ValueError("non-empty corpus must declare canonical_projection_required")
        checkpoint = payload.get("canonical_checkpoint")
        if not isinstance(checkpoint, dict) or checkpoint.get("state") != "canonical":
            raise ValueError("non-empty corpus requires a resolved canonical checkpoint")
        provenance = payload.get("provenance")
        required_provenance = (
            "source",
            "config_hash",
            "canonical_tip_hash",
            "canonical_event_set_hash",
            "canonical_checkpoint_hash",
            "event_content_hash",
            "observation_content_hash",
            "predictions_content_hash",
            "outcomes_content_hash",
            "features_content_hash",
            "partitions_content_hash",
            "bundle_content_hash",
        )
        if not isinstance(provenance, dict) or any(
            not isinstance(provenance.get(field), str) or not provenance[field]
            for field in required_provenance
        ):
            raise ValueError("non-empty corpus requires complete source provenance")
        if provenance["source"] != payload.get("source"):
            raise ValueError("corpus provenance source does not match bundle source")
        if provenance["canonical_tip_hash"] != checkpoint.get("tip_hash"):
            raise ValueError("corpus provenance tip does not match canonical checkpoint")
        if provenance["canonical_checkpoint_hash"] != _mapping_hash(checkpoint):
            raise ValueError("corpus provenance checkpoint hash does not match canonical checkpoint")
    if payload.get("personal_trade_count", 0) != 0:
        raise ValueError("market corpus must not use personal trades as its training trigger")
    predictions = tuple(PredictionRecord.from_dict(item) for item in raw_predictions if isinstance(item, dict))
    outcomes = tuple(OutcomeRecord.from_dict(item) for item in raw_outcomes if isinstance(item, dict))
    observations = tuple(MarketPoint.from_dict(item) for item in raw_observations if isinstance(item, dict))
    if len(predictions) != len(raw_predictions) or len(outcomes) != len(raw_outcomes):
        raise ValueError("corpus records must be objects")
    if len(observations) != len(raw_observations):
        raise ValueError("corpus market observations must be objects")
    if nonempty:
        try:
            actual_hashes = corpus_content_hashes(observations, predictions, outcomes, features, partitions)
        except (TypeError, ValueError) as exc:
            raise ValueError("corpus content is malformed") from exc
        for field, actual in actual_hashes.items():
            if provenance.get(field) != actual:
                raise ValueError(f"corpus {field} content hash does not match")
        if provenance.get("bundle_content_hash") != corpus_bundle_content_hash(payload):
            raise ValueError("corpus bundle_content_hash does not match")
    return payload, predictions, outcomes


def _mapping_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def train_feedback(
    manifest_path: Path,
    data_root: Path,
    feedback_dir: Path,
    features_path: Path | None,
    partitions_path: Path | None,
    *,
    as_of_time: str,
    max_edges: int,
    partition_index: int,
    partition_count: int,
    seeds: tuple[int, ...],
    checkpoint_dir: Path | None = None,
    max_training_examples: int = 100_000,
    corpus_path: Path | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a non-empty unique list")
    if not isinstance(max_training_examples, int) or isinstance(max_training_examples, bool) or max_training_examples <= 0:
        raise ValueError("max_training_examples must be a positive integer")
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = ConnectomeManifest.from_dict(manifest_payload)
    corpus_payload: dict[str, object] | None = None
    corpus_predictions: tuple[PredictionRecord, ...] = ()
    corpus_outcomes: tuple[OutcomeRecord, ...] = ()
    if corpus_path is not None:
        corpus_payload, corpus_predictions, corpus_outcomes = _load_corpus(corpus_path)
    if features_path is None:
        if corpus_payload is None:
            raise ValueError("features are required unless --corpus is supplied")
        feature_values = corpus_payload["features_by_prediction"]
        if not isinstance(feature_values, dict):
            raise ValueError("corpus feature map is malformed")
    else:
        feature_values = _load_mapping(features_path, "features")
    if partitions_path is None:
        if corpus_payload is None:
            raise ValueError("partitions are required unless --corpus is supplied")
        partition_values = corpus_payload["partitions_by_prediction"]
        if not isinstance(partition_values, dict):
            raise ValueError("corpus partition map is malformed")
    else:
        partition_values = _load_mapping(partitions_path, "partitions")
    if corpus_payload is not None:
        declared = corpus_payload.get("provenance")
        if isinstance(declared, dict) and features_path is not None and declared.get("features_content_hash") != _mapping_hash(feature_values):
            raise ValueError("features input does not match corpus features_content_hash")
        if isinstance(declared, dict) and partitions_path is not None and declared.get("partitions_content_hash") != _mapping_hash(partition_values):
            raise ValueError("partitions input does not match corpus partitions_content_hash")
    with FeedbackStore(feedback_dir) as store:
        if corpus_predictions or corpus_outcomes:
            store.record_predictions(corpus_predictions)
            store.record_outcomes(corpus_outcomes)
        dataset = store.dataset(as_of_time=as_of_time)
    if any(not isinstance(value, dict) for value in feature_values.values()):
        raise ValueError("features values must be prediction-to-node maps")
    if any(value not in {"train", "validation", "test"} for value in partition_values.values()):
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
            "features_sha256": sha256_file(features_path) if features_path is not None else _mapping_hash(feature_values),
            "partitions_sha256": sha256_file(partitions_path) if partitions_path is not None else _mapping_hash(partition_values),
            **({"corpus_sha256": sha256_file(corpus_path)} if corpus_path is not None else {}),
        },
        "experiment_config": {
            "decay": 0.9,
            "input_scale": 1.0,
            "l2": 1.0,
            "minimum_train_examples": minimum_train_examples,
        },
        "training_budget": {"max_training_examples": max_training_examples},
        "corpus": None if corpus_path is None else {
            "path": str(corpus_path),
            "schema_version": "willfly.market-feedback-bundle.v0.1",
            "source": corpus_payload.get("source") if corpus_payload is not None else None,
            "personal_trade_count": 0,
            "provenance": None if corpus_payload is None else corpus_payload.get("provenance"),
        },
        "provenance": None if corpus_payload is None else corpus_payload.get("provenance"),
        "operating_mode": "local_research_only",
        "execution_scope": "manual_only",
        "signing": False,
        "broadcast": False,
    }
    if len(build.samples) > max_training_examples:
        report.update(
            {
                "status": "waiting",
                "reasons": ["training_example_budget_exceeded"],
                "experiment_results": [],
                "boundary": "training-example budget exceeded; no graph load or training occurred",
            }
        )
        report["wall_seconds"] = time.perf_counter() - started
        report["process_peak_rss_bytes"] = _peak_rss_bytes()
        return report
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
            "provenance": None if corpus_payload is None else corpus_payload.get("provenance"),
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
    parser.add_argument("--features", type=Path, default=None)
    parser.add_argument("--partitions", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=None, help="market-feedback bundle supplying maps and causal labels")
    parser.add_argument("--as-of-time", required=True)
    parser.add_argument("--max-edges", type=int, default=100_000)
    parser.add_argument("--partition-index", type=int, default=1)
    parser.add_argument("--partition-count", type=int, default=4)
    parser.add_argument("--seeds", default="7,17,27")
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    parser.add_argument("--max-training-examples", type=int, default=100_000)
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
                max_training_examples=args.max_training_examples,
                corpus_path=args.corpus,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
