"""Small offline-first command line surface for P0."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from willfly import __version__
from willfly.domain import (
    Launch,
    ManualAction,
    Observation,
    OutcomeRecord,
    PoolIdentity,
    PredictionRecord,
    RawEvent,
    SignalProposal,
    TradeEvidence,
    VendorAssessment,
    WalletCohort,
    WalletActivity,
)
from willfly.api import ReadOnlyStore, create_server
from willfly.evaluation.coverage import audit_coverage
from willfly.storage.export import ExportUnavailable, export_records
from willfly.storage.raw import AncestryAnchor, RawBatchStore, anchor_evidence_record
from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient
from willfly.ingest.backfill import BackfillCheckpointStore
from willfly.ingest.canonicalize import assess_ancestry_anchor
from willfly.ingest.supervisor import redact_endpoint, redact_error
from willfly.ingest.runner import (
    _header_from_rpc,
    backfill_to_store,
    capture_to_store,
    checkpoint_source,
    filter_identity,
)
from willfly.features.discovery import PoolProjection
from willfly.features.action_linking import link_manual_actions
from willfly.features.projections import LifecycleRevision, materialize_observatory_projection
from willfly.features.signal_generation import build_research_signals
from willfly.features.model_outputs import build_model_output_bundle
from willfly.evaluation.promotion import ModelRegistry, PredictionPoint, evaluate_candidate
from willfly.learning.watcher import LearningWatcher, WatcherConfig
from willfly.shadow.config import freeze_shadow_config, validate_frozen_shadow_config
from willfly.shadow.runner import ShadowCheckpointStore, ShadowInput, ShadowRunner
from willfly.storage.feedback import FeedbackStore
from willfly.storage.wallet import WalletObservationStore


ROOT = Path(__file__).resolve().parents[2]


def _run_id(label: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:12]
    return f"{label}-{digest}"


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _fixture_check(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    passed = 0
    checked = 0
    failures: list[str] = []
    for entry in manifest["files"]:
        checked += 1
        path = manifest_path.parent / entry["path"]
        if not path.is_file():
            failures.append(f"missing fixture: {path}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            failures.append(f"hash mismatch: {path}")
            continue
        passed += 1

    cases_path = manifest_path.parent / manifest["cases_path"]
    cases = _load_json(cases_path)
    constructors = {
        "raw_event": RawEvent.from_dict,
        "pool_identity": PoolIdentity.from_dict,
        "launch": Launch.from_dict,
        "trade_evidence": TradeEvidence.from_dict,
        "vendor_assessment": VendorAssessment.from_dict,
        "wallet_cohort": WalletCohort.from_dict,
        "observation": Observation.from_dict,
    }
    for case in cases["valid"]:
        try:
            constructors[case["type"]](case["record"])
            passed += 1
        except Exception as exc:  # pragma: no cover - message is reported to the user
            failures.append(f"valid case {case['id']} failed: {exc}")
    checked += len(cases["valid"])
    for case in cases["invalid"]:
        try:
            constructors[case["type"]](case["record"])
        except ValueError:
            passed += 1
        else:
            failures.append(f"invalid case accepted: {case['id']}")
    checked += len(cases["invalid"])
    return {
        "run_id": _run_id("fixture-check", manifest),
        "origin": manifest["origin"],
        "checked": checked,
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


def _doctor(config_path: Path, strict: bool) -> dict[str, Any]:
    config = _load_json(config_path)
    checks = {
        "network_chain_id": config["chain"]["chain_id"] == 4663,
        "read_only": config["operating_mode"] == "read_only",
        "public_rpc_declared": bool(config["chain"].get("rpc_url")),
        "selected_launch_source_gate_open": config["selection"]["launch_source_status"] != "verified",
    }
    health_checks = {name: value for name, value in checks.items() if name != "selected_launch_source_gate_open"}
    result = {
        "run_id": _run_id("doctor", config),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "checks": checks,
        "status": "ok" if all(health_checks.values()) else "degraded",
        "network_probe": config.get("last_bounded_probe", {}),
    }
    if strict and (result["status"] != "ok" or checks["selected_launch_source_gate_open"]):
        result["status"] = "failed"
    return result


def _operation_plan(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": _run_id(command, payload),
        "command": command,
        "status": "ready",
        "operating_mode": "read_only",
        "inputs": payload,
    }


def _load_signal_store(path: Path) -> dict[str, Any]:
    """Load a typed, read-only signal snapshot for the local inspection API."""

    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.signal-snapshot.v0.1":
        raise ValueError("signal snapshot schema version is unsupported")
    raw_predictions = payload.get("predictions")
    raw_proposals = payload.get("proposals")
    if not isinstance(raw_predictions, list) or not isinstance(raw_proposals, list):
        raise ValueError("signal snapshot predictions and proposals must be arrays")
    if any(not isinstance(item, dict) for item in (*raw_predictions, *raw_proposals)):
        raise ValueError("signal snapshot records must be objects")
    predictions = tuple(PredictionRecord.from_dict(item) for item in raw_predictions)
    proposals = tuple(SignalProposal.from_dict(item) for item in raw_proposals)
    readiness = payload.get("market_readiness", {})
    if not isinstance(readiness, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in readiness.items()):
        raise ValueError("signal snapshot market_readiness must be a string map")
    training_state = payload.get("training_state")
    if training_state is not None and not isinstance(training_state, dict):
        raise ValueError("signal snapshot training_state must be an object")
    as_of_time = payload.get("as_of_time")
    if not isinstance(as_of_time, str) or not as_of_time:
        raise ValueError("signal snapshot as_of_time is required")
    raw_actions = payload.get("manual_actions", [])
    raw_activities = payload.get("wallet_activities", [])
    if not isinstance(raw_actions, list) or not isinstance(raw_activities, list):
        raise ValueError("signal snapshot manual_actions and wallet_activities must be arrays")
    if any(not isinstance(item, dict) for item in (*raw_actions, *raw_activities)):
        raise ValueError("signal snapshot action records must be objects")
    manual_actions = tuple(ManualAction.from_dict(item) for item in raw_actions)
    wallet_activities = tuple(WalletActivity.from_dict(item) for item in raw_activities)
    time_window_seconds = payload.get("action_link_time_window_seconds", 120)
    if isinstance(time_window_seconds, bool) or not isinstance(time_window_seconds, int) or time_window_seconds < 0:
        raise ValueError("signal snapshot action link time window must be non-negative")
    return {
        "predictions": predictions,
        "proposals": proposals,
        "signal_as_of_time": as_of_time,
        "market_readiness": readiness,
        "training_state": training_state,
        "manual_actions": manual_actions,
        "action_links": link_manual_actions(
            manual_actions, wallet_activities, time_window_seconds=time_window_seconds
        ),
    }


def _load_prediction_points(path: Path) -> tuple[PredictionPoint, ...]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.prediction-points.v0.1":
        raise ValueError("prediction points schema version is unsupported")
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        raise ValueError("prediction points must be an array")
    return tuple(PredictionPoint.from_dict(item) for item in raw_points)


def _load_prediction_templates(path: Path) -> tuple[PredictionRecord, ...]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.prediction-template-bundle.v0.1":
        raise ValueError("prediction template bundle schema version is unsupported")
    raw_predictions = payload.get("predictions")
    if not isinstance(raw_predictions, list) or any(not isinstance(item, dict) for item in raw_predictions):
        raise ValueError("prediction template bundle predictions must be an array of objects")
    return tuple(PredictionRecord.from_dict(item) for item in raw_predictions)


def _load_string_map(path: Path | None, field: str) -> dict[str, str]:
    if path is None:
        return {}
    payload = _load_json(path)
    if not isinstance(payload, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in payload.items()
    ):
        raise ValueError(f"{field} must be a string map")
    return dict(payload)


def _load_feedback_bundle(path: Path) -> tuple[tuple[PredictionRecord, ...], tuple[OutcomeRecord, ...]]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.feedback-bundle.v0.1":
        raise ValueError("feedback bundle schema version is unsupported")
    raw_predictions = payload.get("predictions")
    raw_outcomes = payload.get("outcomes")
    if not isinstance(raw_predictions, list) or not isinstance(raw_outcomes, list):
        raise ValueError("feedback bundle predictions and outcomes must be arrays")
    if any(not isinstance(item, dict) for item in (*raw_predictions, *raw_outcomes)):
        raise ValueError("feedback bundle records must be objects")
    return (
        tuple(PredictionRecord.from_dict(item) for item in raw_predictions),
        tuple(OutcomeRecord.from_dict(item) for item in raw_outcomes),
    )


def _load_wallet_bundle(path: Path) -> tuple[WalletActivity, ...]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.wallet-activity-bundle.v0.1":
        raise ValueError("wallet activity bundle schema version is unsupported")
    raw_activities = payload.get("activities")
    if not isinstance(raw_activities, list) or any(not isinstance(item, dict) for item in raw_activities):
        raise ValueError("wallet activity bundle activities must be an array of objects")
    return tuple(WalletActivity.from_dict(item) for item in raw_activities)


def _load_model_output_bundle(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "willfly.model-output-bundle.v0.1":
        raise ValueError("model output bundle schema version is unsupported")
    raw_templates = payload.get("templates")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_templates, list) or not isinstance(raw_outputs, list):
        raise ValueError("model output bundle templates and outputs must be arrays")
    if any(not isinstance(item, dict) for item in (*raw_templates, *raw_outputs)):
        raise ValueError("model output bundle records must be objects")
    model_identity = (payload.get("model_id"), payload.get("model_version"), payload.get("run_ref"))
    if any(not isinstance(value, str) or not value for value in model_identity):
        raise ValueError("model output bundle identity is required")
    outputs: list[tuple[str, float]] = []
    for item in raw_outputs:
        sample_id = item.get("sample_id")
        predicted_bps = item.get("predicted_bps")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError("model output sample_id is required")
        if isinstance(predicted_bps, bool) or not isinstance(predicted_bps, (int, float)):
            raise ValueError("model output predicted_bps must be numeric")
        outputs.append((sample_id, predicted_bps))
    actions = payload.get("actions_by_prediction", {})
    exit_kinds = payload.get("exit_kinds_by_prediction", {})
    readiness = payload.get("market_readiness", {"spot": "research_only", "lp": "research_only"})
    if not isinstance(actions, dict) or not isinstance(exit_kinds, dict):
        raise ValueError("model output action mappings must be objects")
    if not isinstance(readiness, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in readiness.items()):
        raise ValueError("model output market_readiness must be a string map")
    as_of_time = payload.get("as_of_time")
    if not isinstance(as_of_time, str) or not as_of_time:
        raise ValueError("model output as_of_time is required")
    try:
        parsed = datetime.fromisoformat(as_of_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("model output as_of_time must be RFC-3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("model output as_of_time must include a timezone")
    training_state = payload.get("training_state")
    if training_state is not None and not isinstance(training_state, dict):
        raise ValueError("model output training_state must be an object")
    return {
        "templates": tuple(PredictionRecord.from_dict(item) for item in raw_templates),
        "outputs": tuple(outputs),
        "model_id": model_identity[0],
        "model_version": model_identity[1],
        "run_ref": model_identity[2],
        "actions": {str(key): str(value) for key, value in actions.items()},
        "exit_kinds": {str(key): str(value) for key, value in exit_kinds.items()},
        "as_of_time": as_of_time,
        "market_readiness": readiness,
        "training_state": training_state,
    }


def _signal_build(*, input_path: Path, output_path: Path | None) -> dict[str, Any]:
    payload = _load_model_output_bundle(input_path)
    result = build_research_signals(
        payload["templates"],
        payload["outputs"],
        model_id=payload["model_id"],
        model_version=payload["model_version"],
        run_ref=payload["run_ref"],
        actions_by_prediction=payload["actions"],
        exit_kinds_by_prediction=payload["exit_kinds"],
    )
    bundle = result.to_bundle(
        as_of_time=payload["as_of_time"],
        market_readiness=payload["market_readiness"],
        training_state=payload["training_state"],
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "ready" if result.proposals else "waiting",
        "prediction_count": len(result.predictions),
        "proposal_count": len(result.proposals),
        "excluded": [dict(item) for item in result.excluded],
        "input": str(input_path),
        "input_hash": _config_hash(input_path),
        "output": None if output_path is None else str(output_path),
        "output_hash": None if output_path is None else _config_hash(output_path),
        "bundle": bundle if output_path is None else None,
        "operating_mode": "local_research_only",
        "execution_scope": "manual_only",
        "signing": False,
        "broadcast": False,
    }


def _model_output(
    *,
    experiment_report_path: Path,
    templates_path: Path,
    output_path: Path,
    model_name: str,
    model_id: str,
    model_version: str,
    run_ref: str,
    as_of_time: str,
    run_id: str | None,
    actions_path: Path | None,
    exit_kinds_path: Path | None,
) -> dict[str, Any]:
    report = _load_json(experiment_report_path)
    if not isinstance(report, dict):
        raise ValueError("experiment report must be an object")
    raw_results = report.get("experiment_results")
    if raw_results is None and report.get("schema_version") == "connectome-experiment.v0.1":
        raw_results = [report]
    if not isinstance(raw_results, list) or any(not isinstance(item, dict) for item in raw_results):
        raise ValueError("experiment report must contain experiment_results")
    if run_id is None:
        if len(raw_results) != 1:
            raise ValueError("--run-id is required when the experiment report has multiple results")
        experiment = raw_results[0]
    else:
        matches = [item for item in raw_results if item.get("run_id") == run_id]
        if len(matches) != 1:
            raise ValueError("--run-id did not identify exactly one experiment result")
        experiment = matches[0]
    report_hash = _config_hash(experiment_report_path)
    bundle = build_model_output_bundle(
        experiment,
        _load_prediction_templates(templates_path),
        model_name=model_name,
        model_id=model_id,
        model_version=model_version,
        run_ref=run_ref,
        as_of_time=as_of_time,
        actions_by_prediction=_load_string_map(actions_path, "actions"),
        exit_kinds_by_prediction=_load_string_map(exit_kinds_path, "exit_kinds"),
        source_hash=report_hash,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "ready" if bundle["outputs"] else "waiting",
        "output_count": len(bundle["outputs"]),
        "model_name": model_name,
        "run_id": experiment.get("run_id"),
        "experiment_report": str(experiment_report_path),
        "experiment_report_hash": report_hash,
        "output": str(output_path),
        "output_hash": _config_hash(output_path),
        "operating_mode": "local_research_only",
        "execution_scope": "manual_only",
        "signing": False,
        "broadcast": False,
    }


def _wallet_import(*, bundle_path: Path, wallet_dir: Path) -> dict[str, Any]:
    activities = _load_wallet_bundle(bundle_path)
    with WalletObservationStore(wallet_dir) as store:
        write = store.record(activities)
    return {
        "status": "recorded",
        "bundle": str(bundle_path),
        "bundle_hash": _config_hash(bundle_path),
        "wallet_dir": str(wallet_dir),
        "activity_count": len(activities),
        "inserted": write.inserted,
        "duplicates": write.duplicates,
        "revised": write.revised,
        "operating_mode": "read_only_public_observation_import",
        "signing": False,
        "broadcast": False,
    }


def _wallet_status(*, wallet_dir: Path, wallet: str, as_of_time: str, arrival_cutoff: str) -> dict[str, Any]:
    with WalletObservationStore(wallet_dir) as store:
        observation = store.observation(wallet=wallet, as_of_time=as_of_time, arrival_cutoff=arrival_cutoff)
    return {
        "status": observation.quality_state,
        "wallet_dir": str(wallet_dir),
        "wallet": wallet,
        "activity_count": len(observation.activities),
        "position_count": len(observation.positions),
        "observation": observation.to_dict(),
        "operating_mode": "read_only",
        "signing": False,
        "broadcast": False,
    }


def _feedback_import(*, bundle_path: Path, feedback_dir: Path, as_of_time: str) -> dict[str, Any]:
    predictions, outcomes = _load_feedback_bundle(bundle_path)
    with FeedbackStore(feedback_dir) as store:
        prediction_write = store.record_predictions(predictions)
        outcome_write = store.record_outcomes(outcomes)
        queue = store.mature(as_of_time=as_of_time)
        dataset = store.dataset(as_of_time=as_of_time)
    state = "ready" if dataset.eligible_examples else "waiting"
    return {
        "status": state,
        "bundle": str(bundle_path),
        "bundle_hash": _config_hash(bundle_path),
        "feedback_dir": str(feedback_dir),
        "predictions": {
            "inserted": prediction_write.inserted,
            "duplicates": prediction_write.duplicates,
            "revised": prediction_write.revised,
        },
        "outcomes": {
            "inserted": outcome_write.inserted,
            "duplicates": outcome_write.duplicates,
            "revised": outcome_write.revised,
        },
        "as_of_time": as_of_time,
        "queue": [item.__dict__.copy() for item in queue],
        "dataset": dataset.to_dict(),
        "operating_mode": "read_only_observation_import",
        "signing": False,
        "broadcast": False,
    }


def _feedback_status(*, feedback_dir: Path, as_of_time: str) -> dict[str, Any]:
    with FeedbackStore(feedback_dir) as store:
        predictions = store.list_predictions()
        outcomes = store.list_outcomes()
        queue = store.mature(as_of_time=as_of_time)
        dataset = store.dataset(as_of_time=as_of_time)
    states: dict[str, int] = {}
    for item in queue:
        states[item.state] = states.get(item.state, 0) + 1
    return {
        "status": "ready" if dataset.eligible_examples else "waiting",
        "feedback_dir": str(feedback_dir),
        "as_of_time": as_of_time,
        "prediction_count": len(predictions),
        "outcome_count": len(outcomes),
        "queue_state_counts": states,
        "dataset": dataset.to_dict(),
        "operating_mode": "read_only",
        "signing": False,
        "broadcast": False,
    }


def _evaluate_model(
    *,
    points_path: Path,
    candidate_version: str,
    active_version: str,
    evaluated_at: str,
    dataset_hash: str,
    minimum_forward_windows: int,
    minimum_points_per_window: int,
    registry_path: Path | None,
    record: bool,
) -> dict[str, Any]:
    if record and registry_path is None:
        raise ValueError("--registry is required with --record")
    points = _load_prediction_points(points_path)
    report = evaluate_candidate(
        points,
        candidate_version=candidate_version,
        active_version=active_version,
        evaluated_at=evaluated_at,
        dataset_hash=dataset_hash,
        minimum_forward_windows=minimum_forward_windows,
        minimum_points_per_window=minimum_points_per_window,
    )
    if record:
        assert registry_path is not None
        with ModelRegistry(registry_path, initial_active_version=active_version) as registry:
            if registry.active_version != active_version:
                raise ValueError("registry active version does not match evaluation input")
            registry.record_evaluation(report)
    return {
        "status": report.decision,
        "recorded": record,
        "report": report.to_dict(),
        "points_file": str(points_path),
        "points_file_hash": _config_hash(points_path),
        "registry": None if registry_path is None else str(registry_path),
        "operating_mode": "read_only",
        "signing": False,
        "broadcast": False,
    }


def _model_status(*, registry_path: Path, initial_active_version: str) -> dict[str, Any]:
    with ModelRegistry(registry_path, initial_active_version=initial_active_version) as registry:
        status = registry.status()
    return {
        "status": "ready",
        "registry": str(registry_path),
        "state": status,
        "operating_mode": "read_only",
        "signing": False,
        "broadcast": False,
    }


def _config_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _capture_context(config: dict[str, Any], config_path: Path, addresses: list[str]) -> dict[str, Any]:
    """Derive endpoint, addresses, ABI hashes and families from the source manifest."""
    chain = config.get("chain", {})
    endpoint = chain.get("rpc_url", "")
    expected_chain = chain.get("chain_id", 4663)
    contracts = config.get("contracts", {})
    # Default addresses come from the pinned V4 manager and Pons V2 factory when
    # the caller does not supply explicit --address values.
    defaults: list[str] = []
    protocols = config.get("protocols", {})
    v4 = protocols.get("uniswap_v4", {}) if isinstance(protocols, dict) else {}
    if v4.get("pool_manager"):
        defaults.append(v4["pool_manager"])
    launches = config.get("launch_sources", {})
    pons = launches.get("pons_v2", {}) if isinstance(launches, dict) else {}
    if pons.get("address"):
        defaults.append(pons["address"])
    resolved = addresses or ([contracts] if isinstance(contracts, str) else [])
    if not resolved:
        # contracts may be a mapping in older manifests; fall back to defaults.
        resolved = defaults
    if not resolved:
        raise ValueError("no contract addresses supplied and none found in source manifest")
    abi_hashes: list[str] = []
    for key in ("abi_sha256",):
        if v4.get(key):
            abi_hashes.append(v4[key])
        if pons.get(key):
            abi_hashes.append(pons[key])
    # Also hash the ABI files when present for stronger binding.
    for manifest_rel in (v4.get("abi_manifest"), pons.get("abi_manifest")):
        if manifest_rel:
            abi_path = ROOT / manifest_rel
            if abi_path.is_file():
                abi_hashes.append(hashlib.sha256(abi_path.read_bytes()).hexdigest())
    families: list[str] = []
    families.extend(v4.get("event_families", []) or [])
    families.extend(["TokenLaunched", "LaunchSwept", "GraduationTokensPermanentlyLocked", "PoolGraduated"])
    return {
        "endpoint": endpoint,
        "expected_chain": expected_chain,
        "addresses": resolved,
        "abi_hashes": sorted(set(abi_hashes)),
        "event_families": sorted(set(families)),
        "config_hash": _config_hash(config_path),
    }


def _execute_capture(
    *,
    config_path: Path,
    from_block: int,
    to_block: int,
    addresses: list[str],
    store_dir: Path,
    run_id: str | None,
    base_source: str,
) -> dict[str, Any]:
    config = _load_json(config_path)
    ctx = _capture_context(config, config_path, addresses)
    if not ctx["endpoint"].startswith(("http://", "https://")):
        raise ValueError("source manifest RPC endpoint must be HTTP(S)")
    client = ReadOnlyRpcClient(ctx["endpoint"], expected_chain_id=ctx["expected_chain"])
    store = RawBatchStore(store_dir)
    try:
        payload = {
            "config": str(config_path),
            "from_block": from_block,
            "to_block": to_block,
            "addresses": ctx["addresses"],
            "config_hash": ctx["config_hash"],
        }
        effective_run_id = run_id or _run_id("capture", payload)
        manifest = capture_to_store(
            client,
            store,
            addresses=list(ctx["addresses"]),
            from_block=from_block,
            to_block=to_block,
            run_id=effective_run_id,
            base_source=base_source,
            config_path=str(config_path),
            config_hash=ctx["config_hash"],
            abi_hashes=ctx["abi_hashes"],
            event_families=ctx["event_families"],
            provider_endpoint=ctx["endpoint"],
        )
    finally:
        store.close()
    result = manifest.to_dict()
    result.update(status="executed", executed=True, operating_mode="read_only")
    return result


def _execute_backfill(
    *,
    config_path: Path,
    from_block: int,
    to_block: int,
    addresses: list[str],
    store_dir: Path,
    run_id: str | None,
    base_source: str,
    page_size: int,
) -> dict[str, Any]:
    config = _load_json(config_path)
    ctx = _capture_context(config, config_path, addresses)
    if not ctx["endpoint"].startswith(("http://", "https://")):
        raise ValueError("source manifest RPC endpoint must be HTTP(S)")
    client = ReadOnlyRpcClient(ctx["endpoint"], expected_chain_id=ctx["expected_chain"])
    store = RawBatchStore(store_dir)
    checkpoint_path = Path(store_dir) / "backfill_checkpoints.sqlite3"
    checkpoints = BackfillCheckpointStore(checkpoint_path)
    try:
        payload = {
            "config": str(config_path),
            "from_block": from_block,
            "to_block": to_block,
            "addresses": ctx["addresses"],
            "config_hash": ctx["config_hash"],
        }
        effective_run_id = run_id or _run_id("backfill", payload)
        manifest = backfill_to_store(
            client,
            store,
            addresses=list(ctx["addresses"]),
            start_block=from_block,
            target_block=to_block,
            run_id=effective_run_id,
            base_source=base_source,
            config_path=str(config_path),
            config_hash=ctx["config_hash"],
            abi_hashes=ctx["abi_hashes"],
            event_families=ctx["event_families"],
            provider_endpoint=ctx["endpoint"],
            page_size=page_size,
            checkpoint_store=checkpoints,
        )
    finally:
        checkpoints.close()
        store.close()
    result = manifest.to_dict()
    result.update(status="executed", executed=True, operating_mode="read_only")
    return result


def _audit(expected_path: Path, observed_path: Path, provider_independent: bool) -> dict[str, Any]:
    expected = [RawEvent.from_dict(item) for item in _load_json(expected_path)]
    observed = [RawEvent.from_dict(item) for item in _load_json(observed_path)]
    report = audit_coverage(expected, observed, provider_independent=provider_independent)
    return {"run_id": _run_id("audit", report.__dict__), "status": report.state, "report": report.__dict__}


def _export(records_path: Path, output_dir: Path, dataset_name: str) -> dict[str, Any]:
    records = _load_json(records_path)
    if not isinstance(records, list):
        raise ValueError("records JSON must contain an array")
    manifest = export_records(
        records,
        output_dir=output_dir,
        dataset_name=dataset_name,
    )
    return {"run_id": _run_id("export", manifest.to_dict()), "manifest": manifest.to_dict()}


def _materialize(
    *, input_path: Path, store_dir: Path, source: str, as_of_time: str, replaces_snapshot_id: str | None
) -> dict[str, Any]:
    """Build and persist one causal Observatory bundle from typed JSON inputs."""

    payload = _load_json(input_path)
    if not isinstance(payload, dict):
        raise ValueError("materialize input must be an object")
    pools = tuple(
        PoolProjection(
            identity=PoolIdentity.from_dict(item["identity"]),
            first_observed_at=item["first_observed_at"],
            trading_status=item["trading_status"],
            raw_event_refs=tuple(item["raw_event_refs"]),
        )
        for item in payload.get("pools", [])
    )
    projection = materialize_observatory_projection(
        as_of_time=as_of_time,
        launches=[Launch.from_dict(item) for item in payload.get("launches", [])],
        pools=pools,
        raw_events=[RawEvent.from_dict(item) for item in payload.get("raw_events", [])],
        trades=[TradeEvidence.from_dict(item) for item in payload.get("trades", [])],
        lifecycle_revisions=[LifecycleRevision.from_dict(item) for item in payload.get("lifecycle_revisions", [])],
        cohorts=[WalletCohort.from_dict(item) for item in payload.get("cohorts", [])],
        cohort_id=payload.get("cohort_id"),
    )
    with RawBatchStore(store_dir) as store:
        record = store.save_snapshot(
            projection,
            source=source,
            replaces_snapshot_id=replaces_snapshot_id,
        )
    return {
        "run_id": _run_id("materialize", {"input": str(input_path), "snapshot_id": record.snapshot_id}),
        "status": "materialized",
        "operating_mode": "read_only",
        "snapshot_id": record.snapshot_id,
        "replaces_snapshot_id": record.replaces_snapshot_id,
        "as_of_time": record.as_of_time,
        "quality_state": projection.discovery.quality_state,
        "launch_count": len(projection.discovery.launches),
        "timeline_count": len(projection.timelines),
        "exclusion_count": len(projection.exclusions),
    }


def _qualify_anchor(
    *,
    config_path: Path,
    store_dir: Path,
    base_source: str,
    addresses: list[str],
    height: int,
    block_hash: str,
    independent_rpc_url: str,
    recorded_at: str | None,
    supersedes_source: str | None,
    supersession_reason: str | None,
) -> dict[str, Any]:
    """Qualify one bounded anchor using two performed, read-only RPC checks."""

    config = _load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("source config must be an object")
    context = _capture_context(config, config_path, addresses)
    chain_id = context["expected_chain"]
    config_identity = context["config_hash"]
    primary_endpoint = context["endpoint"]
    if not isinstance(primary_endpoint, str) or not primary_endpoint.startswith(("http://", "https://")):
        raise ValueError("source manifest RPC endpoint must be HTTP(S)")
    if not isinstance(independent_rpc_url, str) or not independent_rpc_url.startswith(("http://", "https://")):
        raise ValueError("independent RPC endpoint must be HTTP(S)")
    primary_endpoint_ref = redact_endpoint(primary_endpoint)
    independent_endpoint_ref = redact_endpoint(independent_rpc_url)
    if primary_endpoint_ref == independent_endpoint_ref:
        raise ValueError("primary and independent RPC endpoints must be distinct")
    if not isinstance(height, int) or isinstance(height, bool) or height < 0:
        raise ValueError("anchor height must be a non-negative integer")
    if not isinstance(block_hash, str):
        raise ValueError("anchor block_hash must be text")
    primary = ReadOnlyRpcClient(primary_endpoint, expected_chain_id=chain_id)
    independent = ReadOnlyRpcClient(independent_rpc_url, expected_chain_id=chain_id)
    primary_chain = primary.check_chain()
    independent_chain = independent.check_chain()
    if primary_chain != chain_id or independent_chain != chain_id:
        raise ValueError("anchor RPC chain identity does not match the active source chain")
    primary_header = _header_from_rpc(primary.block(height), height)
    independent_header = _header_from_rpc(independent.block(height), height)
    if primary_header.block_hash.lower() != block_hash.lower():
        raise ValueError("primary RPC header does not match the declared anchor identity")
    if independent_header.block_hash.lower() != primary_header.block_hash.lower():
        raise ValueError("independent RPC header does not match the primary header identity")
    if (
        (independent_header.parent_hash is None) != (primary_header.parent_hash is None)
        or (
            independent_header.parent_hash is not None
            and independent_header.parent_hash.lower() != primary_header.parent_hash.lower()
        )
    ):
        raise ValueError("independent RPC parent hash does not match the primary header")
    filter_hash = filter_identity(
        chain_id=chain_id,
        addresses=context["addresses"],
        abi_hashes=context["abi_hashes"],
        event_families=context["event_families"],
    )
    source_key = checkpoint_source(base_source, chain_id, filter_hash)
    evidence_payload = {
        "chain_id": chain_id,
        "config_identity": config_identity,
        "height": height,
        "block_hash": primary_header.block_hash,
        "primary_endpoint": primary_endpoint_ref,
        "independent_endpoint": independent_endpoint_ref,
        "read_methods": ["eth_chainId", "eth_getBlockByNumber"],
        "verification": "performed_rpc_cross_check",
        "trust_policy": "distinct_configured_endpoints_operator_assumption",
        "finality_status": "not_verified",
        "primary_header": {
            "number": primary_header.number,
            "hash": primary_header.block_hash,
            "parent_hash": primary_header.parent_hash,
        },
        "external_header": {
            "number": independent_header.number,
            "hash": independent_header.block_hash,
            "parent_hash": independent_header.parent_hash,
        },
    }
    evidence = anchor_evidence_record("independent_header_cross_check", **evidence_payload)
    anchor = AncestryAnchor(
        chain_id=chain_id,
        height=height,
        block_hash=block_hash,
        qualification="independent_header_cross_check",
        evidence=(evidence,),
        config_identity=config_identity,
        source=source_key,
        recorded_at=recorded_at or datetime.now(timezone.utc).isoformat(),
    )
    state, notes = assess_ancestry_anchor(
        anchor,
        [primary_header],
        expected_chain_id=chain_id,
        expected_config_identity=config_identity,
    )
    if state != "qualified":
        raise ValueError(f"anchor rejected ({state}): {'; '.join(notes)}")
    with RawBatchStore(store_dir) as store:
        existing = store.get_ancestry_anchor(source_key)
        if existing is not None and existing.to_dict() != anchor.to_dict():
            raise ValueError("conflicting ancestry anchor already stored for this source")
        store.persist_headers([primary_header])
        store.record_header_range(
            source=source_key,
            range_start=height,
            range_end=height,
            run_id=_run_id("qualify-anchor", evidence_payload),
            headers=[primary_header],
        )
        if supersedes_source is not None:
            store.save_requalified_ancestry_anchor(
                anchor,
                supersedes_source=supersedes_source,
                reason=supersession_reason or "",
            )
        else:
            store.save_ancestry_anchor(anchor)
    return {
        "run_id": _run_id("qualify-anchor", evidence_payload),
        "status": "qualified",
        "operating_mode": "read_only",
        "source": source_key,
        "anchor_state": state,
        "anchor": anchor.to_dict(),
        "evidence": list(notes),
        "read_methods": ["eth_chainId", "eth_getBlockByNumber"],
        "primary_endpoint": primary_endpoint_ref,
        "independent_endpoint": independent_endpoint_ref,
        "supersedes_source": supersedes_source,
    }


def _shadow_plan(config_path: Path, state_db: Path) -> dict[str, Any]:
    config = _load_json(config_path)
    result = _operation_plan(
        "shadow",
        {"config": str(config_path), "state_db": str(state_db)},
    )
    result.update(
        {
            "operating_mode": "read_only",
            "hypothetical_only": True,
            "signing": False,
            "broadcast": False,
            "lp_enabled": bool(config.get("lp_enabled", False)),
        }
    )
    if not config.get("start_time") or not config.get("config_hash"):
        result.update(
            {
                "status": "blocked",
                "reason": "shadow_config_not_frozen",
                "required_before_start": ["start_time", "config_hash"],
            }
        )
    elif config.get("lp_enabled") and config.get("lp_gate") != "enabled":
        result.update(
            {
                "status": "blocked",
                "reason": "lp_gate_not_enabled",
            }
        )
    else:
        validate_frozen_shadow_config(config)
        result.update(
            {
                "status": "blocked",
                "reason": "shadow_runtime_not_integrated",
                "observation_window": "not_started",
            }
        )
    return result


def _shadow_source_config_hash(config_path: Path, config: dict[str, Any]) -> str:
    source_config = config.get("source_config")
    if not isinstance(source_config, str) or not source_config:
        raise ValueError("shadow source_config is required for a bound run")
    source_path = Path(source_config)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    if not source_path.is_file():
        raise ValueError(f"shadow source config is missing: {source_path}")
    return _config_hash(source_path)


def _execute_shadow_run(
    *,
    config_path: Path,
    state_db: Path,
    input_path: Path,
    fixed_entry_atomic: int,
    initial_cash_atomic: int,
    max_positions: int | None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("shadow config must be an object")
    validate_frozen_shadow_config(config)
    if bool(config.get("lp_enabled")):
        raise ValueError("spot-only shadow run refuses an LP-enabled configuration")
    if fixed_entry_atomic <= 0 or initial_cash_atomic < 0:
        raise ValueError("shadow atomic allocation values are invalid")
    resolved_max_positions = config.get("max_simultaneous_positions") if max_positions is None else max_positions
    if not isinstance(resolved_max_positions, int) or isinstance(resolved_max_positions, bool) or resolved_max_positions < 0:
        raise ValueError("max_positions must be a non-negative integer")
    decision_deadline_seconds = config.get("decision_interval_seconds", 15)
    if not isinstance(decision_deadline_seconds, int) or isinstance(decision_deadline_seconds, bool) or decision_deadline_seconds <= 0:
        raise ValueError("decision_interval_seconds must be a positive integer")
    payload = _load_json(input_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise ValueError("shadow input must contain an observations array")
    if not payload["observations"]:
        raise ValueError("shadow input observations cannot be empty")
    inputs = tuple(ShadowInput.from_dict(item) for item in payload["observations"])
    source_hash = _shadow_source_config_hash(config_path, config)
    identity = {
        "config_hash": str(config["config_hash"]),
        "source_config_hash": source_hash,
        "feature_version": str(config.get("feature_version", "unknown")),
        "policy_version": str(config.get("model_id", "unknown")),
        "fixed_entry_atomic": str(fixed_entry_atomic),
        "initial_cash_atomic": str(initial_cash_atomic),
        "max_positions": str(resolved_max_positions),
        "decision_deadline_seconds": str(decision_deadline_seconds),
    }
    run_id = _run_id(
        "shadow-run",
        {
            "config_hash": identity["config_hash"],
            "input_hash": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        },
    )
    store = ShadowCheckpointStore(str(state_db), run_identity=identity)
    try:
        runner = ShadowRunner(
            store,
            fixed_entry_atomic=fixed_entry_atomic,
            max_positions=resolved_max_positions,
            initial_cash_atomic=initial_cash_atomic,
            decision_deadline_seconds=decision_deadline_seconds,
            run_identity=identity,
        )
        summary = runner.run_sequence(inputs)
    finally:
        store.close()
    result = summary.to_dict()
    result.update(
        {
            "run_id": run_id,
            "config": str(config_path),
            "input": str(input_path),
            "input_hash": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "source": "controlled_file",
            "lp_enabled": False,
        }
    )
    return result


def _shadow_freeze(config_path: Path, start_time: str) -> dict[str, Any]:
    frozen = freeze_shadow_config(config_path, start_time=start_time)
    return {
        "status": "frozen",
        "config": str(config_path),
        "config_hash": frozen.config_hash,
        "start_time": frozen.start_time,
        "operating_mode": "read_only",
        "hypothetical_only": True,
        "signing": False,
        "broadcast": False,
    }


def _operator_check(config_path: Path, shadow_config_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Check a local operator installation without network or state mutation."""

    config = _load_json(config_path)
    shadow_config = _load_json(shadow_config_path)
    fixture = _fixture_check(manifest_path)
    checks = {
        "python_3_12": sys.version_info[:2] == (3, 12),
        "willfly_importable": True,
        "source_config_present": config_path.is_file(),
        "shadow_config_present": shadow_config_path.is_file(),
        "fixture_checks": fixture["failed"] == 0,
        "read_only_config": config.get("operating_mode") == "read_only",
        "lp_disabled_in_shadow": shadow_config.get("lp_enabled") is False,
    }
    platform_name = sys.platform
    wsl = bool(__import__("os").environ.get("WSL_DISTRO_NAME"))
    return {
        "status": "ready" if all(checks.values()) else "degraded",
        "checks": checks,
        "fixture": fixture,
        "platform": {"sys_platform": platform_name, "wsl": wsl},
        "network_probe": "not_run",
        "shadow_window": "frozen" if shadow_config.get("config_hash") else "not_started",
        "launch_source_gate": config.get("selection", {}).get("gate_status", "unknown"),
        "lp_gate": "disabled",
        "operating_mode": "read_only",
        "hypothetical_only": True,
        "signing": False,
        "broadcast": False,
    }


