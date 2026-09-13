# Next build task backlog — Luna Extra High continuation

Version 2.0 | 2026-09-13 | 26 tasks

The JSON catalogue is authoritative. DONE requires acceptance evidence and completed prerequisites; existing code and fixture coverage are tracked separately. Target paths may include planned files.

## M0 - Reviewed baseline and publication

### M0-01 - Audit and correct immediate defects

**Status:** DONE | **Owner role:** Muse Sparks 1.3 implementation session | **Depends on:** None

**Target paths:** `docs/reports/astra-deep-audit.md`, `tests/test_audit_regressions.py`

Reproduce critical behavior beyond the inherited test suite; correct bounded defects and retain unresolved findings with their implications.

**Done when:** Audit differentiates fixed, mitigated and open defects; all 100 local tests pass; no live or profitable readiness is inferred.

**Evidence:** docs/reports/astra-deep-audit.md; tests/test_audit_regressions.py

**Verification:** Run the full suite and inspect the adversarial regression cases.

### M0-02 - Reconcile planning and add repeatable checks

**Status:** DONE | **Owner role:** Muse Sparks 1.3 implementation session | **Depends on:** M0-01

**Target paths:** `scripts/render_planning.py`, `scripts/check_planning.py`, `.github/workflows/tests.yml`

Preserve the incoming catalogue as historical evidence; reopen unsupported acceptance; render Markdown from JSON without resetting progress and install CI.

**Done when:** Catalogue dependencies and DONE evidence validate; Markdown is generated exactly; workflow uses Python 3.12 and pinned official actions.

**Evidence:** scripts/check_planning.py; scripts/render_planning.py; .github/workflows/tests.yml

**Verification:** Run scripts/check_planning.py and verify dependency locks in a clean environment.

### M0-03 - Publish reviewed baseline privately

**Status:** DONE | **Owner role:** Muse Sparks 1.3 implementation session | **Depends on:** M0-02

**Target paths:** `docs/reports/repository-publication.md`, `.gitignore`

Inspect candidate content for secrets and generated datasets; commit the reviewed tree and create a new private repository under the authenticated account.

**Done when:** Remote privacy and pushed commit are independently read back; no environment files, private keys, raw datasets or temporary renderings are included; report CI outcome separately.

**Evidence:** docs/reports/repository-publication.md

**Verification:** Compare local HEAD with remote branch SHA and query repository visibility; inspect staged file inventory.

## M1 - Operational Observatory

### M1-01 - Verify one deployable source configuration

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M0-02

**Target paths:** `configs/sources/`, `docs/source-matrix.md`, `docs/provider-budget.md`, `docs/reports/m1-01-source-manifest.md`, `src/willfly/adapters/source_manifest.py`, `scripts/check_source_manifest.py`

Pin chain, PoolManager and launchpad bytecode/ABI/creation blocks with primary and chain evidence; verify archive methods and no-graduate coverage; audit optional vendor access without making it a recorder dependency.

**Done when:** Versioned source manifest separates observed/documented/unavailable facts and includes contract provenance, limits, budget and tested event examples; unsupported history remains a release blocker.

**Evidence:** configs/sources/robinhood-chain-v0.1.json; docs/reports/m1-01-source-manifest.md; scripts/check_source_manifest.py; src/willfly/adapters/source_manifest.py; tests/test_source_manifest.py

**Verification:** Bounded RPC probes plus at least ten examples for each claimed event family; retain redacted responses and hashes.

### M1-02 - Connect durable bounded capture and backfill

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-01

**Target paths:** `src/willfly/cli.py`, `src/willfly/ingest/`, `src/willfly/storage/raw.py`

Wire actual CLI work to validated RPC and durable batches. Acknowledge empty and nonempty ranges only after persistence; bind checkpoints to chain/filter/ABI, stream pages without retaining full history, expose runtime and read-only stop controls.

**Done when:** Subprocess capture writes records and evidence, backfill resumes with no acknowledged loss, changed filters cannot inherit cursors, failures return nonzero and no signing method is reachable.

**Verification:** Crash injection before/after publication and checkpoint commit; overlapping backfill, empty blocks, changed filters and bounded-memory long-range fixture.

### M1-03 - Persist headers and reconcile forks

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-02

**Target paths:** `src/willfly/ingest/canonicalize.py`, `src/willfly/adapters/robinhood_rpc.py`, `src/willfly/ingest/quality.py`, `src/willfly/ingest/runner.py`, `src/willfly/storage/raw.py`, `src/willfly/cli.py`, `tests/test_header_reconciliation.py`, `tests/test_ancestry_repairs.py`, `docs/runbooks/observatory.md`

