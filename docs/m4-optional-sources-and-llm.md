# M4 optional-source and text-enrichment checkpoint

Status: M4-03 and M4-04 are `IN_PROGRESS` as of 2026-09-14.

The optional LP Agent, RH Trenches and Mezzanine boundaries expose explicit
`unavailable` capabilities until an official supported production endpoint,
terms and authentication scope are verified. Vendor-shaped payloads can be
normalized for review, but they cannot become native recorder truth or silently
replace the native source. Native-only operation remains valid.

LLM enrichment is a bounded annotation path behind the numeric features. It
requires literal source-span evidence and a strict claim type schema; malformed,
hostile or unavailable output falls back without blocking the numeric path.
`LLMBudgetLedger` persists cumulative request, token, retry and cache-hit usage
for a run. Optional deadlines execute callbacks on daemon workers and return a
bounded fallback on timeout, so a provider callback cannot hold the decision
loop indefinitely. Budget and cache provenance remain separate from market
outcomes.

Fixture evidence covers unavailable adapter states, source-span validation,
timeout fallback, persistent cumulative budget exhaustion, retries, cache hits
and contamination cutoffs. No optional provider is operational, and no
historical text or LLM claim is treated as available before its recorded cutoff.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_hybrid.py tests/test_features.py
```

