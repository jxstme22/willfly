# Build roadmap

> Historical plan/report. The 13 September Astra audit found incomplete integration and correctness gaps. Use the current [audit](reports/astra-deep-audit.md) and the version 2.0 next roadmap before implementation or readiness decisions.

Version 1.1 | 13 September 2026 | Status: implementation in progress; P0-P3 foundations recorded, P4-P8 machinery implemented with evidence gates open

## What we build first

**Willfly Observatory v0.1:** a local, read-only Robinhood Chain launch and liquidity recorder with a searchable timeline and a data-quality report. It answers: what appeared, when we learned about it, what happened next, and which evidence is missing?

Its first network adapter captures Uniswap V4 pool initialization and subsequent supported pool activity, preserving pool IDs rather than treating the shared PoolManager as a unique pool. A separate launch adapter records creation events from one verified launchpad version, including launches that never produce a trading pool. The exact launchpad deployment is a Phase 0 decision; no unverified contract address is hard-coded by this plan.

The first useful demo lists newly observed launches and pools, opens a token timeline, shows trades and liquidity changes with source timestamps, marks stale/unknown information, and exports a reproducible dataset. It makes no buy recommendation and requires no funded wallet. The same records later support replay, model training and an evidence-based decision interface.

## Deliverable ladder

| Release | Outcome | Required phases |
|---|---|---|
| v0.1 Observatory | Reliable launch/pool history and inspection UI | P0-P2 |
| v0.2 Trading laboratory | Cost-aware replay, labels and baseline decisions | P3-P4 |
| v0.3 Neural experiment | Measured fly-derived versus ordinary sequence models | P5 |
| v0.4 Hybrid intelligence | Independently measured LP-data and LLM contributions | P6 |
| v0.5 LP laboratory | Selective LP evaluated against spot and idle | P7 |
| v0.6 Shadow agent | Prospective hypothetical actions with live arrival delays | P8; P7 only if LP is enabled |
| Conditional pilot | Limited funded execution, subject to a separate decision | P9 |
| Conditional expansion | Another chain and more adaptive learning | P10 |

P0-P8 define the research build. P9-P10 describe contingent work, not current authorization to trade or a commitment to ship it. The backlog records the current status of each task; documentation completion does not count as implementation completion.

## Phase sequence and gates

| Phase | Purpose and exit gate | Effort estimate |
|---|---|---|
| P0 Specification and access | Pin deployments and one launch source; prove read access; freeze v0.1 scope and initial experiment assumptions | 2-4 engineer-days |
| P1 Recorder and recovery | Raw capture, canonical decoding, backfill and reorg/restart recovery pass fixture and sampled-chain audits | 5-8 days |
| P2 Observatory | Discovery, timelines, coverage diagnostics and portable dataset export pass the v0.1 demo | 4-6 days |
| P3 Replay and labels | Ledger and fill assumptions reconcile with fixtures and observed transactions; labels expose failures and missing outcomes | 6-10 days |
| P4 Baseline policies | Strong simple and ordinary learned baselines evaluated without leakage; experiments reproducible | 4-7 days |
| P5 Connectome experiment | Graph provenance and numerical stability verified; readout-only training compared with matched controls | 6-10 days |
| P6 LP data and LLM | Additions evaluated separately with cost, latency, provenance and contamination controls | 4-7 days |
| P7 LP policy | Supported fee paths and inventory accounting validated; LP decision adds value or is rejected | 7-12 days |
| P8 Shadow operation | Prospective records demonstrate reliability and quantify difference from replay | 3-5 engineering days plus observation window |
| P9 Funded pilot | Only after explicit capital/execution authorization and successful staged verification | Re-estimate after P8 |
| P10 Expansion and advanced learning | Chain portability and internal tuning tested independently | Re-estimate after evidence |

Estimates are planning judgments for one experienced engineer with agent assistance, not measured delivery commitments. P0-P2 total 11-18 engineer-days. P0-P8 total 41-69 engineer-days including LP. Provider access delays, insufficient launch history and observation windows are additional elapsed time. No GPU purchase is assumed. Scope and estimates are reviewed at each gate.