Fetch hash-matched headers and parent ancestry including quiet blocks, retain gaps, normalize instants, and rebuild canonical projections transactionally. Preserve unknown metadata without fabricating timestamps. Define and persist a source-verified ancestry anchor for bounded collection, including chain/hash/height/provenance, consecutive parent heights and fork handling at or beyond the anchor; never treat an arbitrary missing parent as a trusted root.

**Done when:** A fork through blocks with no selected logs repairs projections and checkpoints; missing ancestry remains unresolved rather than orphaning unrelated history; stale and unknown sources cannot report healthy. A qualified bounded window can resolve without fetching back to genesis; an unverified anchor, interior gap, nonconsecutive parent or fork crossing the trusted boundary degrades or invalidates acceptance explicitly.

**Evidence:** src/willfly/ingest/canonicalize.py; src/willfly/storage/raw.py; tests/test_header_reconciliation.py; tests/test_ancestry_repairs.py; src/willfly/cli.py; docs/runbooks/observatory.md; docs/reports/luna-repair-checkpoint.md; docs/implementation-log.md

**Review note:** Implementation and fixture coverage are present; live restart evidence (2026-09-13) confirms quiet-block header persistence, stable checkpoints across restarts, and honest unresolved boundaries for bounded live windows. Luna completed repair round 3: resumed backfills probe cursor lineage and replay changed bounded ranges with explicit needs_repair failure state, canonical resolution uses a positive reached/gap-free qualified invariant with strict nested evidence types, and endpoint provenance is origin-only across qualification, manifests, CLI output and errors. Full local suite and coordinator reproduction pass; no live source, timed acceptance or finality claim is inferred. M1-03 remains IN_PROGRESS until the coordinator independently rechecks this repair and M1-02 can satisfy its M1-01 dependency.

**Verification:** Multi-block fork, missing parent, no-log tip, zero timestamp, header mismatch, outage and restarted-process integration fixtures. Anchor qualification, restart, changed chain/config, nonconsecutive heights and forks at/beyond the anchor.

### M1-04 - Prove route attribution and net cash flow

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-02

**Target paths:** `src/willfly/adapters/protocols/v4.py`, `src/willfly/domain/contracts.py`, `src/willfly/features/timelines.py`, `tests/test_v4_protocols.py`, `tests/test_features.py`

Verify issuing contracts, receipt/log inclusion, pool currencies, token route and wallet direction; account for refunds, multi-hop, native currency and wrap/unwrap without counting unrelated multicall transfers. Version uncertain classifications.

**Done when:** Positive swaps have matched route and cash evidence; unrelated transfers remain ambiguous, quoted estimates never become spend, sells and buys reconcile separately, duplicate sources do not multiply volume.

**Evidence:** src/willfly/adapters/protocols/v4.py; src/willfly/domain/contracts.py; src/willfly/features/timelines.py; tests/test_v4_protocols.py; docs/implementation-log.md

**Review note:** The v0.2 route/cash boundary and adversarial fixtures are implemented, and live sampled receipts (2026-09-13) classify as genuine_swap/verified/buy through the v0.2 path while router-mediated and native-ambiguous cases stay ambiguous. M1-04 remains IN_PROGRESS pending M1-02's M1-01 dependency and integrated M1-05 through M1-07 evidence.

**Verification:** Adversarial unrelated airdrop plus swap, fee-on-transfer, refunded native input, forged issuer, failed receipt, sell and routed swap fixtures plus sampled supported receipts.

### M1-05 - Build causal projections and portable snapshots

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-03, M1-04

**Target paths:** `src/willfly/features/`, `src/willfly/storage/export.py`, `src/willfly/storage/raw.py`, `tests/test_observatory_projection.py`

Materialize as-of launch lifecycle, pool and token views from canonical evidence and arrival cutoffs. Deduplicate trade identity, preserve cohort revisions and uncertainty; add typed analytical projections beside lossless raw export.

**Done when:** Future graduation or leaderboard changes cannot rewrite an earlier snapshot; orphaned facts disappear only through explicit revisions; export preserves large values and all source metadata with atomic publication.

**Evidence:** src/willfly/features/projections.py; src/willfly/features/timelines.py; src/willfly/storage/raw.py; tests/test_observatory_projection.py; docs/implementation-log.md

