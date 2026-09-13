# Build task backlog

Version 1.2 | 2026-09-13 | 77 tasks

The JSON catalogue is authoritative. DONE requires acceptance evidence and completed prerequisites; existing code and fixture coverage are tracked separately. Target paths may include planned files.

## P0 - Specification and access

### P0-01 - Initialize the research workspace

**Status:** DONE | **Owner role:** Platform | **Depends on:** None

**Target paths:** `pyproject.toml`, `src/willfly/`, `tests/`, `.gitignore`

Create the package, local environment, lockfile, formatting and test commands. Ignore datasets, credentials and model artifacts. Add a tiny offline CLI entry point and document the supported Python version.

**Done when:** A fresh environment runs the CLI and fixture tests; repository scanning finds no credential values or generated datasets.

**Evidence:** pyproject.toml; requirements-dev.lock; src/willfly/cli.py; tests/test_cli.py

### P0-02 - Pin network and source deployments

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P0-01

**Target paths:** `configs/sources/`, `docs/source-matrix.md`

Verify chain identity, V4 deployment, ABI and creation block from official protocol sources plus chain evidence. Compare Pons versions and pools.trade; select one launch contract/version with creation coverage, including non-graduates. Record provider limits, history and licenses.

**Done when:** Manifest contains evidence URLs, addresses, ABI hashes, deployment blocks and network checks. At least ten raw examples per supported event family decode; unknown deployment means gate remains open.

**Evidence:** configs/sources/robinhood-chain-v0.1.json; configs/sources/uniswap-v4-events.abi.json; docs/source-matrix.md; docs/implementation-log.md

### P0-03 - Validate read access and provider budget

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P0-02

**Target paths:** `src/willfly/adapters/`, `docs/provider-budget.md`

Probe read RPC/archive capability and candidate event API with bounded requests. Measure historical depth, pagination, rate limits, delay and error behavior. Specify daily request/storage estimates and chosen plan without purchasing a subscription. Include RHTrenches and Mezzanine in the source matrix: supported API/export, usage terms, cohort coverage, history, timestamps, pricing and failure behavior. Treat RHTrenches UI observations and Mezzanine advertised features separately from tested integration evidence. Do not bypass region restrictions or buy credits; optional scanner access must not block native capture.

**Done when:** Redacted probe report distinguishes tested endpoints from documented ones; a 24-hour sample budget is estimated; unavailable keys are explicit blockers rather than silently mocked results. Each scanner has a dated tested/documented/unavailable verdict and fallback. No undocumented endpoint, private stream or claimed UI latency is presented as a validated API or measured service guarantee.

**Evidence:** docs/provider-budget.md; configs/sources/robinhood-chain-v0.1.json; docs/implementation-log.md

### P0-04 - Define canonical data contracts

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P0-02

**Target paths:** `src/willfly/domain/`, `docs/data-contracts.md`

Specify raw events, pool identity, launches, observations and lineage. Preserve exact quantities, ETH/WETH identity, V4 pool IDs, timestamps, canonicality and unknown values. Version schemas and reject ambiguous fields. Specify TradeEvidence, VendorAssessment and WalletCohort records. Separate verified swaps, transfers, gifts/airdrops and ambiguous activity; preserve exact payment legs, quote currency, valuation method, estimated USD status, reason flags, method version, as-of time and retrieval time. Cohort membership and wallet relationships carry observation time and uncertainty.

**Done when:** Schema fixtures round-trip exact integer quantities and include V3/V4 identity examples, missing metadata and orphaned logs; ambiguous identity fails validation. Fixtures represent a token receipt without payment, an estimated USD amount, a genuine multi-hop swap, stale vendor flags and unknown cohort history. Transfer value cannot validate actual spend; missing vendor history cannot become an earlier observation.

**Evidence:** src/willfly/domain/contracts.py; docs/data-contracts.md; tests/fixtures/cases.json; tests/test_contracts.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P0-05 - Freeze the first experiment proposal

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P0-03, P0-04

**Target paths:** `configs/experiments/initial.yaml`, `docs/evaluation-contract.md`

Record eligibility, decision interval, target horizons, capital scenarios, splits, drawdown constraints, inference rules and data-quality exclusions. Reserve a calibration sample and untouched holdout; document changes before holdout access. Predeclare the follower-outcome experiment: select wallet cohorts using only prior information, record observable signal arrival, and evaluate our executable entry and exit after costs. Compare genuine net flow with unverified activity and keep the fly-model comparison independent of added data.

**Done when:** Versioned specification includes every metric and gate from the roadmap, known feasibility dependencies and a deterministic split construction rule; no test result is used for specification selection. The proposal distinguishes leader PnL from follower outcomes and explicitly treats unobserved cohort history or missing execution state as an inference limit.

**Evidence:** configs/experiments/initial.yaml; docs/evaluation-contract.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P0-06 - Create offline fixtures and v0.1 gate

**Status:** IN_PROGRESS | **Owner role:** QA | **Depends on:** P0-04

**Target paths:** `tests/fixtures/`, `docs/runbooks/v0.1.md`

Prepare provenance-tagged observed fixtures where available and explicitly synthetic failure cases. Encode the seven-step observatory demo and distinguish synthetic verification from live evidence. Add swap-versus-transfer fixtures, including a flagged BUY with no readable cash leg, multiple recipients in one transaction, duplicate vendor/chain observations and scanner outage. Synthetic examples illustrate failure modes without asserting a specific live token is malicious.

**Done when:** Fixture manifest identifies origin and hashes; v0.1 checklist covers disconnected source, duplicate delivery, malformed log, native asset and fork cases. Fixture provenance and expected classifications are explicit; a dashboard label alone cannot pass payment-evidence checks.

**Evidence:** tests/fixtures/manifest.json; tests/fixtures/cases.json; docs/runbooks/v0.1.md; docs/implementation-log.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

