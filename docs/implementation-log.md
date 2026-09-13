# Implementation log

## Batch 2026-09-13 — P0-01 through P1-02 foundation

### Task status

- P0-01 — DONE: package metadata, Python 3.12 pin, offline CLI, tests and ignore rules.
- P0-02 — IN_PROGRESS: chain and V4 facts verified; Pons V2 launch coverage/creation-block gate remains open.
- P0-03 — IN_PROGRESS: public RPC bounded probe and provider/scanner assessment recorded; archive limits and optional APIs remain unverified.
- P0-04 — DONE: strict versioned contracts and edge-case fixtures implemented.
- P0-05 — DONE: initial experiment and follower-outcome proposal frozen before holdout access.
- P0-06 — DONE: provenance-tagged synthetic fixtures and seven-step demo checklist added.
- P1-01 — DONE: atomic compressed raw batches, SQLite metadata/checkpoints and corruption checks added.
- P1-02 — DONE: read-only RPC client and bounded polling capture path passed injected and live receipt/capture checks.

### Changes

- Added a Python 3.12 package with `willfly doctor` and `willfly fixture-check`.
- Added strict JSON-safe domain contracts for raw events, V3/V4 pool identity,
  launches, observations, payment legs, trade evidence, vendor assessments and cohorts.
- Added source manifest, V4 event ABI manifest, provider budget and evidence matrix.
- Added frozen experiment YAML and evaluation contract.
- Added provenance-tagged fixtures for genuine swaps, transfers, gifts/airdrops,
  ambiguous/no-payment receipts, estimated USD, multi-recipient delivery,
  stale vendor data, unknown cohort history, duplicate delivery, malformed logs,
  native ETH and orphaned/fork evidence.
- Added local append-only raw storage with checkpoint acknowledgement and restart-safe verification.
- Added a read-only Robinhood RPC adapter with explicit chain identity checks,
  bounded log ranges, retry/backoff, block timestamps and arrival timestamps.

### Verification commands/results

```text
python3 --version                         Python 3.12.10
python3 -m pytest                         16 passed
PYTHONPATH=src python3 -m willfly fixture-check  passed (fixture origin: synthetic)
PYTHONPATH=src python3 -m willfly doctor         status: ok; launch-source gate: open
PYTHONPATH=src python3 -m willfly doctor --strict status: failed/exit 1 while launch gate is open
```

Observed evidence:

- public RPC `eth_chainId` returned `0x1237`;
- public RPC head probe returned `0x3a93f54`;
- V4 PoolManager code probe returned 24,009 bytes;
- Pons V2 code probe returned 22,757 bytes;
- V4 deployment receipt returned status `0x1` at block `0x236e` (`9070`);
- a bounded 101-block PoolManager log probe returned one ownership log, not ten
  trading examples.
- the Python adapter passed a live bounded read: chain `4663`, head `61434717`,
  V4 runtime `24,009` bytes. The first Python probe got HTTP 403 from the
  endpoint's default user agent; an explicit read-only User-Agent fixed it.

Synthetic evidence cannot satisfy live coverage, archive or latency gates.

### Blockers and next dependency-ready task

P0-02/P0-03 remain open for independently verified Pons V2 creation history,
archive history, rate limits and a provider plan.
RHTrenches and Mezzanine remain optional and must not block native collection.

## Batch 2026-09-13 — P1-05 through P3-08 implementation loop

### Task status

- P1-05 — DONE: adaptive resumable backfill validates provider page bounds,
  duplicates and checkpoint-after-callback recovery.
- P1-06 — DONE: canonical/orphan projections, confirmation state, missing
  parents and parent-cycle failure are covered.
- P1-07 — DONE: quality metrics and retry supervision report degraded gaps and
  redact credential-shaped error values.
- P1-08 — IN_PROGRESS: coverage audit contract is implemented, but the
  required 72-hour provider-independent capture audit has not been claimed.
- P2-01 through P2-06 — DONE as a partial local Observatory v0.1 package:
  availability-cutoff discovery, causal timelines, Parquet export, GET-only
  inspection routes, CLI run IDs, dashboard rendering and runbook are present.
- P3-01 through P3-08 — DONE as replay/evidence machinery. The generated
  replay audit and bundle remain explicitly inconclusive until observed sample
  count and historical-state gates are met.

### Changes

- Added provider-independent coverage accounting with recall, missing keys,
  duplicate delivery, quarantined exclusions and an explicit independence flag.
- Added discovery/pool projections and token timelines using separate event and
  arrival cutoffs. Ambiguous, transfer and gift activity remains visible but is
  excluded from verified flow; cohort history is unknown unless observed at the
  cutoff.
- Added optional Arrow/Parquet export with exact record hashes, logical keys,
  source-config hashes, gaps and quality metadata. A targeted Arrow round-trip
  preserved `90071992547409931234567890` exactly.
- Added local GET-only `/health`, `/launches`, `/tokens/{token}/timeline` and
  `/pools/{pool_id}` routing plus bounded CLI `capture`, `backfill`, `audit`,
  `export` and `serve` surfaces. The default host is `127.0.0.1`.
- Added HTML dashboard and Observatory runbook with visible cutoff, quality,
  lifecycle, evidence and excluded-activity fields.
- Added deterministic replay scheduler, exact-integer portfolio ledger,
  constant-product fill assumptions, follower requoting, causal labels,
  fixed-allocation constraints, leakage-resistant split manifests, replay
  stress audit and hashed replay evidence bundles.

### Verification commands/results

```text
python3 -m pytest -q                         63 passed, 1 optional export skip
.venv/bin/python -m pytest -q                64 passed
.venv/bin/willfly fixture-check              passed (fixture origin: synthetic)
.venv/bin/willfly doctor                     status: ok; launch-source gate: open
PYTHONPATH=src .venv/bin/python <Arrow check> 1 row round-tripped; large integer preserved
```