**Review note:** Causal projection materialization, revision persistence and fresh-store restoration are implemented with fixture evidence, and a live integrated demo (2026-09-13) materialized a captured Pons launch into an immutable snapshot served over HTTP. M1-05 remains IN_PROGRESS until M1-03/M1-04 have completed their M1-02/M1-01 prerequisites and the qualified source/export evidence is available.

**Verification:** Future-data append invariance, mixed timezone cohort updates, duplicate trades, fork correction and fresh-process export/re-import tests.

### M1-06 - Build the functional terminal-style Observatory UI

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-05

**Target paths:** `src/willfly/api/server.py`, `src/willfly/ui/dashboard.py`, `src/willfly/cli.py`, `tests/test_observatory_projection.py`, `docs/ui-terminal-design.md`

Load persisted snapshots into the local API and route the dashboard. Add launch/pool/timeline lookup, source evidence, excluded rows, stale states and pagination; refresh consistently during capture. Apply docs/ui-terminal-design.md: terminal-style launches, tape, pools and data-health views with searchable/sortable paginated real data, detail/evidence panels, copy feedback, URL view state, refresh-preserved focus/selection, viewport pause and scoped provenance exports. Keep Python backend; choose a frontend framework only if warranted and document dependencies.

**Done when:** A fresh process displays a recorded active launch and a non-graduate, resolves raw evidence, and reports a simulated outage. Empty state is visibly distinct from healthy zero activity. All shipped controls work against persisted backend data; refresh preserves user context and pause does not stop ingestion. Unknown, stale, unsupported and observed zero are distinct. Desktop/mobile and keyboard operation remain usable; untrusted metadata cannot execute HTML or script. Advanced financial/model metrics appear only when actually available.

**Evidence:** src/willfly/api/server.py; src/willfly/ui/dashboard.py; src/willfly/cli.py; tests/test_observatory_projection.py; docs/implementation-log.md

**Review note:** Fresh-store API/dashboard loading, pagination, evidence and exclusions are implemented; a fresh-process live serve (2026-09-13) returned the captured launch over /launches, rendered the dashboard, and exposed /exclusions and /evidence. M1-06 remains IN_PROGRESS pending M1-05's acceptance dependencies, a qualified captured launch/non-graduate bundle and an environment that permits the full localhost socket check. The user explicitly includes the complete monitoring UI in this continuation batch; existing dashboard rendering alone does not satisfy the terminal design or interaction requirements.

**Verification:** Subprocess recorder-to-store-to-HTTP test, browser inspection, pagination/error tests and default localhost binding check. Browser interaction checks for search/filter/sort/pagination, selection/copy/evidence, refresh/pause/reconnect, scoped export and loading/empty/error/stale states; inspect desktop, tablet and mobile screenshots and hostile metadata. Fixture demonstrations cannot satisfy live non-graduate evidence.

### M1-07 - Accept the Observatory evidence bundle

**Status:** TODO | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-06

**Target paths:** `docs/releases/observatory-v0.1-reviewed.md`, `docs/runbooks/`, `src/willfly/evaluation/coverage.py`

Run clean-install demo, recovery drills and a real 72-hour bounded-scope capture audit against an independent canonical source. Measure provider availability and receipt delay separately from chain time.

**Done when:** All declared v0.1 gates have measured numerators, denominators and gaps; required source families verified, 99.5% discovery recall target met, no unexplained gaps or duplicate logical events. Otherwise label partial/inconclusive.

**Verification:** Retain the complete observation interval and independent query manifest; reproduce from another process; do not replace elapsed time with synthetic timestamps.

## M2 - Economically valid trading laboratory

### M2-01 - Implement one verified V4 quote path

**Status:** TODO | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-07

**Target paths:** `src/willfly/replay/execution.py`, `src/willfly/adapters/protocols/`, `configs/experiments/`

Use deployed protocol math and historical state at follower execution availability for one explicitly supported pool/hook family. Define routing, fees, tick crossing, price impact, gas denomination and failure semantics.

**Done when:** Supported quotes reconcile to observed transactions within declared tolerances; missing/stale/future state and unsupported hooks cannot generate validated fills. Toy constant-product outputs remain a separate benchmark.

**Verification:** At least 20 observed action examples plus tick-boundary, low depth, revert, asset mismatch and delayed-entry stress cases.

### M2-02 - Connect idempotent portfolio accounting

**Status:** TODO | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-01

**Target paths:** `src/willfly/replay/ledger.py`, `src/willfly/policies/constraints.py`

