# Next build roadmap — Muse Sparks 1.3

Version 2.0 | 13 September 2026 | Based on the Astra implementation audit

## Starting decision

Keep the Robinhood-first research objective. Reuse existing schemas, decoding helpers, storage, API components and model experiments, but first connect and validate the data path. The next deliverable is an operational local Observatory with persistent capture, truthful health and a populated interface. The current platform cannot yet support a credible financial experiment.

Read [the audit](reports/astra-deep-audit.md) before building. The incoming handoff is historical evidence. Its 50 DONE labels meant implementation slices, not full acceptance. The original [77-task catalogue](build-tasks.json) now preserves `pre_audit_status` and existing implementation evidence while reopening acceptance where defects or incomplete prerequisites apply. Most acceptance remains open; this does not erase existing code. The [26-task next catalogue](next-build-tasks.json) is the active build order, with a [generated Markdown view](next-build-tasks.md).

## Release sequence

| Phase | What changes | Exit evidence | Effort assumption |
|---|---|---|---|
| M0 Reviewed baseline | Local defect corrections, honest statuses, reproducible checks and private repository | Regression suite, planning checks, private remote commit and recorded CI outcome | Current audit batch |
| M1 Observatory | Connect capture, durable ranges, header/fork history, attribution, causal projections and inspection UI | Fresh-process demonstration plus 72-hour independently audited capture; no unexplained gaps | 6–12 engineer-days plus data/access wait |
| M2 Trading laboratory | Real supported V4 mechanics, per-asset ledger, horizon labels and portfolio evaluation | At least 20 observed transaction reconciliations, all locked scenarios rerun, reproducible baseline report | 8–15 days plus adequate history |
| M3 Prospective spot shadow | Bind persistent state to a frozen run and connect scheduling/inference/hypothetical executions | 14 real days, 200 eligible launches, 99% healthy-interval availability, complete reconciliation | 4–8 engineering days plus observation |
| M4 Neural/hybrid evidence | Pin biological data, strengthen ordinary controls, enforce optional API/LLM boundaries and measure contributions | Actual controlled comparisons; unavailable source experiments remain unavailable | 6–12 days plus release/data verification |
| M5 Optional LP/research decision | Replace toy LP amounts/accounting and compare LP under shared capital; publish a candid research decision | Supported position checkpoints, full entry-to-exit economics and marginal benefit, or LP stays disabled | 6–12 days if pursued |

Estimates are planning judgments for an experienced engineer working with an implementation model. They are not model-speed guarantees or delivery dates. M1–M4 total approximately 24–47 engineering days; M5 is additional. Provider limits, missing credentials, sparse launches and required real observation windows can dominate elapsed time. Re-estimate after M1-01 and M2-01. No token, GPU or paid-data budget is assumed approved.

Dependencies describe acceptance evidence, not a ban on independent offline drafts while a live gate is pending. Do not claim a phase complete from such drafts. No automatic multi-agent or new-session orchestration is requested.

## First implementation batch

1. **M1-01:** verify the actual source manifest, bounded archive access, event time and creation history. Explicitly retire prior arrival-time fallbacks as historical event evidence. Confirm the exact launchpad version; do not guess missing creation blocks.
2. **M1-02:** make `willfly capture` and `willfly backfill` perform bounded, resumable work and return a run manifest. Source/filter identity and persisted ranges must precede successful checkpoints. Keep a separate explicit `--dry-run` if useful.
3. **M1-03:** store complete block/header ancestry and fork decisions, including blocks without selected logs. An unresolved parent must degrade health instead of silently orphaning data.
4. **M1-04/M1-05:** establish route/payment evidence and causal projections. No market signal should use the current `genuine_swap` flag as proof until this work passes.
5. **M1-06:** serve persisted data and the actual HTML dashboard; inspect launch timelines, exclusions and source freshness from another process.
6. **M1-07:** run the clean-install demo and real capture audit; publish either accepted Observatory or a clearly limited prototype.

The first useful vertical test is: fixture RPC with one true launch, one non-graduate, a genuine swap, an unrelated airdrop, a quiet block and a fork → durable capture → restart → canonical projections → localhost HTTP views → lossless export. Then repeat the supported path against bounded real data. Synthetic fixtures can validate mechanics, but cannot certify chain coverage or profitability.

## Contracts to settle before orchestration

- **CaptureRun:** run ID, chain/filter/ABI/config hash, operator start/stop, provider identity, attempted and durably acknowledged ranges, header evidence, errors and retained raw batches. Zero-event ranges need evidence too.
- **TradeEvidence v2:** token/pool/route and wallet identity, receipt/log linkage, token direction, payments/refunds, verified versus uncertain classification, exact asset units and arrival provenance. Deduplicate by economic event while retaining all sources.
- **ObservationSnapshot:** immutable as-of state and source cutoffs; lifecycle changes have their own observation time. Canonical revisions never silently rewrite earlier training inputs.
- **ModeledExecution:** proposal ID, run, execution availability, supported protocol path, state references, per-asset spends/receipts, fees/gas, failure or residual inventory. A decision alone cannot change cash.
- **PortfolioState:** asset balances and inventory backed by executions, cash flows external to performance, reproducible valuation/numeraire and time-based equity. Repeated actions must be idempotent.
- **ResearchRun:** source/data/code/config/model hashes, chronology, seed and tuning allocations, declared windows, actual outcomes and uncertainty. Caller-supplied booleans cannot certify gate passage.

Prefer typed stable interfaces and small integration slices over replacing the repository. Keep Python 3.12 as the supported source-checkout runtime until compatibility evidence changes it. Use established numerical libraries when the small dependency-free solver is no longer sufficient. Lossless JSON-in-Parquet is the raw export contract; typed analysis columns can be added as separate projections with explicit schema versions.

## Economic and scientific rules

The ordinary spot laboratory comes before the fly-derived experiment. Define follower outcomes at our received-signal time plus processing/execution delay. Select cohorts only from prior information and model inventory recovered at exit. Validate each quote path against deployed protocol behavior; the current constant-product simulator is a toy comparator, not a V4 execution oracle.

The original simulation defaults ($100/$500/$1,000, 5% entries, at most three positions, no leverage) are research controls. Freeze or revise them with a calibration sample before holdout use. Measure portfolio net return, drawdown, failed exits, exposure, costs and uncertainty; do not substitute win rate or summed episode returns.

Fly-specific advancement requires strong practical and matched ordinary controls, at least five unique seeds per learned family, four locked chronological windows, positive excess return in at least three windows, positive paired 95% intervals against both controls, and the predeclared drawdown limit. These thresholds are research gates, not performance forecasts. Additional trader/social/LLM information must be held equal when testing biological topology.

LP remains disabled until exact math, owned-position accounting and observed fee/exit evidence pass M5. M5-03 can publish a research decision with LP disabled; M5-01/M5-02 are not prerequisites for spot shadow. Additional marketplaces, signer integration, funded trading and online funded adaptation remain outside this next implementation scope.

## Review and handoff discipline

Use [Muse Sparks 1.3 handoff](muse-sparks-1.3-handoff.md). The model name records the user's next implementation preference; this plan does not assert a provider, install a model or switch this session. There is no automatic new task.

Update JSON after each verified batch, then run `python scripts/render_planning.py` and `python scripts/check_planning.py`. Preserve historical evidence and the original task IDs. Record failures as well as passing commands in the implementation log. Do not rerun the old temporary backlog generator, which resets statuses. Acceptance must reference actual work and completed dependencies; elapsed observation time cannot be simulated into completion.