Critical path: P0 -> P1 -> P2 -> P3 -> P4 -> P5 -> P6 -> P8. P7 follows P3/P4 and can be scheduled after the spot shadow milestone if its data is unavailable. Spot research does not wait for LP implementation. These are dependency relationships, not instructions to launch parallel agents.

## First build queue

Execute P0-01 through P0-06 before binding the collector to a live deployment. Build P1-01 through P1-08 next, then P2-01 through P2-06. Detailed dependencies, target paths and completion evidence are in the [task backlog](build-tasks.md).

P0 can prepare the repository, configuration schema and offline fixtures while API access is unresolved. Mark fixture runs as synthetic; they cannot satisfy live coverage or latency gates. Production history needs an archive-capable provider. Public rate-limited RPC is sufficient only for appropriately limited connectivity checks, not an assumed production service.

### v0.1 demo script

1. Run configuration validation and confirm Robinhood chain identity, source manifest and read-only mode.
2. Start capture for the selected launch source and V4 pools; show a moving checkpoint and arrival-delay histogram.
3. Open a launch that later trades and a launch with no observed trading pool. Explain unknown history rather than deleting the second case.
4. Inspect a pool timeline, including a V4 pool ID, token identifiers, swaps and liquidity changes. Show how each row links to raw evidence.
5. Stop the recorder, replay an overlapping backfill and restart. Logical event counts and canonical history remain consistent.
6. Trigger fixture tests for duplicate delivery, a fork, provider disconnect and malformed events. Show recovery and quarantine output.
7. Export a dataset with configuration, hashes, coverage audit and missing intervals. A second local process reproduces the same logical records.

Proposed v0.1 gate: 72 continuous hours of capture; at least 99.5% discovery recall against an independently fetched canonical log set for the selected contracts and intervals; zero unexplained gaps after recovery; no duplicate logical events; restart/backfill/reorg tests pass. Target p95 observation arrival within 15 seconds of the provider-observed canonical block availability. Record chain timestamp separately. These are engineering targets, not current provider guarantees or proof of adequate latency for profitable trenching. If the comparison source is not independent, label the audit accordingly and keep the gate unresolved.

## Engineering decisions

Use a Python-first local research system. Proposed libraries are HTTP/WebSocket clients, typed data validation, Arrow/Parquet, DuckDB, numerical/scientific packages, a compact web API and pytest. Pin actual versions after compatibility checks in P0; this plan does not claim those checks are complete. Add PyTorch only when model work begins. A small server-rendered inspection UI is sufficient for v0.1; a separate frontend stack is optional later.

Store immutable raw batches as compressed JSON lines, analytical partitions as Parquet, and checkpoints/manifests in SQLite. Use DuckDB for local analysis of exported partitions. One process owns metadata writes initially. Introduce distributed queues, hosted databases or GPU infrastructure only when observed load or modeling requirements justify them.

### Proposed repository layout

```text
src/willfly/
  config/        source manifests, typed settings, experiment specifications
  domain/        events, pool identity, observations, decisions, ledger entries
  adapters/      robinhood_rpc, launchpad, bitquery, lpagent, rhtrenches, mezzanine, text_sources
  ingest/        capture, checkpoints, backfill, canonicalization, quarantine
  storage/       raw batches, metadata, parquet exports
  features/      causal windows, token timelines, LP and text features
  replay/        scheduler, quotes, execution assumptions, portfolio ledger
  policies/      baselines, action mapping, constraints
  models/        conventional, reservoirs, connectome, optional tuning
  evaluation/    splits, metrics, uncertainty, ablations, reports
  api/           read-only routes
  ui/            launch list, timeline, quality view, experiment views
  cli.py
configs/         chain, source, recording and experiment manifests
tests/           unit, integration, fixtures, replay and recovery scenarios
data/            ignored local raw/derived datasets
artifacts/       ignored model checkpoints and run outputs
docs/            architecture decisions, runbooks, source matrix and tasks
```

These paths and commands describe the application boundary; implemented slices are
tracked in the backlog and implementation log, while the remaining paths are still
specifications.

Proposed command contract: `willfly doctor`, `willfly capture`, `willfly backfill`, `willfly audit`, `willfly export`, `willfly serve`, then `willfly replay`, `willfly train`, `willfly evaluate`, and `willfly shadow`. Each accepts a versioned config path and produces a run ID. Initial releases must contain no transaction-signing or broadcast command.

