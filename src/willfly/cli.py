"""Small offline-first command line surface for P0."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from willfly import __version__
from willfly.domain import (
    Launch,
    Observation,
    PoolIdentity,
    RawEvent,
    TradeEvidence,
    VendorAssessment,
    WalletCohort,
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
from willfly.features.projections import LifecycleRevision, materialize_observatory_projection


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
        from willfly.shadow.config import validate_frozen_shadow_config
        validate_frozen_shadow_config(config)
        result.update(
            {
                "status": "blocked",
                "reason": "shadow_runtime_not_integrated",
                "observation_window": "not_started",
            }
        )
    return result


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
    serve.add_argument("--check", action="store_true", help="validate binding without starting the loop")

    shadow = subparsers.add_parser("shadow", help="check or prepare the read-only hypothetical shadow loop")
    shadow.add_argument("--config", type=Path, default=ROOT / "configs/shadow/config.json")
    shadow.add_argument("--state-db", type=Path, default=ROOT / "tmp/shadow.sqlite")
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
        else:
            if args.snapshot_id:
                with RawBatchStore(args.store_dir) as snapshot_store:
                    read_store = ReadOnlyStore.from_persisted_snapshot(snapshot_store, args.snapshot_id)
            else:
                read_store = ReadOnlyStore()
            server = create_server(store=read_store, host=args.host, port=args.port)
            result = _operation_plan(
                "serve",
                {"host": args.host, "port": server.server_port, "snapshot_id": args.snapshot_id},
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
    if args.command in {"capture", "backfill"}:
        if result.get("status") == "plan_only":
            return 3  # A non-executed plan cannot be mistaken for successful capture.
        return 0 if result.get("status") == "executed" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
