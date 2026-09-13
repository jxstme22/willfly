# Luna repair checkpoint — DeepSeek ancestry audit

Date: 14 September 2026

Status: `THIRD_REPAIR_IMPLEMENTED_PENDING_COORDINATOR_RECHECK`

This checkpoint covers only DS-01 through DS-06, the reported whitespace
failure, the coordinator's R1/R2 repair review and the R3-R5 repair review. No
feature-build loops or trading execution scope were started.

## Repairs

- DS-01: anchor qualification is now fail-closed. Only a validated block-0
  genesis invariant or a structured independent-header identity check can
  qualify a bounded projection. Runtime-code/deployment labels are not accepted
  as ancestry proof; explicit unverified declarations return `unverified`.
  Reaching the declared anchor is required before resolution.
- DS-02: canonicalization records its proven height interval. Events before the
  anchor or after the selected tip remain unresolved/out of scope; only a
  competing block inside the proven interval is orphaned. The distinction is
  persisted and reproduced after reopening the store.
- DS-03: capture and backfill validate chain, source, configuration and anchor
  evidence before storing a trusted anchor or publishing a capture page. A
  rejected candidate does not poison the source namespace; a corrected retry is
  allowed. Unverified anchors cannot be persisted as trusted state.
- DS-04: backfill now uses the same genesis qualification path as capture,
  including completed/no-op restart state from persisted headers.
- DS-05: `willfly qualify-anchor` now performs `eth_chainId` and
  `eth_getBlockByNumber` against the configured primary RPC and a distinct
  explicitly supplied independent RPC. It records both headers and provenance,
  refuses old offline evidence or mismatched endpoints, and labels finality as
  unverified. It is read-only with respect to the chain; it never signs or
  broadcasts.
- DS-06: anchor import and stored-anchor restoration reject booleans, fractional
  values, null text, string-shaped evidence and unknown fields instead of
  coercing them into trusted identities.
- R1: independent-source qualification is backed by performed read-only RPC
  calls and a strict evidence schema; endpoint independence remains an
  operator trust assumption rather than a cryptographic claim.
- R2: backfill reconciliation selects exactly one tip header fetched in the
  current run, reports an unavailable/conflicting tip instead of choosing a
  stale stored fork, and revalidates the tip during no-op resume.
- Recovery: a boundary-crossing fork is handled by a new source namespace with
  an immutable supersession link; the old source and its checkpoint remain
  preserved.
- R3: resumed backfills probe the current target and acknowledged cursor
  boundary before inheriting a checkpoint. A changed lineage invalidates the
  derived projection, resets the filter-bound cursor and replays the bounded
  requested range. Raw branch evidence remains append-only; unavailable probes
  and failed replays leave `needs_repair` without completed coverage.
- R4: resolution is now a positive invariant: only an explicitly `qualified`
  anchor that is reached by a gap-free parent walk with a proven interval can
  resolve. Nested evidence numbers, chain IDs, hashes, parents and shapes are
  checked without boolean/fractional coercion.
- R5: endpoint references in anchor evidence, run manifests, CLI output and
  error text are origin-only and omit userinfo, path, query and credentials;
  configured URLs remain transport-only.
- Whitespace: the extra EOF blank line in
  `tests/test_header_reconciliation.py` was removed; `git diff --check` passes.

## Evidence

The regression suite covers unverified and false-genesis anchors, malformed
structured evidence, unreached anchors, proven-range orphaning, persistence and
restart, invalid capture followed by corrected retry, capture/backfill genesis
parity, strict import values, a real two-RPC subprocess qualification path,
fresh-tip replacement, no-op tip revalidation, tip outage, partial replay,
replay failure, strict nested evidence, source requalification recovery and
credential-canary redaction across CLI/manifests/errors.
The diagnostic probe at
`docs/reports/deepseek-anchor-audit-probes.py` now reports the repaired states
instead of reproducing the old poisoning behavior.

Verification: sandbox full suite `150 passed, 2 skipped` (the two loopback
tests are sandbox-restricted); the skipped real two-RPC CLI fixture and local
inspection API test both passed in the permitted local-socket run, so all 152
collected tests were exercised. The coordinator reproduction reports the
replacement log captured, canonical checkpoint state, strict nested evidence
rejection and unknown-state rejection. Planning, compileall and diff checks
also pass.

The coordinator must independently re-run the focused and full checks and
review the source policy before G0 is marked complete. Live canonical-source,
archive, 72-hour, 14-day, biological, economic and model gates remain open.
