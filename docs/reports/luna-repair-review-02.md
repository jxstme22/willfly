# Coordinator repair review 02

14 September 2026. **Changes requested; G0 remains open.** Reviewed Luna's second repair while the task was idle. Independent verification: 143 passed and two sandbox skips; both skipped localhost tests passed in a separate permitted run, so 145 tests were exercised successfully. Planning, compileall and whitespace checks pass. The actual primary/independent RPC qualification path now performs reads; the old uploaded-JSON qualification path is gone. Fresh-run tip selection and immutable source supersession improve the prior findings.

## R3 — P1: completed backfill cursor skips replacement-branch events

In `src/willfly/ingest/runner.py::backfill_to_store`, no-op resume fetches a fresh tip after `backfill_range` has skipped the already-acknowledged range. It never invalidates/replays the old range when the hash changed. Independent reproduction uses one persistent BackfillCheckpointStore over heights 0–1: initial branch A has a selected log at 1; replacement branch B has a different selected log at 1. Resume updates the canonical tip to B, reports acknowledged range `[0, 1]` and a canonical checkpoint, but B's log is absent from raw storage. The new unit test for no-op resume uses empty logs and checks only the tip, so it misses this loss.

Required repair: compare acknowledged lineage against fresh source evidence before accepting a no-op or continuation cursor. On divergence, invalidate affected coverage and replay a bounded affected range, preserving raw fork evidence and crash-safe cursor semantics. If affected ancestry cannot be established or replay fails, mark the range as needing repair and do not claim completed coverage. A changed header alone cannot validate log coverage. Apply the policy to partial resumes as well as fully completed ranges. Do not silently retain a healthy current-run state when tip verification is unavailable.

Acceptance: same checkpoint file across restart; A and B both contain distinct selected events; B events must be durably captured exactly once, A retained and correctly classified, coverage repaired only after persistence. Include a quiet final block, multi-block divergence, partial cursor, replay failure, unchanged no-op and source outage. Preserve the fixed per-run header counts and bounded reads.

## R4 — P2: strict nested evidence and positive resolution invariant unfinished

In `canonicalize.py`, `CanonicalizationResult.is_resolved` and the local `resolved` calculation still use a denylist. Replacing a result's anchor state with an unrecognized string makes `is_resolved` true. Also `_matches_identity` and nested header equality accept bool values through Python equality: a height-1 anchor whose evidence `height`, `primary_header.number` and `external_header.number` are all `true` still qualifies. This was explicitly part of review 01's strict-evidence requirement.

Required repair: resolve only for an explicitly supported qualified state, a reached anchor, and no gaps; validate the types/required shape of every structured evidence field before comparison. Preserve existing valid evidence and fail closed on unsupported schema/state. Add negative tests for boolean/fractional nested heights and chain IDs, missing parents where required, malformed nested headers and unknown state.

## R5 — P2: qualification output persists complete authenticated endpoint URLs

`cli.py::_qualify_anchor` places primary/independent URLs verbatim in evidence stored in SQLite and in printed JSON. Provider URLs commonly carry keys in path/query/userinfo; this new operator workflow must separate connection secrets from exportable evidence. No real credentials were supplied during this audit and no leak is claimed to have occurred.

Required repair: retain credential-free provider identity/provenance and a stable non-secret endpoint reference in evidence and output; use configured credentials only for transport. Redact failure paths as well. Avoid a cosmetic query-only scrub that leaves path tokens. Add fake-canary tests covering path/query/userinfo credentials and normal public endpoints; no actual credentials or paid providers are required. Review inherited RunManifest provider endpoint persistence at the same boundary so the same connection does not leak through capture/backfill evidence.

## Handoff

Repair R3–R5 and return a reviewable checkpoint with concrete passing commands and evidence. Retain the successful DS-01–DS-06 and R1/R2 fixes. Feature loops remain gated until these concrete defects are rechecked; do not broaden into unrelated changes. Real source, archive, timed and financial/biological gates remain open independently of G0.