## P1 - Recorder and recovery

### P1-01 - Implement raw storage and metadata

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P0-01, P0-04

**Target paths:** `src/willfly/storage/`

Write compressed append-only raw batches with hashes and a transactional SQLite checkpoint/manifest store. Define partition naming and atomic batch publication.

**Done when:** Interruption before and after checkpoint commit does not lose acknowledged events; corrupt/truncated batches are detected and recoverable from the last good checkpoint.

**Evidence:** src/willfly/storage/raw.py; src/willfly/storage/__init__.py; tests/test_storage.py; docs/implementation-log.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P1-02 - Implement Robinhood log capture

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P0-03, P0-06, P1-01

**Target paths:** `src/willfly/adapters/robinhood_rpc.py`, `src/willfly/ingest/capture.py`

Capture configured contracts through supported subscriptions or bounded polling, recording arrival time and chain context. Keep subscription mechanics distinct from the sequencer feed; enforce read-only operation.

**Done when:** Recorded event batches match sample RPC receipts; throttling/backoff works; wrong-chain endpoint is rejected; no signing or transaction-send method is exposed.

**Evidence:** src/willfly/adapters/robinhood_rpc.py; src/willfly/ingest/capture.py; tests/test_rpc_capture.py; configs/sources/robinhood-chain-v0.1.json; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P1-03 - Decode pool and trading events

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P1-02

**Target paths:** `src/willfly/adapters/protocols/`

Decode initialization, swaps and liquidity changes for supported V4 paths. Implement exact currency ordering and pool identity; flag unsupported hooks instead of treating all V4 behavior as standard. Join supported swap logs with transaction receipts and relevant transfer/native-value evidence to classify trade origin. Reconcile multi-hop routes without counting each leg as a separate wallet purchase. Preserve third-party labels as source claims; quarantine or mark unknown when cash-flow attribution cannot be resolved.

**Done when:** Known receipts decode deterministically with raw lineage; two pools sharing a manager remain separate; malformed and unsupported events enter quarantine. No-payment receipts and airdrops never inflate verified buy counts or spend; duplicate source observations deduplicate while keeping lineage. Valid routed swaps pass; unresolved attribution stays unknown.

**Evidence:** src/willfly/adapters/protocols/v4.py; src/willfly/adapters/protocols/__init__.py; tests/test_v4_protocols.py; configs/sources/robinhood-chain-v0.1.json; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P1-04 - Decode one launchpad lifecycle

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P0-02, P1-02

**Target paths:** `src/willfly/adapters/launchpad.py`

Implement the selected version's creation and lifecycle events. Link pools only using verifiable evidence; retain launches without pool creation and separate first seen from creation time.

**Done when:** Fixtures cover trading and non-trading launches, late discovery and version mismatch; origin confidence and unknown history are visible.

**Evidence:** src/willfly/adapters/launchpad.py; configs/sources/pons-v2-events.abi.json; configs/sources/robinhood-chain-v0.1.json; tests/test_launchpad.py; docs/implementation-log.md

### P1-05 - Implement resumable backfill

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P1-03, P1-04

**Target paths:** `src/willfly/ingest/backfill.py`

Fetch bounded historical ranges with adaptive page sizes, pagination completeness checks and checkpoints. Merge overlap with live capture without losing provenance.

**Done when:** Stopping mid-range and resuming yields the same logical records as uninterrupted replay; truncated pages and provider range limits are surfaced.

**Evidence:** src/willfly/ingest/backfill.py; tests/test_backfill.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P1-06 - Implement canonicalization and fork recovery

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P1-05

**Target paths:** `src/willfly/ingest/canonicalize.py`

Track block hashes/parents and provisional versus confirmed projections using the verified network policy. Roll back derived state on fork changes, retaining raw orphan evidence.

**Done when:** A multi-block fork fixture produces the expected canonical dataset and repaired checkpoints; orphaned events never remain in canonical counts or training snapshots.

**Evidence:** src/willfly/ingest/canonicalize.py; tests/test_canonicalize.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P1-07 - Add supervision and quality telemetry

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P1-02, P1-06

**Target paths:** `src/willfly/ingest/supervisor.py`, `src/willfly/ingest/quality.py`

Measure arrival delay, block lag, gap ranges, quarantine counts, retries and storage growth. Add reconnect, bounded retry and disk-space behavior; redact credentials from logs.

**Done when:** Disconnect/reconnect and storage-failure tests produce explicit degraded states and successful gap recovery; health cannot report green while a gap is unresolved.

**Evidence:** src/willfly/ingest/quality.py; src/willfly/ingest/supervisor.py; tests/test_quality.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P1-08 - Run recorder coverage and recovery audit

**Status:** IN_PROGRESS | **Owner role:** QA | **Depends on:** P1-03, P1-04, P1-05, P1-06, P1-07

**Target paths:** `src/willfly/evaluation/coverage.py`, `artifacts/coverage/`

Compare configured source intervals with separately fetched canonical logs. Run duplicate, crash and fork drills. Record numerator/denominator, provider independence and exclusions.

**Done when:** v0.1 capture gate is measured over 72 hours: discovery recall target, gap accounting and recovery checks reported. Any unmet condition remains an explicit gate failure.

**Evidence:** src/willfly/evaluation/coverage.py; tests/test_coverage.py; docs/implementation-log.md

## P2 - Observatory v0.1

### P2-01 - Build discovery and lifecycle projections

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P1-08

**Target paths:** `src/willfly/features/discovery.py`

Materialize launches, pools, trading status and evidence-backed lifecycle transitions. Keep inactive launches, pools without known launch origin and late-indexed records.

**Done when:** Counts reconcile to raw canonical events; launch time, pool time and first-observed time remain separate and queryable.

**Evidence:** src/willfly/features/discovery.py; tests/test_features.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P2-02 - Build causal token timelines

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P2-01