The clean-environment suite passed with Python 3.12, pytest 9.0.3 and
pyarrow 25.0.1. The sandbox does not permit binding a local socket, so API
route behavior is tested through the same router used by the HTTP handler; the
server still defaults to loopback and only implements GET/405.

### Open evidence gates

P0-02/P0-03 and P1-04/P1-08 remain open for verified Pons creation/archive
history, lifecycle/non-graduate completeness, provider independence and a
72-hour capture sample. P3 audit output intentionally reports fewer than 20
observed transaction examples as `inconclusive`; no profitability claim is
made. Later phases remain untouched until those evidence gates are satisfied.

Next task: decode one launchpad lifecycle (P1-04); P0-02/P0-03 remain open
evidence gates and do not authorize unverified launch-level claims.

## Batch 2026-09-13 — P1-02 completion and P1-03 V4 evidence join

### Task status

- P1-02 — DONE: bounded polling, chain checks, retry/backoff and read-only RPC surface are covered.
- P1-03 — DONE: V4 event decoding, pool identity, hook flags, lineage-preserving deduplication and conservative receipt joins are covered.
- P0-02 — IN_PROGRESS: live V4 coverage is now evidenced; Pons V2 ABI, creation block and launch lifecycle coverage remain open.
- P0-03 — IN_PROGRESS: native RPC reads are usable; archive depth, rate limits and optional scanner integrations remain unverified.

### Changes

- Added deterministic V4 `Initialize`, `Swap` and `ModifyLiquidity` decoding from the pinned ABI, including signed fields, exact pool IDs and native-zero-address currency ordering.
- Added an explicit `unsupported_hook_behavior` flag for non-zero V4 hooks; the decoder does not imply standard mechanics for custom hooks.
- Added receipt-side joining for exact ERC-20 transfer legs and native ETH transaction value. Receipt and swap transaction hashes must match, failed receipts are quarantined, and indirect or missing cash legs remain ambiguous.
- Kept multi-hop routes as one transaction-level `TradeEvidence` record and preserved duplicate delivery lineage across sources.

### Verification commands/results

```text
python3 -m pytest                         28 passed
PYTHONPATH=src python3 -m willfly fixture-check  passed (fixture origin: synthetic)
PYTHONPATH=src python3 -m willfly doctor         status: ok; launch-source gate: open
```

Observed live evidence from the configured public RPC:

- bounded capture from blocks `61436940` through `61437618` returned 2,791 raw PoolManager logs;
- 2,742 decoded deterministically: 2,319 `Swap`, 405 `ModifyLiquidity` and 18 `Initialize`; 49 logs were outside the supported subset and zero supported logs were malformed;
- all decoded pool IDs had the expected bytes32 shape and all captured records retained event and arrival timestamps;
- a separate 20-block receipt cross-check returned 73 logs, found a supported swap, and matched its successful receipt with one corresponding receipt log.

Synthetic evidence covers two V4 pools under one manager, overlapping-source deduplication,
non-zero-hook flags, exact ERC-20/native payment joins, failed/mismatched receipts,
no-payment receipts, airdrops, malformed transfers and vendor-only labels.

### Blockers and next dependency-ready task

P0-02/P0-03 remain open for launchpad ABI/source pin, creation block, non-graduate
history, archive depth, provider limits and optional scanner terms. P1-04 is now
the next dependency-ready implementation task; it must preserve the open launch
source gate and keep unknown lifecycle states explicit.

## Batch 2026-09-13 — P1-04 Pons V2 lifecycle adapter (partial)

### Task status

- P1-04 — IN_PROGRESS: the pinned factory event subset decodes and projects launch lifecycle records; archive and non-graduate gates remain open.
- P0-02 — IN_PROGRESS: the current factory address/source discrepancy was resolved; ABI/source are pinned and live creation events decode, but lifecycle coverage is incomplete.
- P0-03 — IN_PROGRESS: the native RPC returns current Pons events but reports zero block timestamps for that source; provider history/limits remain unverified.

### Changes

- Reconciled the current Pons V2 factory to `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` and retained the earlier `0x7E1E...` deployment as a non-selected legacy candidate.
- Added the pinned Pons V2 lifecycle ABI manifest for `TokenLaunched`, `LaunchSwept`, `GraduationTokensPermanentlyLocked` and `PoolGraduated`.
- Added deterministic launchpad decoding with exact atomic quantities, emitter checks, unsupported-event quarantine, duplicate lineage merging and lifecycle projection.
- Kept pool linkage empty when `PoolGraduated` does not provide a V4 PoolId; retained sweep-without-pool as `unknown` rather than inferring a non-graduate.
- Fixed RPC timestamp handling so a zero provider sentinel becomes an explicit arrival-time fallback instead of a 1970 event timestamp.

### Verification commands/results

```text
python3 -m pytest                         35 passed
PYTHONPATH=src python3 -m willfly fixture-check  passed (fixture origin: synthetic)
PYTHONPATH=src python3 -m willfly doctor         status: ok; launch-source gate: open
```

Observed live evidence:

- the current factory returned 24,177 runtime bytes with SHA-256 `226a042e6d68a69a6038d4fda211925b03eb5299399434b87a7877f79f6e3848`;
- the documented first-seen/deployment block is `26841846` (`0x198bcf6`), but the public RPC did not return historical code at that block, so the creation block remains documented/unverified;
- a bounded 2,000-block current-factory query returned 34 `TokenLaunched` logs; all 34 decoded successfully with the pinned adapter, all had zero `blockTimestamp` values, and no sweep/lock/pool-graduation event appeared in that window.

The official Pons source describes the V2 factory and lifecycle, while the
Bitquery event reference supplies the observed event signatures and documents
that older launch history needs an archive-capable source. These sources support
the adapter contract but do not replace native history/completeness evidence.

