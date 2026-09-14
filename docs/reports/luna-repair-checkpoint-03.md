# Luna repair checkpoint — operator handoff audit closure

Date: 14 September 2026

Status: `REPAIRED_PENDING_INDEPENDENT_RECHECK`

This loop addressed the coordinator's concrete handoff findings without
opening signing, funding, paid-provider, automatic-trading or new-agent scope.

## Repairs

- Rolling observation idempotency now binds the due tick, provider manifest
  identity and filter-derived checkpoint namespace. A retry of one tick is
  reusable, while a later tick cannot reuse the first completed observation.
- Label construction reads the exact `checkpoint_source` from the observation
  artifact. The filter-bound namespace is carried into the corpus and all
  downstream pipeline provenance instead of falling back to a bare config
  source.
- `compare_lp_modes` requires a non-null, qualifying `LPEvidence` object before
  LP metrics can be enabled. A status string alone remains disabled.
- The WSL installer now materializes pipeline config/state and signal paths;
  the rolling pipeline accepts the explicit `WILLFLY_CAPTURE_START_BLOCK`
  bootstrap inherited by `willflyctl start pipeline`. Generated env output has
  no `/path/to` or `/home/user` placeholders.
- Dashboard startup tolerates an absent or malformed signal alias with an
  explicit waiting state, and a transient later read keeps the last good
  snapshot. The API catalog now refreshes as-of, canonical count, training and
  model-registry state together; the browser updates those DOM fields from
  `/catalog`.
- Watcher callback completion records the last completed stage, task and time
  in durable state and restores those fields after restart.
- Market feedback corpus loading recomputes event, observation, prediction,
  outcome, feature and partition content hashes. Mutated corpus content or
  mismatched separately supplied maps is rejected before training.

## Evidence

Focused checks cover the new behavior in `tests/test_pipeline.py`,
`tests/test_lp.py`, `tests/test_watcher.py`, `tests/test_market_feedback.py`,
`tests/test_cli.py`, `tests/test_api.py`, `tests/test_ui.py` and
`tests/test_wsl_packaging.py`. The source-manifest and brain-release checks,
planning render/check, shell syntax, compileall, diff check and WSL2 offline
smoke all pass. The generated WSL env was also exercised in an isolated temp
runtime and contained no template placeholders.

The full suite passes: 291 tests collected, 287 passed and four sandbox
loopback skips. Those skips are local
environment restrictions, not asserted product behavior; the loopback cases
remain explicit in the test report. Live source completeness, provider
comparison, 72-hour observation, 14-day shadow, economic qualification,
causal generalization, biological validity and production execution remain
open gates.

The coordinator should independently re-run the focused/full checks, inspect
the provenance and UI diffs, and decide whether this checkpoint closes the
handoff findings.
