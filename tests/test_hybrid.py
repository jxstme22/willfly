import json

import pytest

from willfly.adapters.lpagent import capability_matrix
from willfly.adapters.rhtrenches import normalize_scanner_claim
from willfly.evaluation.contamination import audit_claim_times
from willfly.evaluation.factorial import run_factorial
from willfly.features.llm import LLMBudget, bounded_enrich
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


def test_contamination_factorial_and_decision_evidence():
    claim = TextClaim("c1", "token", "risk", "text", "https://source", "span", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z", 5000, ())
    audit = audit_claim_times([claim], feature_cutoff="2026-01-01T00:00:01Z")
    assert audit.usable_claim_ids == ("c1",)
    late = TextClaim("c2", "token", "risk", "text", "https://source", "span", "2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z", 5000, ())
    assert audit_claim_times([late], feature_cutoff="2026-01-01T00:00:01Z").usable_claim_ids == ()
    cells = run_factorial(architectures=["ordinary", "fly"], evaluator=lambda architecture, lp, text: (1, 2, 3, "inconclusive"))
    assert len(cells) == 8
    assert "Decision evidence" in render_decision_inspection({"action": "watch", "reason": "unknown"})