**Target paths:** `src/willfly/features/timelines.py`

Calculate trailing trades, flow and liquidity summaries using event and arrival cutoffs. Include available wallet aggregates, missingness and staleness. Do not claim full holder coverage from partial transfer history. Expose verified net flow separately from estimated or ambiguous activity. Version tracked-wallet membership and relationship evidence as of observation. Report cohort coverage; multiple wallets or shared recipients are not proof of independent buyers. Preserve the underlying suspicious events.

**Done when:** Appending future data cannot change an earlier as-of snapshot except through a new explicitly versioned correction; missing history produces unknown features. Future leaderboard membership cannot change earlier features. A planted receipt cannot raise verified buying pressure; an external cohort is never labeled chainwide demand.

**Evidence:** src/willfly/features/timelines.py; tests/test_features.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P2-03 - Implement portable dataset export

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P2-02

**Target paths:** `src/willfly/storage/export.py`

Export canonical Parquet partitions plus schema, source/config hashes, gaps and quality report. Keep API-specific payloads traceable but outside model contracts.

**Done when:** Re-import reproduces row counts, logical keys and feature hashes; large integer identities and quantities survive round-trip.

**Evidence:** src/willfly/storage/export.py; requirements-export.lock; tests/test_export.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P2-04 - Expose read-only inspection API and CLI

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P2-03

**Target paths:** `src/willfly/api/`, `src/willfly/cli.py`

Implement doctor, capture, backfill, audit, export and serve commands. Provide paginated launches, token timeline, pool and health endpoints, bound locally by default.

**Done when:** CLI commands produce run IDs and useful exit codes; endpoint integration tests cover pagination, invalid identity and degraded data. No trading route exists.

**Evidence:** src/willfly/api/server.py; src/willfly/cli.py; tests/test_api.py; tests/test_cli.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P2-05 - Build the observatory interface

**Status:** IN_PROGRESS | **Owner role:** Product | **Depends on:** P2-04

**Target paths:** `src/willfly/ui/`

Create launch list, token timeline and quality views. Show source time, arrival time, stale/missing fields and explorer evidence links. Add filters for lifecycle and supported protocol. Show trade-origin category, valuation method and vendor reason flags with evidence timestamps. Provide explicit display filters and visible excluded counts without deleting raw rows or changing training eligibility implicitly.

**Done when:** The demo can inspect one active launch and one non-graduate, trace an event to evidence and identify a data outage without reading logs. A reviewer can distinguish a real swap from a flagged receipt and an estimated value, and can inspect excluded events and stale vendor assessments.

**Evidence:** src/willfly/ui/dashboard.py; tests/test_ui.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P2-06 - Package and accept Observatory v0.1

**Status:** IN_PROGRESS | **Owner role:** QA | **Depends on:** P2-05, P1-08

**Target paths:** `docs/runbooks/observatory.md`, `artifacts/releases/v0.1/`

Document install, source setup, capture/restart, audit/export and recovery. Run the full v0.1 demo from a clean local environment and publish a release evidence bundle.

**Done when:** Another local process follows the runbook and reproduces the export; phase gates pass or the release is explicitly labeled a partial pool-only prototype.

**Evidence:** docs/runbooks/observatory.md; pyproject.toml; requirements-export.lock; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

## P3 - Replay and labels

### P3-01 - Implement a deterministic replay scheduler

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P2-06

**Target paths:** `src/willfly/replay/scheduler.py`

Replay by observed availability, with event ordering, strategy ticks and execution delay. Separate historical event timestamps from reconstructed availability when actual arrival data is unavailable.

**Done when:** Repeated fixture runs produce identical observations and action ordering; the strategy cannot inspect future events or corrected data before availability.

**Evidence:** src/willfly/replay/scheduler.py; tests/test_replay_core.py; docs/implementation-log.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P3-02 - Implement the portfolio ledger

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P3-01

**Target paths:** `src/willfly/replay/ledger.py`

Track exact asset balances, trades, gas, protocol/platform fees, marks and residual inventory. Separate realized cash flows from modeled liquidation value and include failed actions.

**Done when:** Asset conservation and hand-calculated multi-action fixtures reconcile; deposits cannot be counted as profit and fees are not deducted twice.

**Evidence:** src/willfly/replay/ledger.py; tests/test_replay_core.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P3-03 - Implement supported quotes and fill assumptions

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P3-02

**Target paths:** `src/willfly/replay/execution.py`

Model supported pool mechanics, transaction delay and costs at the chosen capital sizes. Use archive state where available; label approximations. Exclude unsupported hooks from executable claims while retaining their observed episodes. Support follower replay from the signal receipt time plus processing/submission delay. Requote the proposed position at that time and simulate its exit under the same shared ledger. Keep observed leader economics separate from hypothetical follower economics.

**Done when:** Known transaction examples reconcile within declared tolerances; no route, shallow depth, revert, missing state and price changes generate explicit outcomes. A leader-profitable but follower-unprofitable fixture is handled correctly; missing historical depth cannot be replaced by leader fill prices or current marks.

**Evidence:** src/willfly/replay/execution.py; tests/test_execution.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P3-04 - Implement causal training labels

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P3-03, P0-05

**Target paths:** `src/willfly/features/labels.py`

Generate 1/5/15-minute outcome labels with a primary 5-minute task after calibration. Record entry/exit feasibility, net returns and adverse excursions. Distinguish unresolved observations from actual losses.

**Done when:** Every label links to its horizon and fill assumptions; failed and unsellable episodes remain represented; incomplete horizons are marked censored.

**Evidence:** src/willfly/features/labels.py; tests/test_labels.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P3-05 - Implement portfolio constraints and candidate allocation

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P3-02, P0-05

**Target paths:** `src/willfly/policies/constraints.py`

