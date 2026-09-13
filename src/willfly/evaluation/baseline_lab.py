"""Reproducible, fixed-policy laboratory for ordinary trading baselines."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable, Mapping

from willfly.evaluation.metrics import EpisodeResult, MetricReport, calculate_metrics
from willfly.policies.baselines import (
    BaselineConfig,
    BaselineDecision,
    MarketObservation,
    confirmation_momentum,
    fixed_horizon_hold,
    idle_cash,
    tracked_wallet_follow,
    verified_flow_filter,
)


BaselinePolicy = Callable[[MarketObservation, BaselineConfig], BaselineDecision]


@dataclass(frozen=True)
class BaselineCase:
    """One chronologically ordered opportunity with a precomputed replay result.

    ``net_return_if_enter_bps`` must come from the same execution-aware replay
    for every policy. A policy decides whether to consume that result; this
    module never replaces a missing or failed execution with a leader fill.
    """

    case_id: str
    block_id: str
    observation: MarketObservation
    net_return_if_enter_bps: int
    benchmark_return_bps: int = 0
    failed_if_enter: bool = False
    turnover_if_enter_bps: int = 0
    exposure_if_enter_bps: int = 0

    def __post_init__(self) -> None:
        if not self.case_id or not self.block_id:
            raise ValueError("baseline case identity is required")
        if not isinstance(self.net_return_if_enter_bps, int) or isinstance(self.net_return_if_enter_bps, bool):
            raise ValueError("baseline returns must be integer basis points")
        if min(self.turnover_if_enter_bps, self.exposure_if_enter_bps) < 0:
            raise ValueError("baseline diagnostics cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "block_id": self.block_id,
            "observation": self.observation.__dict__.copy(),
            "net_return_if_enter_bps": self.net_return_if_enter_bps,
            "benchmark_return_bps": self.benchmark_return_bps,
            "failed_if_enter": self.failed_if_enter,
            "turnover_if_enter_bps": self.turnover_if_enter_bps,
            "exposure_if_enter_bps": self.exposure_if_enter_bps,
        }


@dataclass(frozen=True)
class BaselineLabConfig:
    capital_atomic: int = 100_000
    policy_config: BaselineConfig = BaselineConfig()
    bootstrap_replicates: int = 0
    seed: int = 0
    minimum_blocks: int = 4
    code_version: str = "baseline-lab-v0.1"

    def __post_init__(self) -> None:
        if self.capital_atomic <= 0 or self.bootstrap_replicates < 0 or self.minimum_blocks < 1 or not self.code_version:
            raise ValueError("baseline laboratory config is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "capital_atomic": self.capital_atomic,
            "policy_config": self.policy_config.__dict__.copy(),
            "bootstrap_replicates": self.bootstrap_replicates,
            "seed": self.seed,
            "minimum_blocks": self.minimum_blocks,
            "code_version": self.code_version,
        }


@dataclass(frozen=True)
class BaselineRun:
    policy: str
    case_id: str
    decision: BaselineDecision
    episode: EpisodeResult

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "case_id": self.case_id,
            "decision": self.decision.__dict__.copy(),
            "episode": self.episode.__dict__.copy(),
        }


@dataclass(frozen=True)
class BaselineLabResult:
    dataset_hash: str
    config_hash: str
    code_hash: str
    reports: Mapping[str, MetricReport]
    runs: tuple[BaselineRun, ...]
    policy_names: tuple[str, ...]
    baseline_selection: str | None
    evidence_state: str

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "config_hash": self.config_hash,
            "code_hash": self.code_hash,
            "reports": {name: report.__dict__.copy() for name, report in self.reports.items()},
            "runs": [run.to_dict() for run in self.runs],
            "policy_names": list(self.policy_names),
            "baseline_selection": self.baseline_selection,
            "evidence_state": self.evidence_state,
        }


def default_baseline_policies() -> dict[str, BaselinePolicy]:
    return {
        "confirmation_momentum": confirmation_momentum,
        "fixed_horizon_hold": fixed_horizon_hold,
        "idle_cash": idle_cash,
        "tracked_wallet_follow": tracked_wallet_follow,
        "verified_flow_filter": verified_flow_filter,
    }


def run_baseline_laboratory(
    cases: Iterable[BaselineCase],
    *,
    policies: Mapping[str, BaselinePolicy] | None = None,
    config: BaselineLabConfig = BaselineLabConfig(),
) -> BaselineLabResult:
    """Run every declared policy over the same causal cases and replay results."""

    ordered_cases = tuple(sorted(cases, key=lambda case: (case.observation.as_of_time, case.case_id)))
    if not ordered_cases:
        raise ValueError("baseline laboratory requires at least one case")
    registered = dict(policies or default_baseline_policies())
    if not registered or any(not name or not callable(policy) for name, policy in registered.items()):
        raise ValueError("baseline policies must be named callables")
    policy_names = tuple(sorted(registered))
    reports: dict[str, MetricReport] = {}
    runs: list[BaselineRun] = []
    for policy_name in policy_names:
        policy = registered[policy_name]
        episodes: list[EpisodeResult] = []
        equity = [config.capital_atomic]
        current_equity = config.capital_atomic
        for case in ordered_cases:
            decision = policy(case.observation, config.policy_config)
            entered = decision.action == "enter"
            episode = EpisodeResult(
                f"{policy_name}:{case.case_id}",
                case.block_id,
                case.net_return_if_enter_bps if entered else 0,
                case.benchmark_return_bps,
                case.failed_if_enter if entered else False,
                case.turnover_if_enter_bps if entered else 0,
                case.exposure_if_enter_bps if entered else 0,
            )
            episodes.append(episode)
            runs.append(BaselineRun(policy_name, case.case_id, decision, episode))
            current_equity = max(0, current_equity + current_equity * episode.net_return_bps // 10_000)
            equity.append(current_equity)
        reports[policy_name] = calculate_metrics(
            episodes,
            equity_curve_atomic=equity,
            bootstrap_replicates=config.bootstrap_replicates,
            seed=config.seed,
            min_blocks=config.minimum_blocks,
        )
    evidence_state = "pass" if all(report.inference_state == "pass" for report in reports.values()) else "inconclusive"
    return BaselineLabResult(
        _hash_json([case.to_dict() for case in ordered_cases]),
        _hash_json(config.to_dict()),
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reports,
        tuple(runs),
        policy_names,
        None,
        evidence_state,
    )


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


__all__ = [
    "BaselineCase",
    "BaselineLabConfig",
    "BaselineLabResult",
    "BaselinePolicy",
    "BaselineRun",
    "default_baseline_policies",
    "run_baseline_laboratory",
]