Join proposals to modeled execution records using exact per-asset debits, credits, gas and fees. Track token inventory, residuals, deposit-adjusted equity and action idempotency; prevent duplicate economic actions.

**Done when:** Cash is released only from reconciled exit proceeds, shared capital cannot be double allocated, fees are not counted twice and failed transactions retain applicable costs.

**Verification:** Hand-calculated multi-asset round trips, duplicate action/restart, partial or failed exit, concurrent candidates and deposit/withdrawal invariants.

### M2-03 - Generate genuine horizon labels and splits

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-02

**Target paths:** `src/willfly/features/labels.py`, `src/willfly/evaluation/splits.py`

Create each 1/5/15-minute label from a specified entry and horizon liquidation attempt; distinguish failure, unsellable residual, missing state and incomplete horizon. Freeze causal cohorts and purge training labels beyond partition boundaries.

**Done when:** Five-minute labels cannot reuse an unrelated earlier sale or leader fill; sample manifest includes failures and censoring; no outcome becomes available before its evidence arrives.

**Evidence:** docs/m2-labels.md; src/willfly/features/labels.py; src/willfly/evaluation/splits.py; tests/test_labels.py; tests/test_splits.py

**Verification:** Known-price paths with different horizon outcomes, late-arriving evidence, unsellable inventory, boundary purge and no-future-cohort tests.

### M2-04 - Measure actual portfolio and scenario outcomes

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-03

**Target paths:** `src/willfly/evaluation/metrics.py`, `src/willfly/evaluation/walk_forward.py`, `src/willfly/evaluation/replay_audit.py`, `src/willfly/evaluation/scenario_runner.py`

Compute net return and percentage drawdown from ordered equity, rerun each cost/capital/delay window through replay, and calculate paired uncertainty over declared independent groups. Derive gates from evidence rather than caller booleans.

**Done when:** Different execution stresses affect outcomes where expected; episode averages are not labeled portfolio returns; interval construction, drawdown, cost allocation and sample sufficiency reconcile.

**Evidence:** docs/m2-scenarios.md; src/willfly/evaluation/metrics.py; src/willfly/evaluation/walk_forward.py; src/willfly/evaluation/replay_audit.py; src/willfly/evaluation/scenario_runner.py; tests/test_baselines.py; tests/test_replay_audit.py; tests/test_scenario_runner.py

**Verification:** Hand-calculated equity curves, changed-cost replay, overlapping episodes, zero/negative equity, missing windows and bootstrap reproducibility tests.

### M2-05 - Publish a reproducible baseline laboratory

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-04

**Target paths:** `src/willfly/policies/`, `src/willfly/models/conventional.py`, `src/willfly/evaluation/baseline_lab.py`, `docs/releases/trading-laboratory.md`

Compare idle, confirmation, verified flow and causal follower rules under one ledger plus credible ordinary predictors. Register dataset/config/code hashes and realistic timing before viewing holdout; make replay/train/evaluate commands reproducible.

**Done when:** Independent rerun reproduces observations, ledgers and metrics across all declared windows; report no edge or inconclusive honestly. Baseline choice cannot be selected using final neural holdout.

**Evidence:** docs/m2-baseline-laboratory.md; docs/releases/trading-laboratory.md; src/willfly/evaluation/baseline_lab.py; src/willfly/policies/baselines.py; src/willfly/models/conventional.py; tests/test_baselines.py

**Verification:** Clean-process experiment command, fixture oracle, chronological held-out run and complete cost/latency/sizing report.

## M3 - Integrated prospective spot shadow

### M3-01 - Bind shadow state to a frozen run

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-05

**Target paths:** `src/willfly/shadow/config.py`, `src/willfly/shadow/runner.py`, `configs/shadow/`

Hash source/model/feature/policy identities and enforce one config per persistent run. Store observations, scheduled ticks, proposals, modeled fills, inventory and checkpoints atomically; serialize writers and define crash recovery.

**Done when:** Restart cannot change capital/model silently, duplicate or reordered delivery cannot create a second action, and exits never reclaim principal without modeled proceeds.

**Evidence:** docs/m3-shadow-loop.md; src/willfly/shadow/config.py; src/willfly/shadow/runner.py; configs/shadow/config.json; tests/test_shadow.py

**Verification:** Transaction-boundary crash tests, config mutation, changed predictions on duplicate observations, multiple writers and DB reconciliation checks.

### M3-02 - Connect the prospective hypothetical runner

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M3-01