### Blockers and next dependency-ready task

P1-04 cannot be marked DONE until a supported archive/native source verifies the
factory creation point, supplies lifecycle samples beyond `TokenLaunched`, and
demonstrates non-graduate coverage. Continue with P1-04's gate-aware coverage
fixtures and provider-independent history checks before starting P1-05.

## Batch 2026-09-13 — P4 through P8 research-ready shadow machinery

### Task status

- P4-01 through P4-06 — DONE: simple and conventional baselines, common action mapping, run budgets, metrics, paired block bootstrap and chronological evaluation machinery are covered by fixtures.
- P4-07 — IN_PROGRESS: the baseline review is explicitly inconclusive until live coverage, adequate independent episodes and historical execution state exist.
- P5-01 — IN_PROGRESS: the connectome manifest remains `pending_verification`; no release, license or biological fidelity is claimed.
- P5-02 through P5-06 — DONE: sparse graph/control construction, rate reservoir resets, frozen readout, matched five-seed comparison registration and ablation review machinery are implemented.
- P5-07 — IN_PROGRESS: neural progression review remains inconclusive under the predeclared multi-window and uncertainty gates.
- P5-08 — DONE: hash-checked graph/reservoir/readout/model-card package reloads and preserves reference predictions.
- P6-01 through P6-05 — DONE: optional scanner access is explicitly unavailable, causal LP observations, source-backed text claims, bounded schema-checked enrichment and contamination audit are implemented.
- P6-06 — IN_PROGRESS: factorial registration and the hybrid review are present, but no valid historical LLM/scanner performance claim is available.
- P6-07 — DONE: decision inspection exposes action, observation, prediction, constraints and evidence references without inventing motives.
- P7-01 — IN_PROGRESS: no pool family is enabled until deployment, hook and observed-receipt evidence is verified.
- P7-02 through P7-06 — DONE: LP position/fee replay, lifecycle ledger, restricted policies, shared mode selection and modeled stress diagnostics are implemented as modeled machinery.
- P7-07 — IN_PROGRESS: synthetic accounting passes, but observed pool checkpoints and supported-family evidence are still missing.
- P7-08 — DONE: LP shadow eligibility is explicitly disabled; spot shadow remains independently eligible.
- P8-01 — IN_PROGRESS: the freeze procedure and pending configuration exist; the real start time/hash must be recorded immediately before observation begins.
- P8-02/P8-03 — DONE: restart-safe hypothetical decisions, shared-cash constraints, stale/contradictory pause behavior and unknown-execution handling are covered.
- P8-04 through P8-06 — IN_PROGRESS: duration/episode/availability audit, reconciliation and release package exist, but the 14-day prospective window has not been collected.

### Changes

- Added ordinary baseline strategies, deterministic conventional models, prediction-to-action mapping, reproducible run tracking and paired evaluation metrics.
- Added license-gated connectome ingestion, sparse graph controls, rate-based reservoir dynamics, frozen readout comparison/ablation review and a hash-checked reloadable neural package.
- Added explicit unavailable-source boundaries for LP Agent, RHTrenches and Mezzanine; causal LP/scanner/text schemas; bounded LLM enrichment with a numeric fallback; historical retrieval cutoff checks; factorial registration and evidence-backed decision inspection.
- Added LP position/fee and lifecycle replay, fixed-wide/volatility/idle policies, shared spot/LP/idle mode selection and modeled stress diagnostics. LP remains disabled pending pool-family verification.
- Added `configs/shadow/config.json`, a pre-observation freeze procedure, SQLite-backed hypothetical decision checkpoints, deduplicated restart behavior, shared-cash accounting, degraded-mode health rules and a 14-day/200-launch/99%-availability audit.
- Added the v0.6 gated release note and empty artifact-bundle marker. No signer, transaction builder, broadcast path or funded-return claim was added.

### Verification commands/results

```text
python3 -m pytest                         80 passed, 1 optional export skip
PYTHONPATH=src python3 -m willfly fixture-check  passed (fixture origin: synthetic)
PYTHONPATH=src python3 -m willfly doctor         status: ok; launch-source gate: open
python3 -m json.tool docs/build-tasks.json       passed
```

The shadow window is intentionally not started by this implementation batch:
the static config still has null `start_time` and `config_hash`, and the review
remains inconclusive until a real read-only collector supplies prospective
observations. P0/P1 launch-history, provider-independence and LP pool-family
gates remain open. P9 funded execution and P10 expansion stay conditional.

## Verification loop — Phase 8 safety hardening

- Added cache keys and bounded retries to optional LLM enrichment; invalid,
  timeout-like and schema-failing calls return the numerical fallback.
- Added the explicit Mezzanine unavailable adapter boundary and included it in
  the P6 evidence map.
- Fixed walk-forward generator reuse, recorded search-budget failures, released
  hypothetical cash on exits, blocked stale exits into hold/reconcile behavior,
  and rejected predictions whose as-of time is later than the received observation.
- Added the `willfly shadow` CLI check. The current static config returns
  `shadow_config_not_frozen` with exit 1; it does not start a collector or make
  an observation claim.

```text
python3 -m pytest                         80 passed, 1 optional export skip
.venv/bin/python -m pytest -rA            81 passed
PYTHONPATH=src python3 -m willfly shadow  blocked; exit 1 (config not frozen)
```

## Astra deep audit — 13 September 2026

Read `docs/reports/astra-deep-audit.md` for the reviewed findings and limitations. Incoming 81 tests passed; after 19 additional regression cases and corrections, 100 tests pass. Fixed raw republish corruption, missing-time fabrication, mixed-timezone replay, partition-boundary leakage, phantom shadow cash release, future arrival/quote handling, wrong-asset round trips, config/package integrity, joint ridge fitting, heterogeneous export and unsupported LLM claims. Planning-only commands and unverified economic/neural evaluation no longer report readiness.