## Data contracts

| Record | Required information |
|---|---|
| RawEvent | chain ID, source, source schema version, block number/hash, parent context, transaction hash, log index, event time, received time, payload, ingestion run, canonical status |
| PoolIdentity | chain, protocol/version, factory or manager, pool address for V3 or manager plus pool ID for V4, currencies, fee settings, tick spacing, hook identity |
| Launch | chain, launch contract/version, token identity, creation evidence, creator if observable, first-seen time, origin confidence, linked pools and lifecycle evidence |
| Observation | token/pool, as-of time, latest included event/arrival time, feature version, values, missingness, quality state and lineage |
| Decision | run/model/config IDs, observation ID, current inventory, proposed action, constraints applied, reason/evidence references and timing |
| LedgerEntry | action/transaction ID, asset quantities, cash flows, fees, gas, fill assumptions, marks and timestamps, failure/residual inventory state |
| ExperimentRun | dataset/code/config hashes, split manifest, seed, model parameters, training budget, metrics, costs, artifacts and decision ledger |

Raw event uniqueness includes chain, block hash, transaction hash and log index. Canonical logical projections resolve forks; orphaned evidence remains auditable. Store EVM integer quantities exactly and use explicit decimals. Symbols are display fields, never identity. Native ETH and wrapped ETH remain distinct internally, even if a vendor merges them. Unknown values stay unknown.

### Trade and scanner evidence

TradeEvidence records transaction identity, wallet attribution, supported swap/route evidence, exact payment and receipt quantities, classification, uncertainty and raw lineage. Verified swaps, transfers, gifts/airdrops and ambiguous receipts are separate categories. USD estimates are separate from actual quote-asset spend; unresolved valuation stays unknown.

VendorAssessment records source, token/pool, provider schema/method version when available, individual reason flags, source as-of time, received time, freshness and raw reference. A scanner warning is a claim to investigate. A missing warning is not proof of safety. WalletCohort records membership and relationship evidence with observation time; current rankings must not leak into historical selection.

P1-03 validates trade origin, P2-02 derives verified flow, and P2-05 exposes these distinctions. UI filters preserve raw events and show exclusions. The v0.1 demo additionally demonstrates that a token receipt without verified payment cannot inflate buying pressure. All foundational checks work with offline fixtures without requiring scanner subscriptions.

## Initial experiment specification

Proposed initial decision interval: 15 seconds, using only observations received by that moment. Candidate label horizons: 1, 5 and 15 minutes; the 5-minute outcome is the initial primary target. These are feasibility defaults to freeze or revise at P0/P3 using a calibration sample before the holdout is viewed.

Predict the net result of a fixed-size hypothetical purchase followed by liquidation at the horizon, accompanied by exit availability and adverse-excursion diagnostics. Use exact supported pool mechanics where available; otherwise label execution as modeled/unknown and keep it out of claims of validated profitability. Never infer a filled trade from a quoted midpoint alone.

Research capital scenarios: $100, $500 and $1,000 equivalents, fixed 5% entry allocation, at most three simultaneous positions, no borrowing and no adding to positions in the first comparison. These are controlled simulation parameters, not investment recommendations or authorized spending. Evaluate candidate size relative to executable depth. Use deterministic candidate ranking and ties so simultaneous opportunities obey a single shared cash ledger.

Primary financial metric: paired difference in net portfolio return against the strongest preselected practical baseline, with maximum drawdown and failure rates reported alongside. Initial rejection threshold: a model with worse drawdown by more than 5 percentage points does not advance on return alone. A fly-specific advantage requires a positive paired 95% block-bootstrap interval against both the strong practical and matched nonbiological model across the locked evaluation, and positive excess return in at least three of four chronological test windows. This is a proposed stringent research gate, not a forecast that adequate evidence will be available.

Use at least five initialization seeds for learned candidates and a final untouched chronological holdout. Pre-register bootstrap blocks and group overlapping/correlated launch episodes; do not count multiple seeds as independent markets. If sample size cannot support inference, report inconclusive. Do not fabricate a backtest through sparse history or repeatedly inspect the final holdout.

### Follower-outcome experiment