**Target paths:** `src/willfly/cli.py`, `src/willfly/shadow/`, `src/willfly/api/`

Wire live recorder observations to scheduled ticks, fixed model inference and hypothetical execution. Provide stop/resume, source health, missed decisions and explicit unknown execution handling. Keep decision timing independent of forged event timestamps.

**Done when:** One end-to-end spot-only run consumes newly persisted observations and records hypothetical outcomes; healthy versus missing intervals are measured, and no funded transaction path exists.

**Evidence:** docs/m3-shadow-loop.md; src/willfly/shadow/runner.py; src/willfly/replay/execution.py; tests/test_shadow.py; tests/test_api.py

**Verification:** Controlled-source integration with stale/contradictory data, delayed ticks, restart and timeout; inspect operator status and ledger.

### M3-03 - Qualify prospective behavior

**Status:** TODO | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M3-02

**Target paths:** `src/willfly/evaluation/shadow.py`, `docs/results/shadow-review.md`

Collect at least 14 real days and 200 eligible prospective launches with the frozen ordinary policy. Reconcile quotes, actual arrival delays, missed decisions, state revisions and accounting; report excluded intervals.

**Done when:** Availability meets the declared 99% healthy-interval target with no unresolved gaps or ledger discrepancy. Results remain hypothetical; unmet duration/sample produces inconclusive, not a fabricated pass.

**Verification:** Evidence-backed interval audit, independent ledger reconstruction and replay-versus-prospective mismatch report.

## M4 - Neural and hybrid evidence

### M4-01 - Validate connectome provenance and dynamics

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-05

**Target paths:** `configs/connectome/`, `src/willfly/models/connectome/`, `src/willfly/models/reservoir.py`

Pin the actual release/license/hash and preprocessing; verify edge direction, sign/magnitude, graph filtering and numerical stability. Choose a compact subnetwork only with documented rationale.

**Done when:** Orientation changes actual edges/dynamics; nonfinite/ambiguous weights are rejected; graph statistics and provenance reproduce. No biological-memory or financial-skill claim follows from loading a graph.

**Evidence:** docs/m4-connectome.md; configs/connectome/male-cns-v1.0.json; src/willfly/models/connectome/ingest.py; src/willfly/models/connectome/graph.py; src/willfly/models/reservoir.py; tests/test_neural.py; tests/test_laboratory.py

**Verification:** Small hand-worked directed graph oracle, reversed orientation, filtered IDs, saturation tests and release/license evidence.

### M4-02 - Run fair neural and ordinary comparisons

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M4-01

**Target paths:** `src/willfly/models/`, `src/willfly/evaluation/neural.py`

Use numerically validated readout training and a sufficiently capable ordinary recurrent baseline. Match inputs, tuning budgets and at least five unique seeds per family; implement raw-feature, random, shuffled and no-state controls.

**Done when:** Run evidence includes four chronological windows, at least three with positive excess return if claiming advancement, paired 95% intervals against both practical and matched controls, and drawdown limits. Otherwise remain inconclusive/revise.

**Evidence:** docs/m4-connectome.md; src/willfly/models/laboratory.py; src/willfly/models/conventional.py; src/willfly/evaluation/neural.py; tests/test_neural.py; tests/test_laboratory.py

**Verification:** Solver comparison to an independent implementation, conditioning tests, actual ablation runs, per-model seed completeness and holdout audit.

### M4-03 - Implement only supported optional source adapters

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M1-07

**Target paths:** `src/willfly/adapters/lpagent.py`, `src/willfly/adapters/rhtrenches.py`, `src/willfly/adapters/mezzanine.py`

Verify official API/export support, terms and authentication per endpoint before bounded ingestion; version capabilities, raw payloads, cohort scope, source as-of time, arrival time, latency and costs.

**Done when:** Each source has tested behavior or an explicit unavailable assessment; unavailable adapters cannot be called operational. Staleness, duplicates and no-source fallback are exercised.

**Evidence:** docs/m4-optional-sources-and-llm.md; src/willfly/adapters/lpagent.py; src/willfly/adapters/rhtrenches.py; src/willfly/adapters/mezzanine.py; tests/test_hybrid.py

**Verification:** Redacted bounded access report, conformance fixtures and native-only operation. Do not bypass access restrictions or silently use undocumented streams.

### M4-04 - Enforce real LLM budgets and provenance

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-05

**Target paths:** `src/willfly/features/llm.py`, `src/willfly/features/text_schema.py`, `src/willfly/evaluation/contamination.py`