The remaining pipeline, protocol/accounting, source coverage, model controls and real LLM budget work is explicitly scoped in the 26-task next catalogue. The original 77 tasks retain their incoming statuses and evidence, with full acceptance reopened where criteria or dependencies are incomplete. This is a status correction, not deletion of implementation.

Verification: `.venv/bin/python -m pytest` (100 passed); `python3 scripts/check_planning.py` validates both catalogues and generated Markdown. A pinned-action Python 3.12 CI workflow was added. Publication and remote CI outcomes are recorded separately in `docs/reports/repository-publication.md`.

Next implementation preference: Muse Sparks 1.3, selected by the user in their next session. No model/session was launched here. Start M1-01 after completing reviewed private publication; keep funded execution and LP disabled.

## Batch 2026-09-13 — M1-01 verification and M1-02 durable capture (Muse Sparks 1.3)

### Task status

- M1-01 — IN_PROGRESS: source manifest, matrix and budget updated with 13 Sept 2026 bounded probes. All claimed families have 10+ examples; historical-code archive and non-graduate window coverage remain open gates.
- M1-02 — IN_PROGRESS: `willfly capture` and `willfly backfill` now perform durable bounded work with filter-bound checkpoints, empty-range acknowledgements, streaming pages and run manifests. `--dry-run` preserves the old plan-only behavior (exit 3).

### Changes

- Verified chain 4663, V4 manager (24,009 bytes) and Pons V2 factory (24,177 bytes) code hashes via public RPC.
- V4 679-block sample: 1,853 raw logs (Swap 1,249, ModifyLiquidity 551, Initialize 12, 41 unsupported observed).
- Pons 39-page scan over `61616075`–`61694074`: 1,130 TokenLaunched, 10 LaunchSwept, 10 Locked, 10 PoolGraduated, 127 other observed.
- Header resolution verified on block `61691574` (log `0x0` sentinel, header `0x6aa62de1`, hash match). Archive: creation block `26841846` header and 22 logs in first 100 blocks available; historical code unavailable (`metadata is not found`).
- Added `src/willfly/ingest/runner.py` with filter identity, checkpoint source binding, capture/backfill-to-store orchestration and run manifests.
- Extended `RawBatchStore` with `empty_range_acks` and `acknowledge_empty_range`; extended `BackfillCheckpointStore` with `filter_hash` binding, `retain_events=False` streaming and changed-filter rejection.
- Fixed `capture_once` to honor `--to-block`; CLI now executes by default, `--dry-run` for plans, and returns nonzero on failures. No signing surface added.
- Added `tests/test_capture_runner.py` (7 tests): durable capture, empty acknowledgement, crash resume without loss, changed-filter isolation, streaming, overlapping-range failure and read-only rejection.
- Updated `tests/test_cli.py` for `--dry-run` plans; updated runbook with store/manifest documentation.

### Verification commands/results

```text
.venv/bin/python -m pytest                         107 passed
python3 scripts/render_planning.py
python3 scripts/check_planning.py                  both catalogues agree
.venv/bin/python -m willfly capture --from-block 61694000 --to-block 61694100 --store-dir /tmp/willfly-m102-test --source m102-live
  executed, 251 events, 1 batch, checkpoint m102-live:4663:6707..., exit 0
.venv/bin/python -m willfly backfill --from-block 61694000 --to-block 61694100 --store-dir /tmp/willfly-m102-test --source m102-live-backfill --page-size 50
  executed, 251 events, 2 batches, 3 covered ranges, exit 0
.venv/bin/python -m willfly capture --from-block -5 --to-block 10
  error, exit 2 (failures return nonzero)
```

Event time (header `05:04:24`) remains distinct from received time (`05:10:17`). Changed `--address` yields a different filter hash and namespace with empty header evidence. No `eth_sendRawTransaction` path exists in the runner.

### Open gates and next task

M1-01 remains open for historical-code archive (public RPC unavailable) and a declared non-graduate window sample. M1-02 remains IN_PROGRESS until M1-01 completes (dependency) and M1-03 header/fork persistence lands. Next: M1-03 persist headers and reconcile forks, then M1-04 attribution hardening, reusing this durable store. Later phases follow only after the Observatory evidence bundle (M1-07).

## GPT Terra continuation dispatch — 13 September 2026

The user requested handoff to GPT Terra to continue the remaining work. Prepared `docs/gpt-terra-handoff.md` and updated the active catalogue/model preference without changing M1-01/M1-02 statuses. The uncommitted Muse implementation checkpoint is preserved. Begin with a local verification/review of that checkpoint, then M1-03 ancestry/fork recovery and subsequent dependency-ready work. Real qualification windows remain measured evidence gates, not reasons to stop independent implementation. The existing implementation task is being resumed with `gpt-5.6-terra`; no additional task or timed automation is created.

## Batch 2026-09-13 — M1-03 header ancestry and fork reconciliation (GPT Terra)

### Status

- M1-03 — IN_PROGRESS: complete header evidence, quiet-block persistence,
  transactional canonical projections and conservative health handling are
  implemented and fixture-verified. It cannot be marked DONE while M1-02 is
  still gated by M1-01, and it has not been qualified against a fresh live
  Observatory source.

### Changes

- Added an immutable SQLite header ledger separate from append-only raw batches,
  with persisted header-range evidence and explicit missing-block records.
- Capture and backfill now request every header in their bounded ranges, so
  selected-log-free blocks participate in ancestry. Header acquisition errors
  are redacted in run manifests rather than being swallowed.
- Canonical rebuilds replace only derived projection/checkpoint rows in one
  transaction; raw batches remain unchanged. A newer branch therefore marks
  former selected events orphaned while a quiet block can become the repaired
  canonical checkpoint.
