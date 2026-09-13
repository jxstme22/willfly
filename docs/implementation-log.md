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