Use a transport with enforceable deadline/cancellation, persistent per-run request/token budgets based on provider usage, strict claims schema and archived source spans. Record retries and cache hits separately; keep present-day model knowledge out of retrospective features.

**Done when:** No callback can hang the decision loop; input/output/retry usage is charged, hostile fields cannot change policy, cache provenance is reproducible and unsupported historical text remains unavailable.

**Evidence:** docs/m4-optional-sources-and-llm.md; src/willfly/features/llm.py; src/willfly/features/text_schema.py; src/willfly/evaluation/contamination.py; tests/test_hybrid.py

**Verification:** Timeout/cancellation, huge compact output, cumulative budget exhaustion, retry accounting, injected fields, stale cache and identity-contamination tests.

### M4-05 - Attribute each hybrid contribution

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M4-02, M4-03, M4-04

**Target paths:** `src/willfly/evaluation/factorial.py`, `src/willfly/ui/decisions/`, `docs/results/hybrid-review.md`

Run distinct trader, contract-risk, social, LP-data and text ablations across ordinary and fly-derived architectures with data costs and latency charged. Use prospective evaluation where historical availability cannot be proven.

**Done when:** Every claimed contribution has actual comparable outcomes; optional unavailable experiments are recorded separately, not manufactured. Explanations cite recorded inputs and constraints without invented neural motives.

**Evidence:** docs/m4-hybrid-attribution.md; src/willfly/evaluation/factorial.py; src/willfly/ui/decisions/; tests/test_hybrid.py

**Verification:** Versioned factorial cells, same-data comparison, no-scanner/no-LLM baselines and reproducible evidence inspection.

## M5 - Optional LP and research decision

### M5-01 - Replace LP toy mechanics and ledger

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M2-04

**Target paths:** `src/willfly/replay/lp_positions.py`, `src/willfly/replay/lp_execution.py`, `configs/lp/`

Pin one supported family; implement exact sqrt-price/range and modular inside-fee accounting, owned position state, per-token cash flow and gas in its asset. Reject remove/collect without a position and duplicate lifecycle actions.

**Done when:** Observed checkpoints reconcile acquired inventory through final liquidation; distinct asset amounts are never summed as money; leaving range does not discard previously accrued fees. Keep LP disabled until evidence passes.

**Evidence:** docs/m5-lp-mechanics.md; src/willfly/replay/lp_positions.py; src/willfly/replay/lp_execution.py; configs/lp/scope.json; tests/test_lp.py

**Verification:** On-chain position examples, full-range boundary cases, uint256 fee wrap, exit out of range, unfunded removal, resize, duplicate collect and residual-asset ledger tests.

### M5-02 - Evaluate selective LP under shared capital

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M5-01, M2-05

**Target paths:** `src/willfly/policies/lp_baselines.py`, `src/willfly/policies/mode_selection.py`, `src/willfly/evaluation/lp_stress.py`

Compare spot, idle and restricted LP ranges under the same numeraire, execution times and starting funds. Stress fee demand, inventory loss, gas and exit depth without double-counting IL or LVR.

**Done when:** Actual supported mechanics drive comparisons; no simultaneous spot/LP over-allocation; LP stays disabled if its marginal benefit or execution evidence is missing.

**Evidence:** docs/m5-lp-mechanics.md; docs/lp-scope.md; src/willfly/policies/lp_baselines.py; src/willfly/policies/mode_selection.py; src/willfly/evaluation/lp_stress.py; tests/test_lp.py

**Verification:** Complete paired ledgers, capital conservation, observed fee checkpoint audit and stress report with all exclusions.

### M5-03 - Publish the next research decision

**Status:** IN_PROGRESS | **Owner role:** GPT Luna Extra High implementation session | **Depends on:** M3-03, M4-05

**Target paths:** `docs/releases/research-decision.md`, `docs/next-build-tasks.json`

Summarize operator reliability, baseline/neural comparisons, costs, uncertainty and optional-source limits. Include LP only if M5-02 passes; otherwise state disabled. Recommend further research, revision or separately scoped funded planning.

**Done when:** A reproducible release report records go/revise/inconclusive per capability and names unresolved findings. No automatic funding, scaling or strategy self-modification is enabled.

**Evidence:** docs/releases/research-decision.md; docs/releases/trading-laboratory.md; docs/next-build-tasks.json

**Verification:** Verify release manifest against captured runs and task evidence; publish separate acceptance records for data, inference and economic claims.