Enforce simulation capital, fixed entry allocation, concurrent-position limit, no leverage and no adding. Resolve simultaneous candidates deterministically against one shared cash ledger.

**Done when:** Competing opportunities cannot spend the same cash; rejected actions carry reasons; fixtures exercise all caps and ties.

**Evidence:** src/willfly/policies/constraints.py; tests/test_constraints.py; docs/implementation-log.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P3-06 - Implement leakage-resistant split manifests

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P3-04

**Target paths:** `src/willfly/evaluation/splits.py`

Create chronological calibration/train/validation/test manifests, purge overlapping label horizons and group related episodes where justified. Fit normalization only on training data. Freeze wallet selection using pre-window information, preserve cohort joins/removals as observed, and retain failed or delisted tokens. Never backfill a current leaderboard into historical membership.

**Done when:** Automated checks reject overlapping labels and future-derived features; held-out partitions are immutable and their hashes recorded before tuning. A future successful wallet cannot enter an earlier cohort; insufficient historical membership requires prospective evaluation.

**Evidence:** src/willfly/evaluation/splits.py; tests/test_splits.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P3-07 - Audit replay mechanics and cost stress

**Status:** IN_PROGRESS | **Owner role:** QA | **Depends on:** P3-03, P3-04, P3-05, P3-06

**Target paths:** `tests/replay/`, `artifacts/replay-audit/`

Reconcile at least 20 observed transaction examples spanning supported action paths, plus adverse synthetic fixtures. Evaluate increased delay, fees, slippage and incomplete liquidity. Audit follower timing and liquidation assumptions and compare verified-only flow against contaminated activity fixtures. Record scanner/data charges in full-system economics using an explicit allocation rule.

**Done when:** An audit lists exact versus approximate paths, tolerances and residual discrepancies; unsupported paths cannot silently pass as validated fills. Leader PnL is never the follower label, suspicious-event exclusions are counted, and shared data fees are neither omitted nor charged twice.

**Evidence:** src/willfly/evaluation/replay_audit.py; tests/test_replay_audit.py; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P3-08 - Publish the replay dataset and evidence bundle

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P3-07

**Target paths:** `artifacts/datasets/`, `docs/runbooks/replay.md`

Package dataset, label/split configs, accounting evidence and reproduction commands. Define a minimum adequate sample after observed episode counts and correlation analysis.

**Done when:** An independent local rerun reconstructs labels and ledgers; insufficient sample or historical state is explicitly inconclusive and blocks profitability claims.

**Evidence:** src/willfly/evaluation/replay_bundle.py; tests/test_replay_audit.py; docs/runbooks/replay.md; docs/implementation-log.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

## P4 - Baseline policies

### P4-01 - Implement simple baseline strategies

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P3-08

**Target paths:** `src/willfly/policies/baselines.py`

Implement idle cash, fixed-horizon hold, deterministic confirmation/momentum and a simple flow/liquidity filter with predeclared parameters and shared constraints. Add a deterministic tracked-wallet-following baseline when causal cohort evidence is available. Freeze selection and trigger rules before evaluation; account for signal latency, executable depth, fees and exits under the shared ledger.

**Done when:** Every strategy uses identical information cutoffs and costs; a fixture demonstrates the intended trigger and actual allocation behavior. Report follower returns separately from vendor/leader PnL; unavailable cohort data yields an explicit unavailable benchmark, not fabricated trades.

**Evidence:** src/willfly/policies/baselines.py; tests/test_baselines.py; docs/results/baseline-review.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P4-02 - Implement conventional prediction baselines

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P3-08

**Target paths:** `src/willfly/models/conventional.py`

Train regularized raw-feature models and one compact ordinary recurrent model. Use the same target family and feature information as the proposed neural experiment.

**Done when:** Training is reproducible from hashes and seeds; recurrent state cannot leak between unrelated token episodes or across split boundaries.

**Evidence:** src/willfly/models/conventional.py; tests/test_baselines.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P4-03 - Define common prediction-to-action mapping

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P4-01, P4-02

**Target paths:** `src/willfly/policies/prediction.py`

Map predictions and uncertainty to enter/hold/exit decisions under shared fixed-size rules. Select thresholds only on validation and retain watch as an action.

**Done when:** Both learned model families run under the same decision rule; changing model predictions cannot bypass constraints.

**Evidence:** src/willfly/policies/prediction.py; tests/test_baselines.py

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P4-04 - Implement experiment tracking and budgets

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P4-02

**Target paths:** `src/willfly/evaluation/runs.py`

Record source/code/data/config hashes, seeds, training time, parameter counts, search trials and artifacts. Enforce comparable tuning opportunities and log failed runs.

**Done when:** A run can be reconstructed without undocumented manual settings; search-budget overrun is detected and failed models remain in the experiment record.

**Evidence:** src/willfly/evaluation/runs.py; tests/test_baselines.py

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P4-05 - Implement metrics and paired uncertainty

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P4-03, P4-04

**Target paths:** `src/willfly/evaluation/metrics.py`

Calculate net and excess return, drawdown, tail outcomes, failure rates, turnover, calibration and exposure. Implement paired block-bootstrap with episode grouping and locked resampling rules.

**Done when:** Hand-calculated fixtures verify metrics; seed repetitions are not treated as independent markets; insufficient independent blocks are flagged.

**Evidence:** src/willfly/evaluation/metrics.py; tests/test_baselines.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P4-06 - Run walk-forward evaluation and stresses

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P4-05

**Target paths:** `artifacts/baselines/`

Tune on permitted windows, freeze candidates, then evaluate locked windows with cost and delay stresses. Record each regime rather than selecting only favorable launches.

**Done when:** All predeclared periods and capital scenarios appear; the strongest practical baseline is selected before the neural holdout comparison.