def _load_watcher_config(config_path: Path) -> tuple[dict[str, Any], WatcherConfig]:
    """Load the scheduler contract and reject configurations that widen scope."""

    payload = _load_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError("watcher config must be an object")
    if payload.get("personal_trade_trigger_required") is not False:
        raise ValueError("watcher must not require a personal trade as its trigger")
    if payload.get("execution_scope") != "read_only_observation":
        raise ValueError("watcher execution_scope must be read_only_observation")
    fields = {
        name: payload[name]
        for name in (
            "observation_interval_seconds",
            "label_interval_seconds",
            "training_interval_seconds",
            "evaluation_interval_seconds",
            "max_training_seconds",
            "max_training_examples",
        )
        if name in payload
    }
    try:
        config = WatcherConfig(**fields)
    except TypeError as exc:
        raise ValueError(f"watcher config fields are invalid: {exc}") from exc
    return payload, config


def _watcher_tick(
    *,
    config_path: Path,
    state_db: Path,
    feedback_dir: Path,
    observed_at: str,
    personal_trade_count: int,
    observation_state: str,
    training_state: str,
    evaluation_state: str,
) -> dict[str, Any]:
    payload, config = _load_watcher_config(config_path)
    if personal_trade_count < 0:
        raise ValueError("personal_trade_count cannot be negative")
    config_hash = _config_hash(config_path)
    with FeedbackStore(feedback_dir) as feedback_store, LearningWatcher(
        state_db, config=config, config_identity=config_hash
    ) as watcher:
        snapshot = watcher.tick(
            observed_at=observed_at,
            feedback_store=feedback_store,
            personal_trade_count=personal_trade_count,
            observation_state=observation_state,
            training_state=training_state,
            evaluation_state=evaluation_state,
        )
    return {
        "status": snapshot.status,
        "recorded": True,
        "snapshot": snapshot.to_dict(),
        "config": str(config_path),
        "config_hash": config_hash,
        "state_db": str(state_db),
        "feedback_dir": str(feedback_dir),
        "personal_trade_trigger_required": payload["personal_trade_trigger_required"],
        "execution_scope": payload["execution_scope"],
        "signing": False,
        "broadcast": False,
    }


