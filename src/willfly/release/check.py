"""Honest capability matrix for the manual-execution brain product."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Mapping

from willfly.domain import default_signal_contract


@dataclass(frozen=True)
class BrainReleaseReport:
    status: str
    capabilities: Mapping[str, str]
    implementation_tasks: Mapping[str, str]
    open_gates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "brain-release-report.v0.1",
            "status": self.status,
            "capabilities": dict(self.capabilities),
            "implementation_tasks": dict(self.implementation_tasks),
            "open_gates": list(self.open_gates),
        }


def build_brain_release_report(root: str | Path) -> BrainReleaseReport:
    """Read checked-in evidence and return a research-only capability matrix."""

    repository = Path(root)
    contract = default_signal_contract()
    manifest = json.loads((repository / "configs/connectome/male-cns-v1.0.json").read_text(encoding="utf-8"))
    catalogue = json.loads((repository / "docs/brain-product-tasks.json").read_text(encoding="utf-8"))
    task_status = {task["id"]: task["status"] for task in catalogue["tasks"]}
    if contract.execution_scope != "manual_only" or contract.signing_enabled or contract.funding_enabled:
        raise ValueError("brain release contract is not manual-only")
    capabilities = {
        "signal_contracts": "available_manual_only",
        "connectome_source": "verified_bounded_subset" if manifest.get("status") == "verified" else "unavailable",
        "connectome_training": "mechanics_available_live_labelled_run_open",
        "signal_inbox": "available_research_only_until_model_and_economic_gates",
        "public_wallet_observer": "available_fixture_verified_live_coverage_open",
        "manual_feedback": "available_fixture_verified_live_demo_open",
        "spot_recommendations": "research_only_economic_gate_open",
        "lp_recommendations": "research_only_lp_accounting_gate_open",
        "automatic_execution": "disabled",
        "model_promotion": "guarded_forward_evaluation_required",
        "continuous_learning": "scheduler_available_live_24_7_evidence_open",
    }
    open_gates = (
        "live labelled MaleCNS training and held-out comparison",
        "real forward evaluation and calibration",
        "live public-wallet coverage and manual-feedback demonstration",
        "spot quote/ledger economic qualification",
        "LP exact accounting and independent benefit evidence",
        "real 24/7 zero-personal-trade observation-to-evaluation interval",
        "M1-07/M3-03 timed acceptance windows",
    )
    return BrainReleaseReport("research_release_only", capabilities, task_status, open_gates)


__all__ = ["BrainReleaseReport", "build_brain_release_report"]