Use a cohort selected from information available before each evaluation window. Ask whether observed demand remains actionable after the signal reaches us. Replay the follower entry at signal arrival plus processing/submission delay, then model liquidation and all costs. Report leader observations separately; leader fill prices and current marked PnL cannot stand in for our entry, exit or training labels.

P3-03/P3-06/P3-07 implement and audit this replay; P4-01 adds a deterministic follow baseline where data supports it. Compare against idle, confirmation and ordinary learned policies. Candidate features include verified net flow, buyer concentration, retention and executable depth; proposed relationships remain hypotheses. Unknown historical membership or arrival times require explicit assumptions or prospective collection. P6-06 measures trader, risk and social data additions separately from LP, LLM and fly-topology effects.

## Observation and deployment gates

P8 initially requires 14 calendar days and at least 200 eligible prospective launch episodes; extend if either is missing. These minimums check operation and provide a research sample, not statistical proof of profitability. Qualification requires no unresolved ledger discrepancy or capture gap, at least 99% scheduled decision availability over healthy-source intervals, and recorded behavior under stale data and outages. Report all excluded intervals explicitly.

At shadow start freeze the model, feature versions, capital rules and quality thresholds. Shadow records hypothetical executions; do not label them fills. LP shadow is enabled only for pool families validated in P7. New strategy versions start a new evaluation run rather than rewriting previous results.

P9 requires a separately agreed chain, assets, signer/custody choice, capital cap, loss limits and permitted actions. It includes unsigned transaction verification, simulation, idempotency, approval limits, receipt reconciliation, pause/recovery and a manual exit procedure. No promise of execution quality follows from a profitable replay.

## Tool integration priorities and open gates

P0 validates native RPC and one event provider first. RHTrenches is a discovery/behavior comparison source; Mezzanine is an optional risk/social enrichment candidate. Neither has a verified public integration API in our research. Their access and terms are audited in P0-03; supported read adapters belong to P6-02 and must not block native collection. See the [scanner integration specification](scanner-integration-plan.md). Bitquery is a candidate for enrichment/backfill; the system keeps its own history. LP Agent is a later read adapter, not a Robinhood execution dependency. Zenith is a workflow reference until a supported integration and appropriate custody arrangement are established. LLM providers are selected and versioned in P6, with a request/token budget and a no-LLM fallback.

Source coverage, provider budget and exact launchpad deployment remain open facts. P0-02 evaluates Pons versions and pools.trade as leads already identified in the research, chooses one based on verified creation-event coverage and accessible history, and writes the rationale. If neither can be verified, ship the explicitly labeled pool observatory subset while launch-level v0.1 acceptance remains incomplete. Pool creation is not silently substituted for token launch.

Current sources: [Robinhood connection docs](https://docs.robinhood.com/chain/connecting/), [Bitquery pool events](https://docs.bitquery.io/docs/blockchain/robinhood/robinhood-new-pools-trending/), [LP Agent API](https://docs.lpagent.io/api-reference/introduction), [Zenith](https://lpzenith.com/). Public documentation was rechecked on 13 September 2026; API behavior and deployment bytecode still need validation.

## Build tracking rules

The task catalogue is exhaustive for this roadmap's initial scope, not a prediction of every future implementation issue. New discoveries become explicit tasks linked to a phase. Task IDs are stable. A task is DONE only when its acceptance evidence exists; a phase passes only when its gate is met. Provider-dependent tasks may be BLOCKED without marking offline work complete or misrepresenting coverage. Keep proposed design choices separate from observed results.

Use the [machine-readable backlog](build-tasks.json) and [human-readable backlog](build-tasks.md) together. Effort, progress and phase gates should be updated after each implementation batch. The PDF is a review snapshot; Markdown and the task catalogue are the maintained planning sources.

## Next-session handoff

Continue from [the implementation handoff](luna-build-handoff.md) and
[implementation log](implementation-log.md). P4-P8 implementation machinery is
now recorded, with P0/P1 source-history gates, connectome verification, LP pool
verification and the prospective shadow window still open. The next operational
step is to freeze `configs/shadow/config.json` immediately before starting a
real read-only observation window; do not fund execution. The existing PDF
predates these scanner refinements; maintained Markdown and JSON version 1.1
take precedence.
