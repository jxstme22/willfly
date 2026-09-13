import json
import time

import pytest

from willfly.adapters.lpagent import capability_matrix
from willfly.adapters.rhtrenches import normalize_scanner_claim
from willfly.evaluation.contamination import audit_claim_times
from willfly.evaluation.factorial import factorial_hash, review_factorial, run_factorial
from willfly.features.llm import LLMBudget, LLMBudgetLedger, bounded_enrich
from willfly.features.lp_behavior import LPObservation, causal_lp_observations
from willfly.features.text_schema import TextClaim
from willfly.ui.decisions.inspect import render_decision_inspection


def test_optional_sources_are_explicitly_unavailable_and_lp_cutoff_is_causal():
    assert all(capability.status == "unavailable" for capability in capability_matrix())
    observation = LPObservation("wallet", "pool", "position", "open", "2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z", 10, "1", "2", -10, 10, "cohort-before-window", "lp:1")
    assert causal_lp_observations([observation], arrival_cutoff="2026-01-01T00:00:01Z") == ()
    assert normalize_scanner_claim("rhtrenches", "token", {"reason_flags": ["claim"], "status": "stale"}, retrieved_time="2026-01-01T00:00:03Z").status == "stale"


def test_llm_fallback_and_schema_checked_output_never_block_numeric_path():
    fallback = bounded_enrich("untrusted", call=None, budget=LLMBudget(1, 20), model_version="none", prompt_version="p1")
    assert fallback.fallback_used is True
    accepted = bounded_enrich("text span", call=lambda _: json.dumps([{"claim_type": "risk", "evidence": "span"}]), budget=LLMBudget(1, 20), model_version="m1", prompt_version="p1")
    assert accepted.status == "accepted"
    invalid = bounded_enrich("text span", call=lambda _: "not-json", budget=LLMBudget(1, 20), model_version="m1", prompt_version="p1")
    assert invalid.fallback_used is True
    attempts = iter(["not-json", json.dumps([{"claim_type": "risk", "evidence": "span"}])])
    cache = {}
    retried = bounded_enrich("retry span", call=lambda _: next(attempts), budget=LLMBudget(2, 20), model_version="m1", prompt_version="p1", cache=cache, max_retries=1)
    assert retried.status == "accepted" and retried.request_count == 2
    cached = bounded_enrich("retry span", call=lambda _: "not-json", budget=LLMBudget(1, 20), model_version="m1", prompt_version="p1", cache=cache)
    assert cached.status == "accepted" and cached.request_count == 2


def test_llm_deadline_and_persistent_cumulative_budget_are_enforced(tmp_path):
    def slow(_: str) -> str:
        time.sleep(0.05)
        return json.dumps([])

    timed_out = bounded_enrich(
        "text span",
        call=slow,
        budget=LLMBudget(1, 20),
        model_version="m1",
        prompt_version="deadline",
        deadline_seconds=0.001,
    )
    assert timed_out.fallback_used is True
    assert timed_out.reason == "TimeoutError"
    ledger_path = tmp_path / "llm-usage.json"
    ledger = LLMBudgetLedger(2, 4, path=ledger_path)
    accepted = bounded_enrich(
        "text span",
        call=lambda _: json.dumps([{"claim_type": "risk", "evidence": "span"}]),
        budget=LLMBudget(2, 20),
        model_version="m1",
        prompt_version="budget-1",
        ledger=ledger,
    )
    assert accepted.status == "accepted"
    assert ledger.requests == 1 and ledger.tokens > 0
    restored = LLMBudgetLedger(2, 4, path=ledger_path)
    exhausted = bounded_enrich(
        "another text",
        call=lambda _: json.dumps([]),
        budget=LLMBudget(2, 20),
        model_version="m1",
        prompt_version="budget-2",
        ledger=restored,
    )
    assert exhausted.fallback_used is True
    assert exhausted.reason == "budget_exhausted"


def test_contamination_factorial_and_decision_evidence():
    claim = TextClaim("c1", "token", "risk", "text", "https://source", "span", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", 5000, ())
    audit = audit_claim_times([claim], feature_cutoff="2026-01-01T00:00:01Z")
    assert audit.usable_claim_ids == ("c1",)
    late = TextClaim("c2", "token", "risk", "text", "https://source", "span", "2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z", 5000, ())
    assert audit_claim_times([late], feature_cutoff="2026-01-01T00:00:01Z").usable_claim_ids == ()
    cells = run_factorial(
        architectures=["ordinary", "fly"],
        evaluator=lambda architecture, lp, text: (1, 2, 3, "pass"),
        dataset_hash="d" * 64,
        config_hash="c" * 64,
        evidence_refs=("fixture:factorial",),
    )
    assert len(cells) == 8
    assert len(factorial_hash(cells)) == 64
    assert review_factorial(cells, architectures=["ordinary", "fly"], dataset_hash="d" * 64, config_hash="c" * 64).state == "pass"
    assert "Decision evidence" in render_decision_inspection({"action": "watch", "reason": "unknown"})
