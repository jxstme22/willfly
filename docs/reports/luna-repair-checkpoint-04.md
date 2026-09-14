# Luna repair checkpoint — post-baseline semantic closure

Date: 14 September 2026

Status: `REPAIRED_PENDING_INDEPENDENT_RECHECK`

This loop repaired the five concrete regressions identified after commit
`63a02ce` while preserving the existing research-only, read-only and
no-signing/no-broadcast boundaries.

## Repairs

- Rolling labels now recompute the exact runtime filter-bound checkpoint
  identity, including deduplicated ABI and event-family inputs, and reject an
  observation artifact from a different namespace before building labels.
- Market-feedback bundles now bind one hash over every non-provenance field in
  addition to the six component hashes. Training recomputes both the component
  hashes and the bundle hash, so safety, lineage, split-policy and canonical
  metadata mutations fail closed.
- Direct `finish_task(..., status="completed")` writes completion metadata and
  the last snapshot inside the same SQLite transaction as the task update;
  callback-driven completion uses the same path and restart recovery is tested.
- The WSL installer now migrates quoted or unquoted legacy placeholders,
  rebinds training/evaluation/registry paths, materializes a runtime-bound
  pipeline config under the standard runtime tree, and rejects unsupported
  XDG/config/env/runtime overrides instead of generating mismatched units.
- Dashboard model-registry reads are SQLite read-only and retain the last good
  state when the registry disappears. First paint binds the attached signal
  cutoff, and the browser refresh updates status classes, quality state and
  refresh time from the catalog.

## Evidence

Focused repair checks pass for pipeline, corpus, watcher, WSL packaging, API,
CLI and UI tests. The complete suite collects 297 tests, with 293 passing and
four loopback tests skipped by the managed sandbox. The WSL offline smoke
passes all 16 fixture checks. Planning render/check, source-manifest
validation, brain-release validation, shell syntax, compileall and
`git diff --check` pass.

The verified filter identity probe matches in both paths:

`pipeline-live-readonly:4663:6707856a8275fbb4`

The release remains `research_release_only`. Live history completeness,
timed observation/shadow windows, forward evaluation/calibration, economic
spot and LP qualification, causal generalization, biological validity and
production execution remain open gates. No WSL/systemd uptime evidence is
claimed; the checks cover packaging and offline smoke only.

The coordinator should independently re-run this checkpoint and inspect the
provenance, installer and dashboard diffs before marking the repair stage
accepted.