**Evidence:** src/willfly/evaluation/walk_forward.py; docs/results/baseline-review.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P4-07 - Accept baseline laboratory v0.2

**Status:** IN_PROGRESS | **Owner role:** QA | **Depends on:** P4-06

**Target paths:** `docs/results/baseline-review.md`

Review accounting, sample adequacy, inference and reproducibility. Document whether any candidate shows net opportunity and which data limits remain.

**Done when:** Gate report states pass, revise or inconclusive; no positive narrative substitutes for missing costs, failures or holdout evidence.

**Evidence:** docs/results/baseline-review.md

## P5 - Connectome experiment

### P5-01 - Pin and validate connectome data

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P4-07

**Target paths:** `configs/connectome/`, `src/willfly/models/connectome/ingest.py`

Select exact MaleCNS release and review attribution/license terms and dependencies. Download only needed tables; hash and validate IDs, annotations and curated-neuron filters.

**Done when:** Manifest links every input to its release and license; no floating-point ID conversion; counts and excluded records reconcile.

**Evidence:** configs/connectome/manifest.json; src/willfly/models/connectome/ingest.py; docs/results/neural-review.md

### P5-02 - Build the sparse graph and controls

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-01

**Target paths:** `src/willfly/models/connectome/graph.py`

Specify subnetwork selection, orientation, aggregation, sign assumptions and weight transforms. Build matched random and shuffled controls retaining declared degree/sign/weight properties where feasible.

**Done when:** Toy directed graph verifies orientation; graph statistics and matching deviations are reported; controls differ only in documented properties.

**Evidence:** src/willfly/models/connectome/graph.py; tests/test_neural.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P5-03 - Implement stateful reservoir dynamics

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-02

**Target paths:** `src/willfly/models/reservoir.py`

Use a compact rate-based recurrent model initially, with explicit decay, input scale and stability controls. Preserve state per episode and specify warm-up/reset behavior. Benchmark sparse memory and runtime.

**Done when:** Impulse and constant-input tests expose decay and stability; no accidental dense full-brain matrix allocation; model remains finite on training input stress.

**Evidence:** src/willfly/models/reservoir.py; tests/test_neural.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P5-04 - Train the frozen-reservoir readout

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-03, P4-04

**Target paths:** `src/willfly/models/readout.py`

Train a regularized output layer on reservoir activity with identical labels and split rules. Tune only declared readout/reservoir hyperparameters; keep recurrent weights fixed during training.

**Done when:** Before/after graph hashes match; readout parameters change; held-out prediction generation uses only frozen training artifacts and causal activity.

**Evidence:** src/willfly/models/readout.py; tests/test_neural.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P5-05 - Run matched model comparisons

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-04, P4-06

**Target paths:** `artifacts/neural/comparisons/`

Compare fly graph, random reservoir, shuffled graph, raw-feature readout and ordinary recurrent model with at least five seeds and comparable budgets.

**Done when:** Same dataset, policy and ledger used throughout; performance, compute and uncertainty are reported for every predeclared comparator.

**Evidence:** src/willfly/evaluation/neural.py; tests/test_neural.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P5-06 - Run contribution and state ablations

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-05

**Target paths:** `src/willfly/evaluation/ablations.py`

Reset state, remove the reservoir, perturb input mapping and graph organization. Preserve fair retuning rules and report each intervention's scope.

**Done when:** Results distinguish useful recurrence, feature effects and biological topology; conclusions cannot attribute surviving wrapper performance to the removed component.

**Evidence:** src/willfly/evaluation/neural.py; tests/test_neural.py; docs/results/neural-review.md

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P5-07 - Apply neural progression gate

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-06

**Target paths:** `docs/results/neural-review.md`

Apply predeclared return, drawdown, multi-window and uncertainty criteria. Assess sensitivity to capital, delay and graph assumptions; report negative and inconclusive results.

**Done when:** Signed-off research note chooses retain, revise or reject the fly component with traceable evidence; internal fine-tuning is not automatically triggered.

**Evidence:** docs/results/neural-review.md

### P5-08 - Package neural experiment v0.3

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P5-07

**Target paths:** `artifacts/models/`, `docs/runbooks/neural.md`

Save graph manifest, model/readout state, feature config, model card and inference interface. Document data licenses and limits, including lack of demonstrated biological fidelity in the market task.

**Done when:** Reloaded model reproduces reference predictions and action ledger within declared numerical tolerance on the same environment.

**Evidence:** src/willfly/models/package.py; tests/test_neural.py; docs/runbooks/neural.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

## P6 - LP data and LLM integration

### P6-01 - Validate LP Agent read coverage

**Status:** IN_PROGRESS | **Owner role:** Data | **Depends on:** P4-07

**Target paths:** `src/willfly/adapters/lpagent.py`, `docs/integrations/lpagent.md`

Probe Robinhood V3/V4 read endpoints, authentication, paging, freshness and field meanings. Reconcile native ETH/WETH handling and vendor PnL against raw evidence.

**Done when:** Endpoint matrix separates tested, missing and unsupported features; Solana-only transaction routes are not presented as Robinhood execution support.

**Evidence:** src/willfly/adapters/lpagent.py; docs/integrations/lpagent.md; tests/test_hybrid.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P6-02 - Build causal LP, trader and scanner observations

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P6-01

**Target paths:** `src/willfly/features/lp_behavior.py`, `src/willfly/adapters/rhtrenches.py`, `src/willfly/adapters/mezzanine.py`

Record wallet position changes, range movement and liquidity withdrawal with arrival times. Avoid selecting wallets based on future leaderboard outcomes; express incomplete coverage. Add optional tracked-trader and scanner read adapters only after the source matrix establishes supported access and terms. Normalize RHTrenches observations and Mezzanine assessments independently; preserve raw payloads, timestamps, cohort scope and method versions. Implement bounded polling/caching where supported and an unavailable-source fallback; browser inspection is not a production integration.

