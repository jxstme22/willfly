# Interrupted DeepSeek checkpoint audit

13 September 2026. **Disposition: M1-03 remains incomplete; repair before feature continuation.** DeepSeek stopped at a usage limit, not a completed release. Reviewed the uncommitted diff against `f39bf5b43f5723f7d15264597588f0ec71dfe8f2`; [file hashes](deepseek-audit-input.json) identify the inspected implementation. Concurrent product-planning documents belong to the coordinator and were not DeepSeek implementation claims.

## Verified scope

DeepSeek added persisted ancestry anchors, anchor status in canonical checkpoints, consecutive-height checks, runner anchor plumbing and eight additional passing tests. Reviewed all six changed implementation/test files. The existing data, attribution and dashboard checkpoint remains present; no new M1-05 export, M1-06 interaction or M1-07 coverage implementation was found in this diff.

Independent checks: 128 passed / one localhost test skipped in the managed sandbox; a separate permitted localhost run passed the remaining test (129 tests exercised successfully across two runs). Both existing planning catalogues pass. `compileall` passes. `git diff --check` fails on an extra blank line at EOF in `tests/test_header_reconciliation.py:427`. No live RPC sample, full browser interaction review or measured endurance qualification was performed in this audit.

The passing suite does not cover the defects below. Reproduce the diagnostic outputs from the repository root with `PYTHONPATH=src .venv/bin/python docs/reports/deepseek-anchor-audit-probes.py`. This probe imports existing fixture helpers and reports observed behavior; it is not itself an acceptance test. Convert the relevant scenarios into assertions for the repaired design.

## Required repairs

### DS-01 — P1: unverified declarations certify canonical history

**Locations:** `src/willfly/ingest/canonicalize.py:192` (`_anchor_state`), `src/willfly/storage/raw.py:51` (qualification/state definitions).

`_anchor_state` checks matching hash/height and optional identity, then returns `qualified` for every allowed qualification. The probe supplies `operator_declared_unverified` and obtains `resolved=true`, `anchor_state=qualified`, one canonical event. A `genesis` label attached to height 100 also qualifies. Evidence is currently arbitrary nonempty text. Runtime-code equality or a deployment receipt does not by itself establish a canonical/finalized block boundary. The denied-state tuple also omits the emitted `unqualified` state. A separate reproduction supplies the anchor at height 100 and an unrelated tip at 150 with a null parent: the walk never reaches the anchor, emits `unqualified`, yet `is_resolved` is true. Prefer an explicit allowlist plus a reached-anchor invariant.

**Required fix:** define a narrow, auditable qualification policy and structured evidence checks. Explicitly unverified or unknown declarations cannot certify history. Validate genesis invariants and external header identity/chain/config under declared trust/finality assumptions. An unavailable verifier must retain an unavailable/unverified result, not accept caller-supplied labels as evidence. Avoid inventing finality from code hashes.

**Acceptance:** negative tests for unverified, false-genesis, unsupported/malformed evidence and unknown states; positive fixture/chain-check evidence for each actually supported qualification; restart retains the same trust decision.

**Status:** OPEN.

### DS-02 — P1: bounded projections falsely orphan events outside their scope

**Location:** `src/willfly/ingest/canonicalize.py:153`–`179` (classification after anchor-limited walk).

Once the walk reaches an anchor it stops. Every event whose hash is absent from that bounded walk is then orphaned. Probe: anchor height 100, tip 101, events at 99/101/102 on one consistent chain. The result calls 99 and 102 orphaned, even though 99 is an ancestor and 102 is a descendant outside the selected tip. This corrupts previously observed history during backfill or reconciliation of an older window.

**Required fix:** define the projection's proven height range. Retain out-of-range events unresolved/out-of-scope or preserve independently established lineage under an explicit policy; orphan only branches contradicted by evidence within the proven range. Keep snapshots/revisions honest.

**Acceptance:** before-anchor and after-tip events remain non-orphaned; an actual competing block within the proven interval is still orphaned; persisted projections and restart reproduce these distinctions.

**Status:** OPEN.

### DS-03 — P1: invalid anchor permanently poisons the source namespace

**Locations:** `src/willfly/ingest/runner.py:208`, `:283` and corresponding backfill initialization; `src/willfly/storage/raw.py:469` (`save_ancestry_anchor`).

