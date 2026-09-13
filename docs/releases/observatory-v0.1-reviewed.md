# Observatory v0.1 reviewed checkpoint

Status: `PARTIAL_INCONCLUSIVE` — draft, 2026-09-14.

The read-only observatory has durable bounded capture/backfill, filter-bound
checkpoints, header/fork reconciliation, route attribution, causal projections,
lossless export, local GET-only inspection routes and the dashboard. Synthetic
recovery fixtures and bounded live probes are recorded separately from
acceptance.

The v0.1 acceptance bundle is not closed. A real 72-hour bounded capture,
provider-independent discovery recall, complete non-graduate launch coverage,
archive limits, receipt delay and independent replay manifest have not been
measured as one elapsed observation interval. The configured public RPC and
optional vendor sources do not authorize replacing those gates with synthetic
timestamps or browser observations.

Current decision: continue native read-only collection and recovery testing;
keep launch discovery, economic claims and downstream timed gates
inconclusive. No signing, funding or automatic execution is enabled.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_coverage.py tests/test_quality.py tests/test_capture_runner.py tests/test_api.py
```