- Missing parent hashes and absent parent metadata leave all non-quarantined
  evidence unresolved/provisional. They cannot be misclassified as an orphan
  branch or a canonical root. Zero header timestamps fail event-time resolution.
- Extended quality reports with an explicit source state (default `unknown`) and
  unresolved-parent evidence. Full event coverage alone cannot report healthy.

### Verification

```text
.venv/bin/python -m pytest -q                 114 passed
git diff --check                               passed
.venv/bin/python -m compileall -q src tests    passed
```

`tests/test_header_reconciliation.py` covers a restarted multi-block fork with
quiet intermediate blocks, header-only tip, missing parent, provider outage,
zero timestamp and header-hash mismatch. Existing capture/backfill, storage,
canonicalization and quality tests continue to pass. The test fixtures are not
evidence of real provider coverage, latency, archive access or a completed
72-hour Observatory audit.

### Next dependency-ready work

Proceed with M1-04 route attribution hardening. M1-01 source-history and
non-graduate gates remain open; no signal, funded trade, LP position or shadow
qualification is claimed.

## Batch 2026-09-13 — M1-04 route proof and net cash flow (GPT Terra)

### Status

- M1-04 — IN_PROGRESS: the v0.2 `TradeEvidence` route/cash boundary and
  adversarial receipt fixtures are implemented. Live sampled-receipt evidence,
  the M1-01/M1-02 dependency gates and integrated M1-05 projection evidence
  remain open.

### Changes

- V4 decoding now retains the emitting contract address. A verified route must
  match the configured V4 manager, a declared pool ID/currencies, the receipt's
  swap-log index and the wallet's supported asset direction.
- `genuine_swap` now requires verified route evidence, explicit `buy` or `sell`
  direction and positive net wallet input after recorded refunds. Route status,
  direction and inbound refund legs are serialized in `TradeEvidence` v0.2.
- Receipt parsing only accepts route-actor transfers for the selected token and
  verified pool quote asset. It records fee/route splits, keeps airdrops and
  unrelated multicall legs out of receipts, treats unmatched wraps/unwraps as
  uncertain and requires explicit native-refund coverage.
- Added economic trade deduplication by transaction, wallet, token and
  direction. Equivalent source deliveries merge lineage; conflicting duplicate
  cash flows fail closed.
- Timelines now exclude legacy or uncertain genuine-swap claims from verified
  flow, deduplicate v0.2 evidence, and report verified buys, sells, token
  outflow, quote inflow and net buy payments separately.

### Verification

```text
.venv/bin/python -m pytest -q tests/test_v4_protocols.py tests/test_features.py tests/test_ui.py    passed
git diff --check && .venv/bin/python -m compileall -q src tests                                    passed
```

The V4 fixtures cover a routed buy, sell, duplicate source delivery, unrelated
airdrop plus swap, fee/route split, full native refund, unproved wrapped-native
path, forged issuer, failed receipt and cross-transaction event. They are local
mechanics evidence only; they do not establish deployed route coverage or a
tradable signal.

## Batch 2026-09-13 — M1-05/M1-06 causal persistence and local Observatory (GPT Terra)

### Status

- M1-05 — IN_PROGRESS: immutable causal projections, dated lifecycle revisions,
  exclusion records and restart-safe snapshot persistence are implemented.
- M1-06 — IN_PROGRESS: a persisted snapshot now feeds the read-only API and HTML
  dashboard, but the prerequisite source acceptance and qualified live launch
  demonstration remain open.

### Changes

- Added `LifecycleRevision` and `ObservatoryProjection`. A current launch record
  cannot rewrite a prior snapshot: lifecycle is `unknown` until a dated revision
  available at the projection cutoff supplies `active`, `non_graduate` or
  `graduated`.
- Materialization takes canonical raw evidence only. Orphaned/quarantined raw
  rows and unverified legacy trade claims remain explicit projection exclusions;
  they are not silently removed or counted as flow.
- Added immutable snapshot records to the recorder SQLite store with content IDs,
  source/type validation and an optional prior-snapshot link. A fresh process can
  restore the same serialized projection without reading mutable current data.
- Added `willfly materialize --input ... --as-of-time ...` for typed offline JSON
  inputs and `willfly serve --store-dir ... --snapshot-id ...` for inspecting the
  resulting local-only bundle. The API now exposes `/exclusions` and
  `/evidence/{reference}`; `/` and `/dashboard` render the persisted dashboard.
- The dashboard displays quality/missingness, launch lifecycle/evidence, buy/sell
  timeline values and excluded evidence instead of presenting empty state as
  healthy zero activity.

### Verification

```text
.venv/bin/python -m pytest -q tests/test_cli.py tests/test_observatory_projection.py tests/test_api.py    passed (one socket test skipped)
.venv/bin/python -m pytest -q                                                                    passed (one socket test skipped)
python3 scripts/render_planning.py && python3 scripts/check_planning.py                         passed
git diff --check && .venv/bin/python -m compileall -q src tests                                 passed
```

The projection fixture proves future-lifecycle append invariance, orphan exclusion,
revision persistence and fresh-store API restoration. It includes a launch that is
currently marked graduated but correctly appears active/non-graduate only when the
respective dated revision is available. The managed sandbox denies loopback socket
binding (`PermissionError`), so the real HTTP request segment skips there after
route/dashboard construction has passed; this is recorded rather than treated as a
network success. No real launch collection or 72-hour audit is claimed.

## Batch 2026-09-13 — M1-03/M1-04 verification, live receipt sampling and integrated demo (Muse Sparks 1.3 continuation)

### Status