The runner validates only `source`, then stores the anchor before chain/config/evidence qualification. Probe: an anchor with `config_identity=WRONG` is persisted, capture completes with `config_mismatch`, and retry with the correct anchor raises `conflicting ancestry anchor already stored for this source`. Invalid input has changed durable trust state, preventing routine recovery. A fork crossing a once-valid anchor also lacks a documented supersession/requalification workflow.

**Required fix:** validate active chain/config and qualification before promoting/persisting trusted state, or store invalid candidates separately. Provide explicit, auditable recovery/requalification semantics retaining old evidence; never silently overwrite a trusted anchor. Verify wrong chain as well as wrong config. Rejected input must not strand the normal capture path.

**Acceptance:** invalid capture and backfill inputs leave no trusted checkpoint mutation; corrected retry succeeds; crossing-boundary requalification is either implemented with immutable history or explicitly blocked with a documented recoverable operation.

**Status:** OPEN.

### DS-04 — P2: capture/backfill disagree on genesis qualification

**Locations:** `src/willfly/ingest/runner.py:215`, `:291`, `:400` onward.

Capture invokes `_qualify_genesis_anchor`; backfill does not. With identical fixture headers at heights 0 and 1, the probe reports capture `qualified` and backfill `unavailable`. Both commands are supposed to share durable canonical semantics.

**Required fix:** share the qualification/reconciliation path rather than creating another header store. Check completed/no-op backfill restart behavior as well as nonempty and empty ranges.

**Acceptance:** equivalent evidence, identity and trust policy produce equivalent results across capture/backfill and fresh-process resumes. Do not loosen the qualification policy to get parity.

**Status:** OPEN.

### DS-05 — P1 completion gap: no supported operator path to qualify a bounded live anchor

**Locations:** `src/willfly/cli.py` capture/backfill argument and execution paths; `docs/runbooks/observatory.md`; source configuration schema.

The optional `AncestryAnchor` exists only on Python runner functions. The CLI does not construct/import/verify one, and no qualifying operator workflow is documented. Therefore ordinary bounded capture on a fresh store still cannot resolve canonical history. This was the operational problem M1-03 needed to address. New fixtures manually instantiate anchors and do not demonstrate that operators can establish a valid boundary.

**Required fix:** expose a bounded, read-only qualification path with source/config binding and reviewable evidence. Fail closed when the necessary independent/finality evidence is unavailable; document supported providers/policies and recovery. A fixture-backed subprocess integration must exercise the real CLI path. Preserve live source restrictions and archive gates.

**Acceptance:** fresh-store operator workflow qualifies a supported anchor, captures/restarts and exposes the trust state; mismatched/unverified input fails without poisoning storage. Keep live M1-03 acceptance open if real evidence is unavailable.

**Status:** OPEN.

### DS-06 — P2: coercive anchor deserialization bypasses strict field validation

**Location:** `src/willfly/storage/raw.py:121` (`AncestryAnchor.from_dict`).

`int(...)` turns boolean IDs/heights into integers and truncates fractional numbers; `str(...)` turns null/string-invalid fields into nonempty text; a string evidence value becomes a tuple of characters. This defeats the stricter constructor checks just as a CLI/import boundary is being added. Reproduced `chain_id=true`, `height=100.9`, `source=null`, `config_identity=null`, `evidence="x"`: accepted as chain 1, height 100, the text "None" and one-character evidence.

**Required fix:** validate the serialized schema before construction, including real integer types, evidence sequence shape, nonempty string elements, timestamp and identity fields. Reject malformed data rather than silently repairing it.

**Acceptance:** JSON boolean/fractional/null IDs and heights, string-shaped evidence and null source/config are rejected; valid export/import round trips remain exact.

**Status:** OPEN.

## Handoff and independent review

Luna Extra High (`gpt-5.6-luna`, `xhigh`) should repair DS-01 through DS-06 and the whitespace failure, update documentation and add behavior-based regressions. The coordinator must recheck these findings before authorizing the feature-build continuation described in `docs/luna-extra-high-handoff.md`. Keep the M1 source/timed gates open and do not label the interrupted checkpoint accepted.

After repairs are independently verified, continue the remaining M1 integration alongside the B-track priority: actual connectome training, 24/7 candidate learning without user trades, coin/LP/exit signals, manual execution feedback and tested model promotion. Every inherited audit finding and economic gate remains relevant; this review was scoped to the interrupted M1-03 delta, not a fresh certification of the entire repository.
