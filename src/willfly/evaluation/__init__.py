"""Evaluation and evidence-audit helpers."""

from willfly.evaluation.coverage import CoverageAudit, audit_coverage
from willfly.evaluation.splits import LabelReference, SplitExclusion, SplitManifest, SplitWindow, build_split_manifest
from willfly.evaluation.replay_audit import CostScenario, ReplayAudit, run_replay_audit
from willfly.evaluation.replay_bundle import ReplayBundle, write_replay_bundle
from willfly.evaluation.runs import BudgetExceeded, ExperimentRun, RunTracker
from willfly.evaluation.metrics import EpisodeResult, MetricReport, calculate_metrics, paired_block_bootstrap
from willfly.evaluation.contamination import ContaminationAudit, audit_claim_times
from willfly.evaluation.factorial import FactorialCell, run_factorial
from willfly.evaluation.lp_stress import LPStressResult, LPStressScenario, stress_lp_scenarios
from willfly.evaluation.shadow import ShadowReconciliation, ShadowWindowAudit, ShadowWindowRequirements, audit_shadow_window, reconcile_shadow
from willfly.evaluation.scenario_runner import ScenarioOutcome, run_quote_stress_scenarios
from willfly.evaluation.baseline_lab import (
    BaselineCase,
    BaselineLabConfig,
    BaselineLabResult,
    BaselinePolicy,
    BaselineRun,
    default_baseline_policies,
    run_baseline_laboratory,
)

__all__ = [
    "CoverageAudit",
    "ContaminationAudit",
    "CostScenario",
    "BudgetExceeded",
    "EpisodeResult",
    "ExperimentRun",
    "FactorialCell",
    "LabelReference",
    "SplitExclusion",
    "SplitManifest",
    "SplitWindow",
    "ShadowReconciliation",
    "ShadowWindowAudit",
    "ShadowWindowRequirements",
    "ReplayAudit",
    "ReplayBundle",
    "RunTracker",
    "MetricReport",
    "LPStressResult",
    "LPStressScenario",
    "audit_coverage",
    "audit_claim_times",
    "build_split_manifest",
    "run_replay_audit",
    "audit_shadow_window",
    "reconcile_shadow",
    "write_replay_bundle",
    "calculate_metrics",
    "paired_block_bootstrap",
    "run_factorial",
    "stress_lp_scenarios",
]
from willfly.evaluation.promotion import CandidateEvaluation, ModelRegistry, PredictionPoint, WindowScore, evaluate_candidate

__all__ = [
    "CoverageAudit",
    "ContaminationAudit",
    "CostScenario",
    "BudgetExceeded",
    "EpisodeResult",
    "ExperimentRun",
    "FactorialCell",
    "LabelReference",
    "SplitExclusion",
    "SplitManifest",
    "SplitWindow",
    "ShadowReconciliation",
    "ShadowWindowAudit",
    "ShadowWindowRequirements",
    "ReplayAudit",
    "ReplayBundle",
    "RunTracker",
    "MetricReport",
    "LPStressResult",
    "LPStressScenario",
    "audit_coverage",
    "audit_claim_times",
    "build_split_manifest",
    "run_replay_audit",
    "audit_shadow_window",
    "reconcile_shadow",
    "write_replay_bundle",
    "calculate_metrics",
    "paired_block_bootstrap",
    "run_factorial",
    "stress_lp_scenarios",
    "CandidateEvaluation",
    "ModelRegistry",
    "PredictionPoint",
    "WindowScore",
    "evaluate_candidate",
    "ScenarioOutcome",
    "run_quote_stress_scenarios",
    "BaselineCase",
    "BaselineLabConfig",
    "BaselineLabResult",
    "BaselinePolicy",
    "BaselineRun",
    "default_baseline_policies",
    "run_baseline_laboratory",
]