**Done when:** Feature fixtures prevent future ranking leakage; wallet identities are observations rather than unverified claims of skill or common ownership. Adapter conformance fixtures cover absent APIs, stale flags, rate limits, outages and duplicate observations. Test evidence or a documented unavailable outcome exists for each source; no-source operation works and missing integrations are not claimed complete.

**Evidence:** src/willfly/features/lp_behavior.py; src/willfly/adapters/rhtrenches.py; src/willfly/adapters/mezzanine.py; tests/test_hybrid.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P6-03 - Define text evidence and LLM extraction

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P4-07

**Target paths:** `src/willfly/adapters/text_sources.py`, `src/willfly/features/text_schema.py`

Choose accessible public sources and a versioned extraction schema for claims, narrative, contradictions, uncertainty and source spans. Archive only permitted content with publication and retrieval times.

**Done when:** A labeled calibration set checks extraction accuracy and unsupported claims; missing publication time or evidence is explicit rather than fabricated.

**Evidence:** src/willfly/adapters/text_sources.py; src/willfly/features/text_schema.py; tests/test_hybrid.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P6-04 - Implement bounded LLM enrichment

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P6-03

**Target paths:** `src/willfly/features/llm.py`

Use retrieval, schema validation, caching, retries and per-run request/token budgets. Treat external content as untrusted data. Record model/prompt versions; provide a no-LLM fallback.

**Done when:** Invalid outputs, hostile instructions, timeouts and budget exhaustion cannot change permissions or block the numerical decision path; source-backed output survives schema checks.

**Evidence:** src/willfly/features/llm.py; tests/test_hybrid.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P6-05 - Audit historical contamination

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P6-04, P3-06

**Target paths:** `docs/results/llm-contamination.md`

Evaluate identity masking and time-bounded retrieval. Separate extraction labels from market outcomes; do not use present-day model knowledge as historical evidence.

**Done when:** Audit identifies usable retrospective features and those requiring prospective evaluation; no LLM-created profit labels enter training.

**Evidence:** src/willfly/evaluation/contamination.py; docs/results/llm-contamination.md; tests/test_hybrid.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P6-06 - Run feature and architecture factorial tests

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P5-08, P6-02, P6-05

**Target paths:** `artifacts/hybrid/`

Compare market-only, plus LP, plus text, and both feature sets across ordinary and fly-derived candidates. Charge data/LLM costs and measure added delay. Separately ablate tracked-wallet behavior, vendor contract-risk flags and social-graph features before combining them with LP or LLM features. Test whether confirmed demand persists after signal arrival. Avoid conflating external data gains with fly topology, and report unavailable source experiments explicitly.

**Done when:** Marginal contributions are reported separately; a benefit from additional data is not misattributed to biological wiring; invalid historical LLM tests are marked unresolved. Results include a no-scanner baseline, cost/latency effects and coverage limitations. A vendor safety score is neither a profit target nor ground-truth contract safety.

**Evidence:** src/willfly/evaluation/factorial.py; docs/results/hybrid-review.md; tests/test_hybrid.py

### P6-07 - Package evidence-backed decision inspection

**Status:** IN_PROGRESS | **Owner role:** Product | **Depends on:** P6-06, P2-05

**Target paths:** `src/willfly/ui/decisions/`, `docs/results/hybrid-review.md`

Show observations, predictions, constraint outcomes and source citations for recorded decisions. Use LLM prose only to summarize recorded evidence, with uncertainty visible.

**Done when:** A reviewer can reproduce why an action was permitted and inspect evidence; explanations do not claim hidden neural motives or unverified causal intent.

**Evidence:** src/willfly/ui/decisions/inspect.py; docs/results/hybrid-review.md; tests/test_hybrid.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

## P7 - Selective LP laboratory

### P7-01 - Select and verify an LP pool family

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P3-08, P4-07

**Target paths:** `configs/lp/`, `docs/lp-scope.md`

Choose one supported V3 or V4 family from verified deployment and hook behavior. Document position contracts, fee rules, supported actions, required historical state and exit constraints.

**Done when:** Source/bytecode evidence and observed receipts support the selected mechanics; unknown hooks or unavailable state block that family rather than being approximated as standard.

**Evidence:** configs/lp/scope.json; docs/lp-scope.md

### P7-02 - Implement position and fee replay

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P7-01

**Target paths:** `src/willfly/replay/lp_positions.py`

Model tick rounding, active liquidity, fee growth, range crossing and token quantities. State the small-position counterfactual assumption and its capacity limits.

**Done when:** Hand-calculated positions and observed checkpoints reconcile; out-of-range positions accrue only fees justified by the actual supported path.

**Evidence:** src/willfly/replay/lp_positions.py; tests/test_lp.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P7-03 - Implement LP lifecycle accounting

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P7-02, P3-02

**Target paths:** `src/willfly/replay/lp_execution.py`

Account for acquisition, opening, fee collection, resizing, removal and final conversion, including gas/platform costs and residual tokens. Model failure and unsupported exit behavior.

**Done when:** Complete base-asset-to-base-asset cycles reconcile; displayed LP PnL is not substituted for portfolio profit; IL/LVR diagnostics are not double-subtracted.

**Evidence:** src/willfly/replay/lp_execution.py; tests/test_lp.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P7-04 - Build restricted LP baseline policies

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P7-03

**Target paths:** `src/willfly/policies/lp_baselines.py`

Compare fixed wide range, a simple volatility-based range and idle/spot alternatives. Initially use fixed allocation and a small discrete range set with minimum dwell time.

**Done when:** All policies share starting capital and recorded price exposure benchmarks; high nominal APR alone cannot trigger a favorable evaluation.

**Evidence:** src/willfly/policies/lp_baselines.py; tests/test_lp.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P7-05 - Add LP as a competing policy action

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P7-04, P6-07