- M1-03 — IN_PROGRESS: prior checkpoint verified; live restart evidence collected.
  A bounded live window is honestly `unresolved` below its oldest stored header
  (boundary == oldest header's parent), and each ancestry extension moves the
  boundary back without ever orphaning in-window history.
- M1-04 — IN_PROGRESS: prior checkpoint verified; the "sampled supported receipts"
  gate is now satisfied with real chain receipts classified through the v0.2 path.
- M1-05/M1-06 — IN_PROGRESS: an integrated live demo now runs capture → headers →
  projection → launch decode → materialize → fresh-process HTTP serving.

### Deduplication note

A redundant parallel `src/willfly/ingest/headers.py` (separate HeaderStore) and
unused `backfill_range(header_store=...)` plumbing from an overlapping editing
stream were removed. The canonical header pipeline is `RawBatchStore.persist_headers`
plus `rebuild_canonical_projection`, matching the M1-03 target paths. 121 tests
pass after the cleanup.

### Live evidence (all read-only, public RPC, 13 September 2026)

```text
M1-03 live restart evidence (store /tmp/willfly-m103-small):
- capture 61932990-61932997: 40 events, 8 headers, no gaps, tip persisted
- fresh-process restart: batches=8 durable, 60 headers persisted incl. quiet blocks,
  8 header-range records, checkpoint tip stable across restarts
- ancestry boundary behaviour: each window extension (61932989...61932938) moves the
  missing-parent boundary exactly one block back; boundary == oldest stored header's
  parent hash at every step; in-window events stay unresolved (never orphaned)
- final projection: 320 events, all 'unresolved' (bounded window, honest state)

M1-04 live sampled receipts (v0.2 trade_evidence_from_receipt):
- 41 recent pool Initialize events decoded into verified pool identities
- sample 1: tx 0x5f1e3c85b013... pool 0x0000.../0x7a96e16127 hook 0xe5e70264
  -> genuine_swap | route verified | buy; native ETH payment 8033484769109287;
  receipt 426762970571021803740779 of token 0x7a96e16127; flag token_fee_or_route_split_observed
- sample 2: tx 0x09bb66d3439c... same pool -> genuine_swap | verified | buy
  (20e13 wei native payment)
- ambiguous live cases correctly stay ambiguous: router-mediated swaps where the
  wallet has no direct legs remain 'ambiguous' with no_readable_cash_leg; a
  zero-currency0 pool with a native tx value but no native payment leg stays ambiguous
  (native_input_outside_verified_pool_currency / quote_asset_not_in_verified_pool_currency)

Integrated demo (store /tmp/willfly-pons-demo):
- capture 61959990-61960000 (Pons): 1 TokenLaunched event decoded
  -> launch 0x166c79d40996b9d3fe64a2b19c4f3199f4f7d258, state 'active',
  created_at from header time 2026-09-13T12:33:28+00:00 (distinct from received)
- materialize_observatory_projection saved as immutable snapshot
  49b00c29de2681ebd7e444dc (source pons-demo)
- fresh-process serve: GET /launches returns the launch; GET / renders the dashboard
  including the launch token; GET /exclusions total=1 (the single unresolved
  provisional raw event); GET /evidence/<ref> returns the raw evidence record
```

### Verification

```text
.venv/bin/python -m pytest                 121 passed
python3 scripts/render_planning.py
python3 scripts/check_planning.py          both catalogues agree
.venv/bin/python -m compileall -q src tests
git diff --check                           passed
```

### Open gates

- M1-01: historical-code archive and non-graduate window coverage remain open, so
  M1-02 through M1-06 cannot be marked DONE.
- The 72-hour capture audit (M1-07) and 14-day shadow (M3-03) are timed evidence
  gates that continue to gate their own acceptance, not the implementation.
- Live bounded windows resolve to `canonical` only when their ancestry reaches a
  declared boundary; production collection windows must either overlap or use an
  explicit window anchor decision recorded in the runbook.


## 2026-09-13 — DeepSeek continuation and explicit M1-06 assignment

User selected DeepSeek V4.1 Flash for the next external implementation session and explicitly included the terminal monitoring UI. Added docs/deepseek-v4.1-flash-handoff.md, linked it from README and the active roadmap, and updated the JSON model preference and unfinished-task ownership without changing completion statuses. M1-06 now carries the full terminal design, real-data interactions, accessibility, stale-state and browser verification requirements from docs/ui-terminal-design.md.

Recorded an additional M1-03 acceptance issue: finite parent walks remain unresolved at the oldest missing ancestor without an explicit verified anchor. The next builder must define anchor provenance, consecutive heights and fork-boundary invalidation; this planning update does not implement the fix. M1-05 export evidence and M1-07 coverage scaffolding precede/reinforce the UI batch; source and elapsed-time gates remain open.

Preserved all inherited implementation changes. Verification: managed-sandbox suite 120 passed / 1 skipped; targeted permitted localhost HTTP test passed, so all 121 tests were exercised successfully across the two runs. Both planning catalogues validate; compileall and diff whitespace checks pass. Changed-file credential-pattern scan found no matches (not a comprehensive security audit). Live RPC samples were not rerun during this documentation/checkpoint batch.

DeepSeek has not been launched by this task: available Codex model controls do not expose it. Terra remains paused; use a single external implementation writer with the new handoff. Checkpoint publication records code and open gates, not Observatory acceptance.


## 2026-09-13 — Main product: brain signals and manual execution

Recorded the user's explicit product priority in docs/brain-signal-product.md and docs/brain-product-tasks.json (B0–B10). The next track brings real-connectome training forward after the current DeepSeek batch, adds spot/LP/exit signals, public-wallet/position feedback, historical and external-wallet data, and evaluated model promotion on the Windows/WSL2 PC. Linked this priority from README, project direction and the roadmap. Existing M statuses and timed/economic gates are unchanged. This is a product/planning update, not implemented model or execution functionality. Active implementation changes in ingest/storage were left untouched.


## 2026-09-13 — Continuous learning independent of personal trades

Added the user's explicit 24/7 learning requirement to the brain product brief, B-track JSON v1.1, README, project direction and roadmap. Expanded B3/B4/B6/B8/B9/B10 acceptance to cover durable label maturation, automatic resource-bounded candidate training from external-wallet/market evidence and historical replay, truthful waiting/outage states, forward evaluation, versioned promotion and a zero-personal-trade learning demonstration. Observation is continuous while infrastructure is available; training cycles need qualified evidence and do not silently alter the active model. This documents required future behavior, not a running service or scheduled Codex automation. Active implementation files were not edited.


## 2026-09-13 — Luna Extra High post-DeepSeek sequence

User authorized continued build loops after DeepSeek finishes, with a coordinator audit first, Luna repairs, independent repair verification, then remaining in-scope phases. Prepared docs/luna-extra-high-handoff.md and docs/luna-build-loops.json (G0–G5); set the B-track model to gpt-5.6-luna/xhigh and linked current product authorities. DeepSeek's active M-catalogue preference/statuses and source edits were left intact. The final audit report is a future output, not a fabricated present finding. No Luna dispatch, goal execution, external-model completion watcher or funded scope was started.


## 2026-09-13 — Interrupted DeepSeek checkpoint audit and Luna takeover

User reports DeepSeek exhausted its limit during M1-03 and authorizes Luna Extra High takeover. Independently audited all six changed implementation/test files against f39bf5b. Added docs/reports/deepseek-completion-audit.md, input file hashes and executable diagnostic probes. Reproduced unverified/false-genesis/unreached anchors resolving, outside-window events falsely orphaned, invalid-config persistence blocking corrected retry, capture/backfill genesis inconsistency and coercive anchor import. Operator qualification CLI remains missing. Six repair findings are open.

Verification: 128 passed / one skipped in sandbox; remaining localhost HTTP test passed separately (129 tests total). Planning and compileall pass; diff-check fails on an extra EOF blank line and is explicitly assigned to Luna. Preserved source edits; this is a known-incomplete checkpoint, not accepted M1-03. Updated model ownership to gpt-5.6-luna/xhigh. Existing task Implement Luna build plan is idle and will receive the repair-stage prompt; coordinator recheck gates subsequent feature loops.


## 2026-09-14 — Luna repair checkpoint for DS-01 through DS-06

Implemented the audited ancestry repairs in the sole-writer repair stage. Anchor
qualification now uses structured genesis or independent-header identity checks;
unverified/runtime/deployment declarations cannot certify history. Canonical
projections preserve before-anchor and after-tip events as unresolved outside a
proven interval, while competing blocks inside that interval remain orphaned.
Capture and backfill preflight anchor binding before durable trust changes and
share genesis qualification. Added strict anchor import/restoration validation,
the bounded read-only `qualify-anchor` CLI, runbook recovery instructions and
regression/subprocess coverage. Fixed the reported extra EOF blank line.

Evidence is recorded in docs/reports/luna-repair-checkpoint.md and the repaired
diagnostic probe. The repair checkpoint is pending independent coordinator
recheck; no feature loops, live completeness gate, timed gate, model claim or
funded execution claim is made here.


## 2026-09-14 — Coordinator repair review 01

Rechecked Luna's first repair delta while its task was idle. 141 tests passed / one sandbox HTTP skip; planning, compileall and diff-check pass. Original diagnostic cases improve, but the offline qualification CLI still manufactures independent verification from supplied JSON, and a repeated backfill over a changed quiet tip selects the old stored hash. Recorded R1/R2 plus the missing recovery procedure in docs/reports/luna-repair-review-01.md. Feature loops remain gated; source changes preserved for Luna's next repair round.


## 2026-09-14 — Luna repair round 2

Repaired the coordinator's R1/R2 findings. `qualify-anchor` now performs
read-only chain-ID and exact-header reads against the configured primary RPC and
a distinct explicitly supplied independent RPC, records both header identities
and provenance, labels finality as unverified, rejects mismatches and no longer
accepts offline evidence bundles. Backfill reconciliation now selects exactly
one current-run tip header, revalidates a completed/no-op resume, and reports an
unavailable tip instead of selecting a stale stored fork. Added an immutable
source-namespace supersession link for boundary-crossing recovery while
preserving the old source.

Added regression coverage for the real two-endpoint CLI flow, mismatched
independent headers, replacement tips, no-op revalidation, tip outage and
requalification. Full suite: 143 passed / 2 sandbox skips. Coordinator
independent recheck remains required; feature loops and live/timed acceptance
gates remain closed.


## 2026-09-14 — Coordinator repair review 02

Completed independent second-round review: 143 passed / two sandbox skips, both localhost cases passed separately (145 verified); planning/compile/diff checks clean. Two-provider verification performs actual calls and fresh-tip selection is repaired. Same-checkpoint fork reproduction still loses replacement logs while acknowledging the range; nested booleans and unknown states remain accepted. Documented R3-R5 (including exportable endpoint credential hygiene) in docs/reports/luna-repair-review-02.md and requested a focused third repair round. No source edits or feature-stage dispatch by coordinator.


## 2026-09-14 — Luna repair round 3

Repaired the coordinator's R3-R5 findings. Resumed backfills now probe the
current target and acknowledged cursor boundary before inheriting a checkpoint;
changed lineage invalidates the derived projection and replays the bounded
requested range, preserving raw events from both branches. Partial resumes,
quiet tips, unchanged no-ops, provider outage and failed replay leave explicit
`needs_repair` state when coverage cannot be claimed.

Canonical resolution now uses a positive `qualified` plus reached-anchor and
gap-free invariant, with strict nested evidence types and shapes. Exportable
endpoint provenance is origin-only and strips userinfo, path/query credentials
from qualification evidence, run manifests, CLI output and errors while
transport keeps the configured URL in memory.

Added the coordinator reproduction and regression coverage for replacement-log
replay, partial cursor repair, replay failure, nested boolean/fractional
evidence, unknown resolution state and credential canaries. Feature loops and
live/timed acceptance gates remain closed pending coordinator recheck.

Verification: sandbox full suite `150 passed, 2 skipped`; both skipped loopback
tests passed separately with permitted local sockets, so all 152 collected tests
were exercised. The coordinator reproduction, planning, compileall and
whitespace checks pass.


## 2026-09-14 — Coordinator acceptance of G0

The coordinator independently rechecked the Luna repair round 3 checkpoint and
accepted G0. The reviewed repair and audit files are preserved in the
checkpoint commit; live canonical-source, timed, economic and biological/model
gates remain deferred with explicit scope. The build stage is now open at B0,
with the separate B-task catalogue still authoritative for implementation
status.


## 2026-09-14 — B0 signal contracts and B1 MaleCNS source

Implemented the versioned brain signal boundary for spot/LP entry, hold and
explicit exit operations. Predictions, research-only or later qualified manual
proposals, externally reported manual actions and actual/simulated/market
outcomes are separate records. Expiry, as-of portfolio context, model version,
evidence references and confidence calibration semantics are required; an
uncalibrated score cannot become a probability, and signing/funding remain
disabled.

Added planning validation for the 11-task brain catalogue and loop-plan
identity/dependency/reference checks. Marked B0 complete with executable
contract/config/test evidence.

Verified the user-selected official MaleCNS v1.0 release locally. The 1.05 GB
connectivity Feather and 14 MB annotation Feather match their recorded byte
counts and SHA-256 values; real Arrow schemas and pre-to-post direction were
checked. A bounded 20,000-edge subset drives a three-step sparse reservoir
smoke run, with explicit positive-sign and log1p preprocessing assumptions.
The subset is not whole-CNS coverage and does not claim a pretrained financial
model, biological memory or financial advantage. B1 is complete for the
subset/provenance contract; full-release resource/model gates remain open.


## 2026-09-14 — M1-01 source manifest guard

Added an offline validator for the pinned Robinhood Chain source manifest. It
checks read-only mode, chain identity, credential-free endpoint declarations,
Uniswap V4/Pons V2 ABI hashes and exact event-family sets, while preserving the
recorded bounded probe and its open gates. The validator and focused tests pass;
M1-01 remains IN_PROGRESS because historical code, non-graduate coverage,
provider limits and the M1-07 elapsed-time completeness gate are still real
external acceptance requirements.


## 2026-09-14 — B2 public-wallet and position observer

Added the read-only B2 observer layer. Route-aware trades and causal LP records
become exact signed atomic wallet activities with explicit confirmed, failed,
pending and unknown states. SQLite storage is idempotent across restart, keeps
payload revisions for fork/canonicality changes, and binds cursors to filter
identity so a changed lineage enters `needs_repair`. Derived LP positions mark
unknown/orphaned actions as uncertain rather than inventing ownership. Focused
observer tests pass; live wallet coverage and prospective learning gates remain
open.


## 2026-09-14 — B3 causal feedback and label maturation

Added durable prediction/outcome storage and a horizon-maturation queue. The
dataset join waits for label availability, retains observed-market and
simulated-counterfactual outcomes without requiring a personal trade, and
keeps actual manual outcomes separate. Self-label references, future labels,
target mismatches, unresolved/fork-revised outcomes and missing targets remain
visible but ineligible. Focused B3 tests pass; live zero-personal-trade
continuous learning and automatic training remain open.


## 2026-09-14 — B4 fixed-connectome laboratory

Added a checkpointable local training runner for the verified directed graph.
The `fly` recurrent path is kept fixed while matched shuffled-wiring,
random-weight, no-state and ordinary controls use the same partitions. The
runner hashes graph/config/sample identities, resumes encoded state rows,
reports held-out error and returns `waiting` for insufficient train or
held-out evidence. Tiny-graph tests and checkpoint identity checks pass;
actual labelled MaleCNS training, Windows/WSL2 resource measurement, forward
evaluation and promotion remain open.


## 2026-09-14 — B5 observed accounting boundary

Added exact-atomic reconciliation for wallet observations. Canonical confirmed
verified swaps contribute per-asset deltas; failed, pending, unknown and fork-
orphaned activity remains visible as unresolved or residual evidence. LP
ownership stays separate from spot cash flow. Focused accounting tests pass;
validated quote economics, complete LP accounting and live outcome gates remain
open.


## 2026-09-14 — B6 signal inbox and position views

Added the read-only signal inbox projection and exposed `/signals`, `/positions`
and `/training` alongside the existing dashboard. Versioned prediction/model
identity, expiry, confidence, evidence, manual-only scope and spot/LP economic
readiness are visible; stale, invalidated and unsupported proposals abstain.
Observed positions and training state are displayed without adding execution
controls. Focused API/UI checks pass; real labelled model output, economic
qualification and manual-action linkage remain open.


## 2026-09-14 — B7 manual-action linkage

Added conservative linkage from externally reported manual actions to public
wallet activity. Exact transaction identity is preferred; hashless matching
requires one compatible wallet/instrument/direction candidate in a bounded time
window, while ambiguous and missing evidence remain unresolved. The read-only
`/actions` surface exposes links without execution controls, and actual manual
outcomes remain distinct from simulated or market outcomes. Focused linkage
tests pass; live feedback and complete position-update acceptance remain open.


## 2026-09-14 — B8 candidate evaluation and registry

Added candidate-versus-active evaluation over paired forward windows and an
untouched final-test partition. Evaluation hashes dataset/final-test identity,
requires minimum window/sample evidence and records an inconclusive state when
gates fail. A persistent model registry records evaluations, consumes a final
test only once, guards promotion and supports rollback. Focused tests pass;
live forward evidence, calibration, scheduling and model promotion remain open.
