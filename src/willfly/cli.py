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

    for name, help_text in (("capture", "prepare a bounded read-only capture"), ("backfill", "prepare a bounded read-only backfill")):
        operation = subparsers.add_parser(name, help=help_text)
        operation.add_argument("--config", type=Path, default=ROOT / "configs/sources/robinhood-chain-v0.1.json")
        operation.add_argument("--from-block", type=int, required=True)
        operation.add_argument("--to-block", type=int, required=True)
        operation.add_argument("--address", action="append", default=[])

    audit = subparsers.add_parser("audit", help="audit two raw-event JSON arrays")
    audit.add_argument("--expected", type=Path, required=True)
    audit.add_argument("--observed", type=Path, required=True)
    audit.add_argument("--provider-independent", action="store_true")

    export = subparsers.add_parser("export", help="export JSON records to Parquet")
    export.add_argument("--records", type=Path, required=True)
    export.add_argument("--output-dir", type=Path, required=True)
    export.add_argument("--dataset-name", required=True)

    serve = subparsers.add_parser("serve", help="serve local read-only inspection endpoints")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
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
            config = _load_json(args.config)
            result = _operation_plan(
                args.command,
                {
                    "config": str(args.config),
                    "from_block": args.from_block,
                    "to_block": args.to_block,
                    "addresses": args.address or config.get("contracts", {}),
                },
            )
            result.update(status="plan_only", executed=False, reason="collector_cli_not_integrated")
        elif args.command == "audit":
            result = _audit(args.expected, args.observed, args.provider_independent)
        elif args.command == "export":
            result = _export(args.records, args.output_dir, args.dataset_name)
        elif args.command == "shadow":
            result = _shadow_plan(args.config, args.state_db)
        else:
            server = create_server(store=ReadOnlyStore(), host=args.host, port=args.port)
            result = _operation_plan("serve", {"host": args.host, "port": server.server_port})
            if not args.check:
                print(json.dumps(result, indent=2, sort_keys=True))
                server.serve_forever()
            server.server_close()
    except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    except ExportUnavailable as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, sort_keys=True))
        return 3
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
        return 3  # A non-executed plan cannot be mistaken for successful capture.
    return 0


if __name__ == "__main__":
    sys.exit(main())