**Target paths:** `src/willfly/policies/mode_selection.py`

Allow spot, selected LP or idle based on the same information cutoff and shared portfolio. Charge mode-switching costs and enforce supported-pool constraints.

**Done when:** Mode changes preserve inventory and cash; unsupported pools cannot receive LP actions; no double allocation across spot and LP engines.

**Evidence:** src/willfly/policies/mode_selection.py; tests/test_lp.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P7-06 - Stress LP economics and counterfactuals

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P7-05

**Target paths:** `artifacts/lp/stress/`

Evaluate directional moves, depleted liquidity, range churn, higher fees/delay, hook-related exit costs and greater position sizes. Separate observed from modeled behavior.

**Done when:** Report includes failure and sensitivity cases plus capacity limits; performance that disappears under plausible costs is rejected or labeled inconclusive.

**Evidence:** src/willfly/evaluation/lp_stress.py; docs/results/lp-audit.md; tests/test_lp.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P7-07 - Audit LP replay and decisions

**Status:** IN_PROGRESS | **Owner role:** QA | **Depends on:** P7-06

**Target paths:** `tests/lp/`, `docs/results/lp-audit.md`

Reconcile sampled historical positions and complete lifecycle fixtures; inspect contract-specific exceptional paths and fee attribution independently of the model.

**Done when:** No unresolved accounting discrepancy in supported cases; unsupported behavior is documented and excluded from claimed execution coverage.

**Evidence:** docs/results/lp-audit.md; tests/test_lp.py

### P7-08 - Decide LP eligibility for shadow

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P7-07

**Target paths:** `docs/results/lp-review.md`

Compare selective LP with spot and idle under the registered metric, exposure and drawdown rules. Publish the outcome even if LP adds no value.

**Done when:** Gate explicitly enables named LP families or leaves LP disabled; spot shadow remains independently eligible.

**Evidence:** docs/results/lp-review.md

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

## P8 - Prospective shadow agent

### P8-01 - Freeze a prospective shadow configuration

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P6-07

**Target paths:** `configs/shadow/`, `docs/shadow-protocol.md`

Select the best evidence-supported model, which may be ordinary, and freeze feature/model/source versions and capital rules. Enable LP only after P7-08.

**Done when:** Config hash and start time are recorded before observation; study requires 14 days and 200 eligible launches, with extensions for inadequate coverage.

**Evidence:** configs/shadow/config.json; src/willfly/shadow/config.py; docs/shadow-protocol.md; tests/test_shadow.py

### P8-02 - Implement live hypothetical decision loop

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P8-01

**Target paths:** `src/willfly/shadow/runner.py`

Use actual arrival timestamps, shared portfolio constraints and modeled execution to record proposed actions. Keep signing/broadcast absent; persist decision checkpoints.

**Done when:** Shadow runs across restarts without duplicate hypothetical orders; each record is labeled hypothetical and traceable to received observations.

**Evidence:** src/willfly/shadow/runner.py; src/willfly/cli.py; tests/test_shadow.py; tests/test_cli.py

**Review note:** Acceptance reopened by Astra audit: fixture coverage is retained, but integration, economic correctness or evidence gates remain incomplete. See docs/reports/astra-deep-audit.md and the mapped next-build tasks.

### P8-03 - Implement degraded-mode behavior

**Status:** IN_PROGRESS | **Owner role:** Platform | **Depends on:** P8-02

**Target paths:** `src/willfly/shadow/health.py`

On stale or contradictory data, block new hypothetical entries and record the prescribed management behavior for existing simulated positions. Track decision availability and missed deadlines.

**Done when:** Outage drills show explicit pause/degradation and recovery; unknown execution state is never reported as a successful exit.

**Evidence:** src/willfly/shadow/health.py; tests/test_shadow.py

**Review note:** Existing implementation evidence is retained. Full task acceptance awaits incomplete prerequisite evidence; this is not a claim that its code must be rewritten.

### P8-04 - Run the prospective observation window

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P8-03

**Target paths:** `artifacts/shadow/`

Collect the frozen study, including adverse episodes and all excluded intervals. Track latency, decision availability, provider costs and modeled performance.

**Done when:** Minimum duration/episode requirements and 99% healthy-interval decision availability are measured; unmet targets or source gaps remain visible.

**Evidence:** src/willfly/evaluation/shadow.py; artifacts/shadow/README.md; docs/results/shadow-review.md

### P8-05 - Reconcile shadow against replay assumptions

**Status:** IN_PROGRESS | **Owner role:** Quant | **Depends on:** P8-04

**Target paths:** `docs/results/shadow-review.md`

Compare live availability, quotes and hypothetical fills against historical assumptions; quantify drift, missed opportunities and data revisions.

**Done when:** Evidence explains material differences and applies cost stresses; prospective results are not represented as funded returns.

**Evidence:** src/willfly/evaluation/shadow.py; docs/results/shadow-review.md; tests/test_shadow.py

### P8-06 - Publish the research go/no-go package

**Status:** IN_PROGRESS | **Owner role:** Research | **Depends on:** P8-05

**Target paths:** `docs/releases/v0.6.md`

Summarize all model comparisons, costs, data quality, uncertainty and open execution issues. Recommend continued shadow, revised experiments or a separately scoped pilot.

**Done when:** Reproducible bundle and decision record exist; no funded deployment is inferred from a positive report.

**Evidence:** docs/releases/v0.6.md; docs/results/shadow-review.md; artifacts/shadow/README.md

## P9 - Funded pilot

### P9-01 - Specify authorized pilot boundaries

**Status:** CONDITIONAL | **Owner role:** Product | **Depends on:** P8-06

**Target paths:** `docs/pilot-scope.md`, `configs/pilot/`

Only after a separate user decision, record chain, allowed assets/protocols, signer/custody, funded capital cap, daily loss limit, position cap and allowed transaction types.