def _watcher_status(*, config_path: Path, state_db: Path) -> dict[str, Any]:
    payload, config = _load_watcher_config(config_path)
    config_hash = _config_hash(config_path)
    with LearningWatcher(state_db, config=config, config_identity=config_hash) as watcher:
        snapshot = watcher.snapshot()
        pending = watcher.pending_tasks()
    return {
        "status": snapshot.status if snapshot is not None else "not_started",
        "started": snapshot is not None,
        "snapshot": None if snapshot is None else snapshot.to_dict(),
        "pending_tasks": list(pending),
        "config": str(config_path),
        "config_hash": config_hash,
        "state_db": str(state_db),
        "personal_trade_trigger_required": payload["personal_trade_trigger_required"],
        "execution_scope": payload["execution_scope"],
        "signing": False,
        "broadcast": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="willfly", description="Read-only Willfly Observatory tools")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="validate local config without network access")
    doctor.add_argument("--config", type=Path, default=ROOT / "configs/sources/robinhood-chain-v0.1.json")
    doctor.add_argument("--strict", action="store_true", help="return non-zero while any P0 gate is open")

    fixture = subparsers.add_parser("fixture-check", help="validate provenance-tagged offline fixtures")
    fixture.add_argument("--manifest", type=Path, default=ROOT / "tests/fixtures/manifest.json")

    for name, help_text in (("capture", "perform a bounded read-only capture"), ("backfill", "perform a bounded read-only backfill")):
        operation = subparsers.add_parser(name, help=help_text)
        operation.add_argument("--config", type=Path, default=ROOT / "configs/sources/robinhood-chain-v0.1.json")
        operation.add_argument("--from-block", type=int, required=True)
        operation.add_argument("--to-block", type=int, required=True)
        operation.add_argument("--address", action="append", default=[])
        operation.add_argument("--store-dir", type=Path, default=ROOT / "data" / "observatory")
        operation.add_argument("--source", default=None, help="checkpoint namespace; defaults to the command name")
        operation.add_argument("--run-id", default=None, help="explicit run ID; defaults to a content hash")
        operation.add_argument("--page-size", type=int, default=2000, help="backfill page bound (max 2000)")
        operation.add_argument(
            "--dry-run",
            action="store_true",
            help="print a read-only plan without performing RPC reads or writes (exits 3)",
        )

    audit = subparsers.add_parser("audit", help="audit two raw-event JSON arrays")
    audit.add_argument("--expected", type=Path, required=True)
    audit.add_argument("--observed", type=Path, required=True)
    audit.add_argument("--provider-independent", action="store_true")

    export = subparsers.add_parser("export", help="export JSON records to Parquet")
    export.add_argument("--records", type=Path, required=True)
    export.add_argument("--output-dir", type=Path, required=True)
    export.add_argument("--dataset-name", required=True)

    materialize = subparsers.add_parser("materialize", help="persist a causal local Observatory projection from typed JSON")
    materialize.add_argument("--input", type=Path, required=True)
    materialize.add_argument("--as-of-time", required=True)
    materialize.add_argument("--store-dir", type=Path, default=ROOT / "data" / "observatory")
    materialize.add_argument("--source", default="observatory")
    materialize.add_argument("--replaces-snapshot-id", default=None)

    qualify = subparsers.add_parser(
        "qualify-anchor",
        help="persist one bounded ancestry anchor after two read-only RPC checks",
    )
    qualify.add_argument("--config", type=Path, default=ROOT / "configs/sources/robinhood-chain-v0.1.json")
    qualify.add_argument("--height", type=int, required=True)
    qualify.add_argument("--block-hash", required=True)
    qualify.add_argument("--independent-rpc-url", required=True)
    qualify.add_argument("--recorded-at", default=None, help="RFC-3339 observation time; defaults to now")
    qualify.add_argument("--store-dir", type=Path, default=ROOT / "data" / "observatory")
    qualify.add_argument("--source", default="capture", help="capture/backfill source namespace")
    qualify.add_argument("--address", action="append", default=[])
    qualify.add_argument("--supersedes-source", default=None)
    qualify.add_argument("--supersession-reason", default=None)

    serve = subparsers.add_parser("serve", help="serve local read-only inspection endpoints")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--store-dir", type=Path, default=ROOT / "data" / "observatory")
    serve.add_argument("--snapshot-id", default=None, help="load an immutable persisted Observatory projection")
    serve.add_argument(
        "--signals-file",
        type=Path,
        default=None,
        help="load a versioned read-only signal/training snapshot for the dashboard",
    )
    serve.add_argument("--check", action="store_true", help="validate binding without starting the loop")

    shadow = subparsers.add_parser("shadow", help="check or prepare the read-only hypothetical shadow loop")
    shadow.add_argument("--config", type=Path, default=ROOT / "configs/shadow/config.json")
    shadow.add_argument("--state-db", type=Path, default=ROOT / "tmp/shadow.sqlite")

    shadow_freeze = subparsers.add_parser(
        "shadow-freeze", help="freeze a prospective shadow config before its first observation"
    )
    shadow_freeze.add_argument("--config", type=Path, default=ROOT / "configs/shadow/config.json")
    shadow_freeze.add_argument("--start-time", required=True, help="timezone-aware RFC-3339 start time")

    shadow_run = subparsers.add_parser(
        "shadow-run", help="consume a controlled observation file through the hypothetical shadow loop"
    )
    shadow_run.add_argument("--config", type=Path, default=ROOT / "configs/shadow/config.json")
    shadow_run.add_argument("--state-db", type=Path, required=True)
    shadow_run.add_argument("--input", type=Path, required=True)
    shadow_run.add_argument("--fixed-entry-atomic", type=int, required=True)
    shadow_run.add_argument("--initial-cash-atomic", type=int, required=True)
    shadow_run.add_argument("--max-positions", type=int, default=None)

    operator = subparsers.add_parser("operator-check", help="check local read-only operator setup without network")
    operator.add_argument("--config", type=Path, default=ROOT / "configs/sources/robinhood-chain-v0.1.json")
    operator.add_argument("--shadow-config", type=Path, default=ROOT / "configs/shadow/config.json")
    operator.add_argument("--manifest", type=Path, default=ROOT / "tests/fixtures/manifest.json")

    watcher_tick = subparsers.add_parser("watcher-tick", help="record one read-only learning watcher heartbeat")
    watcher_tick.add_argument("--config", type=Path, default=ROOT / "configs/learning/watcher-v0.1.json")
    watcher_tick.add_argument("--state-db", type=Path, required=True)
    watcher_tick.add_argument("--feedback-dir", type=Path, required=True)
    watcher_tick.add_argument("--observed-at", required=True, help="timezone-aware RFC-3339 heartbeat time")
    watcher_tick.add_argument("--personal-trade-count", type=int, default=0)
    watcher_tick.add_argument(
        "--observation-state", choices=("running", "waiting", "degraded", "failed"), default="waiting"
    )
    watcher_tick.add_argument(
        "--training-state", choices=("running", "waiting", "degraded", "failed"), default="waiting"
    )
    watcher_tick.add_argument(
        "--evaluation-state", choices=("running", "waiting", "degraded", "failed"), default="waiting"
    )

    watcher_status = subparsers.add_parser("watcher-status", help="read persisted learning watcher state")
    watcher_status.add_argument("--config", type=Path, default=ROOT / "configs/learning/watcher-v0.1.json")
    watcher_status.add_argument("--state-db", type=Path, required=True)

    model_evaluate = subparsers.add_parser("model-evaluate", help="evaluate a candidate model against an active model")
    model_evaluate.add_argument("--points", type=Path, required=True, help="versioned prediction-point JSON bundle")
    model_evaluate.add_argument("--candidate-version", required=True)
    model_evaluate.add_argument("--active-version", required=True)
    model_evaluate.add_argument("--evaluated-at", required=True, help="timezone-aware RFC-3339 evaluation time")
    model_evaluate.add_argument("--dataset-hash", required=True)
    model_evaluate.add_argument("--minimum-forward-windows", type=int, default=2)
    model_evaluate.add_argument("--minimum-points-per-window", type=int, default=2)
    model_evaluate.add_argument("--registry", type=Path, default=None)
    model_evaluate.add_argument(
        "--record", action="store_true", help="record the evaluation in the supplied model registry; never promotes"
    )

    model_status = subparsers.add_parser("model-status", help="inspect the durable model registry")
    model_status.add_argument("--registry", type=Path, required=True)
    model_status.add_argument("--initial-active-version", required=True)

    feedback_import = subparsers.add_parser(
        "feedback-import", help="import typed read-only predictions and outcomes into the causal feedback store"
    )
    feedback_import.add_argument("--bundle", type=Path, required=True)
    feedback_import.add_argument("--feedback-dir", type=Path, required=True)
    feedback_import.add_argument("--as-of-time", required=True, help="timezone-aware RFC-3339 dataset cutoff")

    feedback_status = subparsers.add_parser("feedback-status", help="inspect the causal feedback store")
    feedback_status.add_argument("--feedback-dir", type=Path, required=True)
    feedback_status.add_argument("--as-of-time", required=True, help="timezone-aware RFC-3339 dataset cutoff")

    wallet_import = subparsers.add_parser(
        "wallet-import", help="import typed read-only public-wallet activities"
    )
    wallet_import.add_argument("--bundle", type=Path, required=True)
    wallet_import.add_argument("--wallet-dir", type=Path, required=True)

    wallet_status = subparsers.add_parser("wallet-status", help="derive a public-wallet observation and positions")
    wallet_status.add_argument("--wallet-dir", type=Path, required=True)
    wallet_status.add_argument("--wallet", required=True)
    wallet_status.add_argument("--as-of-time", required=True, help="timezone-aware event cutoff")
    wallet_status.add_argument("--arrival-cutoff", required=True, help="timezone-aware arrival cutoff")

    signal_build = subparsers.add_parser(
        "signal-build", help="build versioned research signals from explicit model outputs"
    )
    signal_build.add_argument("--input", type=Path, required=True, help="versioned model-output JSON bundle")
    signal_build.add_argument("--output", type=Path, default=None, help="optional signal snapshot output path")

    model_output = subparsers.add_parser(
        "model-output", help="export one connectome experiment metric as typed model outputs"
    )
    model_output.add_argument("--experiment-report", type=Path, required=True)
    model_output.add_argument("--templates", type=Path, required=True, help="prediction-template bundle")
    model_output.add_argument("--output", type=Path, required=True, help="model-output bundle destination")
    model_output.add_argument("--model-name", default="fly")
    model_output.add_argument("--model-id", required=True)
    model_output.add_argument("--model-version", required=True)
    model_output.add_argument("--run-ref", required=True)
    model_output.add_argument("--as-of-time", required=True, help="timezone-aware output cutoff")
    model_output.add_argument("--run-id", default=None, help="select one result from a multi-seed report")
    model_output.add_argument("--actions", type=Path, default=None, help="explicit prediction-to-action map")
    model_output.add_argument("--exit-kinds", type=Path, default=None, help="explicit exit-kind map")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = _doctor(args.config, args.strict)
        elif args.command == "fixture-check":
            result = _fixture_check(args.manifest)
        elif args.command in {"capture", "backfill"}:
            if args.from_block < 0 or args.to_block < args.from_block:
                raise ValueError("block range is invalid")
            if args.page_size <= 0 or args.page_size > 2000:
                raise ValueError("page_size must be between 1 and 2000")
            if args.dry_run:
                config = _load_json(args.config)
                result = _operation_plan(
                    args.command,
                    {
                        "config": str(args.config),
                        "from_block": args.from_block,
                        "to_block": args.to_block,
                        "addresses": args.address or config.get("contracts", {}),
                        "store_dir": str(args.store_dir),
                    },
                )
                result.update(status="plan_only", executed=False, reason="dry_run_requested")
            elif args.command == "capture":
                result = _execute_capture(
                    config_path=args.config,
                    from_block=args.from_block,
                    to_block=args.to_block,
                    addresses=list(args.address),
                    store_dir=args.store_dir,
                    run_id=args.run_id,
                    base_source=args.source or "capture",
                )
            else:
                result = _execute_backfill(
                    config_path=args.config,
                    from_block=args.from_block,
                    to_block=args.to_block,
                    addresses=list(args.address),
                    store_dir=args.store_dir,
                    run_id=args.run_id,
                    base_source=args.source or "backfill",
                    page_size=args.page_size,
                )
        elif args.command == "audit":
            result = _audit(args.expected, args.observed, args.provider_independent)
        elif args.command == "export":
            result = _export(args.records, args.output_dir, args.dataset_name)
        elif args.command == "materialize":
            result = _materialize(
                input_path=args.input,
                store_dir=args.store_dir,
                source=args.source,
                as_of_time=args.as_of_time,
                replaces_snapshot_id=args.replaces_snapshot_id,
            )
        elif args.command == "qualify-anchor":
            result = _qualify_anchor(
                config_path=args.config,
                store_dir=args.store_dir,
                base_source=args.source,
                addresses=list(args.address),
                height=args.height,
                block_hash=args.block_hash,
                independent_rpc_url=args.independent_rpc_url,
                recorded_at=args.recorded_at,
                supersedes_source=args.supersedes_source,
                supersession_reason=args.supersession_reason,
            )
        elif args.command == "shadow":
            result = _shadow_plan(args.config, args.state_db)
        elif args.command == "shadow-freeze":
            result = _shadow_freeze(args.config, args.start_time)
        elif args.command == "shadow-run":
            result = _execute_shadow_run(
                config_path=args.config,
                state_db=args.state_db,
                input_path=args.input,
                fixed_entry_atomic=args.fixed_entry_atomic,
                initial_cash_atomic=args.initial_cash_atomic,
                max_positions=args.max_positions,
            )
        elif args.command == "operator-check":
            result = _operator_check(args.config, args.shadow_config, args.manifest)
        elif args.command == "watcher-tick":
            result = _watcher_tick(
                config_path=args.config,
                state_db=args.state_db,
                feedback_dir=args.feedback_dir,
                observed_at=args.observed_at,
                personal_trade_count=args.personal_trade_count,
                observation_state=args.observation_state,
                training_state=args.training_state,
                evaluation_state=args.evaluation_state,
            )
        elif args.command == "watcher-status":
            result = _watcher_status(config_path=args.config, state_db=args.state_db)
        elif args.command == "model-evaluate":
            result = _evaluate_model(
                points_path=args.points,
                candidate_version=args.candidate_version,
                active_version=args.active_version,
                evaluated_at=args.evaluated_at,
                dataset_hash=args.dataset_hash,
                minimum_forward_windows=args.minimum_forward_windows,
                minimum_points_per_window=args.minimum_points_per_window,
                registry_path=args.registry,
                record=args.record,
            )
        elif args.command == "model-status":
            result = _model_status(registry_path=args.registry, initial_active_version=args.initial_active_version)
        elif args.command == "feedback-import":
            result = _feedback_import(
                bundle_path=args.bundle,
                feedback_dir=args.feedback_dir,
                as_of_time=args.as_of_time,
            )
        elif args.command == "feedback-status":
            result = _feedback_status(feedback_dir=args.feedback_dir, as_of_time=args.as_of_time)
        elif args.command == "wallet-import":
            result = _wallet_import(bundle_path=args.bundle, wallet_dir=args.wallet_dir)
        elif args.command == "wallet-status":
            result = _wallet_status(
                wallet_dir=args.wallet_dir,
                wallet=args.wallet,
                as_of_time=args.as_of_time,
                arrival_cutoff=args.arrival_cutoff,
            )
        elif args.command == "signal-build":
            result = _signal_build(input_path=args.input, output_path=args.output)
        elif args.command == "model-output":
            result = _model_output(
                experiment_report_path=args.experiment_report,
                templates_path=args.templates,
                output_path=args.output,
                model_name=args.model_name,
                model_id=args.model_id,
                model_version=args.model_version,
                run_ref=args.run_ref,
                as_of_time=args.as_of_time,
                run_id=args.run_id,
                actions_path=args.actions,
                exit_kinds_path=args.exit_kinds,
            )
        else:
            if args.snapshot_id:
                with RawBatchStore(args.store_dir) as snapshot_store:
                    read_store = ReadOnlyStore.from_persisted_snapshot(snapshot_store, args.snapshot_id)
            else:
                read_store = ReadOnlyStore()
            signal_file_hash = None
            if args.signals_file is not None:
                signal_values = _load_signal_store(args.signals_file)
                read_store = replace(read_store, **signal_values)
                signal_file_hash = _config_hash(args.signals_file)
            server = create_server(store=read_store, host=args.host, port=args.port)
            result = _operation_plan(
                "serve",
                {
                    "host": args.host,
                    "port": server.server_port,
                    "snapshot_id": args.snapshot_id,
                    "signals_file": None if args.signals_file is None else str(args.signals_file),
                    "signals_file_hash": signal_file_hash,
                    "signal_count": len(read_store.proposals),
                },
            )
            if not args.check:
                print(json.dumps(result, indent=2, sort_keys=True))
                server.serve_forever()
            server.server_close()
    except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": redact_error(exc)}, sort_keys=True))
        return 2
    except ExportUnavailable as exc:
        print(json.dumps({"status": "unavailable", "error": redact_error(exc)}, sort_keys=True))
        return 3
    except RuntimeError as exc:
        # RPC, backfill and storage failures must return nonzero without a traceback.
        print(json.dumps({"status": "error", "error": redact_error(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "fixture-check":
        return 0 if result["failed"] == 0 else 1
    if args.command == "doctor":
        return 0 if result["status"] == "ok" or not args.strict else 1
    if args.command == "audit":
        return 0 if result["status"] == "pass" else 1
    if args.command == "shadow":
        return 0 if result["status"] == "ready_hypothetical" else 1
    if args.command == "shadow-freeze":
        return 0 if result["status"] == "frozen" else 1
    if args.command == "shadow-run":
        return 0 if result["status"] == "completed" else 1
    if args.command == "operator-check":
        return 0 if result["status"] == "ready" else 1
    if args.command in {
        "watcher-tick",
        "watcher-status",
        "model-evaluate",
        "model-status",
        "feedback-import",
        "feedback-status",
        "wallet-import",
        "wallet-status",
        "signal-build",
    }:
        return 0
    if args.command in {"capture", "backfill"}:
        if result.get("status") == "plan_only":
            return 3  # A non-executed plan cannot be mistaken for successful capture.
        return 0 if result.get("status") == "executed" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