**Done when:** Exact authorization and config match; no placeholder capital limits or blanket unlimited permissions remain.

### P9-02 - Implement isolated signer interface

**Status:** CONDITIONAL | **Owner role:** Security | **Depends on:** P9-01

**Target paths:** `src/willfly/execution/signer.py`

Select the approved custody mechanism and separate proposal, validation and signing. Keep private keys out of model inputs, logs and repository files.

**Done when:** Signer contract tests reject unapproved destinations/actions and prevent the LLM or market content from expanding authority.

### P9-03 - Implement transaction construction and simulation

**Status:** CONDITIONAL | **Owner role:** Execution | **Depends on:** P9-02

**Target paths:** `src/willfly/execution/transactions.py`

Build approved swaps and, if enabled, LP calls with exact amounts, slippage/deadlines and bounded allowances. Simulate against current state and inspect calldata.

**Done when:** Fixtures and fork/test environment runs reconcile decoded intent with proposed action; failed simulation blocks submission and does not count as a fill.

### P9-04 - Implement submission and receipt reconciliation

**Status:** CONDITIONAL | **Owner role:** Execution | **Depends on:** P9-03

**Target paths:** `src/willfly/execution/submission.py`

Handle nonces, idempotency, replacement, timeouts, reverts and confirmed receipts. Track pending transaction exposure and avoid unsafe resubmission after uncertain responses.

**Done when:** Recovery tests demonstrate no duplicate economic action and correct ledger state for pending, replaced, reverted and finalized transactions.

### P9-05 - Verify pause, withdrawal and recovery procedures

**Status:** CONDITIONAL | **Owner role:** Security | **Depends on:** P9-04

**Target paths:** `docs/runbooks/pilot-recovery.md`, `tests/execution/`

Test limit enforcement, emergency pause, approval management, manual inspection and permitted exit procedures. Document dependencies on contract liquidity and token transfer behavior.

**Done when:** Drills demonstrate signer/ledger consistency and bounded permissions; recovery instructions distinguish a possible action from a guaranteed exit.

### P9-06 - Run the separately authorized bounded pilot

**Status:** CONDITIONAL | **Owner role:** Execution | **Depends on:** P9-05

**Target paths:** `artifacts/pilot/`

Start only inside the agreed limits. Monitor receipts, costs and drawdown; stop according to the frozen pilot rules and record every funded action.

**Done when:** Actual wallet balances reconcile with the ledger; limit breaches pause the system; no automatic capital increase occurs.

### P9-07 - Review funded results before scaling

**Status:** CONDITIONAL | **Owner role:** Research | **Depends on:** P9-06

**Target paths:** `docs/results/pilot-review.md`

Compare actual execution and returns with shadow, including failed transactions and residual positions. Assess whether any demonstrated edge survives all paid costs.

**Done when:** Complete cash-flow report supports stop, revise or separately authorized continuation; scaling is not triggered by isolated wins.

## P10 - Expansion and advanced learning

### P10-01 - Implement a second-chain data adapter

**Status:** CONDITIONAL | **Owner role:** Data | **Depends on:** P8-06

**Target paths:** `src/willfly/adapters/second_chain/`

After selecting a named market, map its identity, finality, events and pool mechanics into existing contracts. Revalidate provider coverage and source licenses.

**Done when:** Cross-chain conformance fixtures pass; chain-specific facts are not hidden behind Robinhood assumptions.

### P10-02 - Rebuild cross-market evaluation

**Status:** CONDITIONAL | **Owner role:** Research | **Depends on:** P10-01

**Target paths:** `configs/experiments/cross_chain/`

Measure distribution shift and define fresh chronological holdouts before retraining. Compare pooled and per-chain models with matched costs and budgets.

**Done when:** Results distinguish transfer from retraining; Robinhood performance is not treated as evidence on the new chain.

### P10-03 - Test constrained internal fine-tuning

**Status:** CONDITIONAL | **Owner role:** Research | **Depends on:** P5-07

**Target paths:** `src/willfly/models/connectome/tuning.py`

Only if representation evidence justifies it, tune a limited encoder, gains/time constants or synaptic scales. Document graph/sign constraints and use frozen-reservoir and ordinary trained controls.

**Done when:** Gradient/parameter-change tests and held-out comparisons show whether extra tuning helps; biological fidelity claims remain distinct from financial usefulness.

### P10-04 - Test offline policy learning

**Status:** CONDITIONAL | **Owner role:** Research | **Depends on:** P3-08, P4-07

**Target paths:** `src/willfly/models/policy_learning.py`

If replay supports the required counterfactuals, compare imitation or offline RL with the existing prediction-to-action policy. Account for missing actions and expert-wallet selection bias.

**Done when:** Evaluation exposes unsupported action regions and reward shortcuts; apparent gain cannot rely on unmodeled fills or privileged demonstrator information.

### P10-05 - Test online adaptation in simulation or shadow

**Status:** CONDITIONAL | **Owner role:** Research | **Depends on:** P10-03, P8-06

**Target paths:** `src/willfly/models/plasticity.py`

Specify eligibility traces, delayed feedback, update bounds, retention tests and rollback checkpoints. Start with simulated or hypothetical outcomes only.

**Done when:** Frozen-learning, shuffled-feedback and regime-shift controls show adaptation and retention; no live funded self-modification is enabled.

### P10-06 - Review infrastructure and broader product scope

**Status:** CONDITIONAL | **Owner role:** Platform | **Depends on:** P10-02

**Target paths:** `docs/scaling-review.md`

Use measured storage, latency and compute demands to decide whether hosted services, queues, GPU training or a richer UI are justified. Re-estimate the next roadmap.

**Done when:** Capacity report and proposed cost budget support each infrastructure change; broader markets and funded authority remain explicitly scoped.
