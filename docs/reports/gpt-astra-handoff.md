# GPT Astra handoff report — Willfly roadmap implementation

> Historical plan/report. The 13 September Astra audit found incomplete integration and correctness gaps. Use the current [audit](astra-deep-audit.md) and the version 2.0 next roadmap before implementation or readiness decisions.

Date: 13 September 2026

## Executive summary

The roadmap was continued from Phase 3 through the research-ready Phase 8
shadow milestone in small, verified loops. The implementation is read-only and
evidence-first. It does not sign, broadcast, fund, or claim profitable trading.

Roadmap status is synchronized in `docs/build-tasks.json` and
`docs/build-tasks.md`:

- 50 tasks are `DONE` as implementation/evidence-supported slices.
- 14 tasks remain `IN_PROGRESS` because live source, sample, or time-window
  gates are not satisfied.
- 13 P9/P10 tasks remain `CONDITIONAL` and were not started.

## Work completed after Phase 3

### Phase 4 — baseline laboratory

- Added idle, fixed-horizon, confirmation/momentum, verified-flow and causal
  tracked-wallet-follow baselines.
- Added deterministic linear and recurrent conventional models with hashes,
  seeds and episode state resets.
- Added shared prediction-to-action mapping, run tracking, search budgets,
  failure recording, metrics, paired block bootstrap and walk-forward windows.

### Phase 5 — connectome experiment machinery

- Added a license-gated connectome manifest and text-preserving ID validation.
- Added sparse directed graph construction, shuffled/random-weight controls,
  graph hashes and rate-based reservoir dynamics.
- Added frozen readout training, matched five-seed comparison registration,
  ablation review and explicit inconclusive progression gates.
- Added a hash-checked neural package that reloads graph, reservoir config,
  readout and model card while reproducing reference predictions.

The connectome manifest remains `pending_verification`; no MaleCNS release,
license, or biological fidelity is claimed.

### Phase 6 — optional data and LLM boundaries

- Added explicit unavailable capability boundaries for LP Agent, RHTrenches and
  Mezzanine, so optional access cannot block native capture.
- Added causal LP observations, scanner-claim normalization, source-backed text
  claims and historical retrieval-cutoff auditing.
- Added bounded, schema-checked LLM enrichment with cache keys, retry limits,
  request/token budgets and a numerical fallback. LLM output cannot create
  profit labels or change permissions.
- Added factorial registration and evidence-backed decision inspection.

The hybrid review remains `INCONCLUSIVE` because no valid historical scanner or
LLM performance claim is available.

### Phase 7 — selective LP laboratory

- Added tick/range and fee-growth replay with explicit counterfactual labeling.
- Added lifecycle accounting for acquire/open/collect/resize/remove/convert,
  gas, residual inventory, failure and unsupported paths.
- Added fixed-wide, volatility-range and idle LP policies plus shared spot/LP/
  idle mode selection that prevents double allocation.
- Added linearized LP stress diagnostics.

LP is currently `DISABLED_PENDING_EVIDENCE`. No pool family is enabled until
deployment, hook behavior, fee state and observed checkpoints are verified.

### Phase 8 — prospective shadow agent

- Added `configs/shadow/config.json` with ordinary-baseline/spot-only defaults.
- Added config-freeze procedure requiring a start time and canonical hash before
  the first observation.
- Added SQLite-backed hypothetical decision checkpoints with deterministic IDs,
  restart-safe deduplication, shared cash, position limits and exit cash release.
- Added stale/contradictory/unknown health handling: pause new entries and hold
  existing positions for reconciliation; unknown execution is never a successful
  exit.
- Added a 14-day/200-eligible-launch/99%-healthy-availability audit and shadow
  reconciliation metadata.
- Added `willfly shadow`, which currently returns `blocked` because the static
  config is intentionally unfrozen.

## Existing foundation retained

The earlier phases provide strict exact-integer contracts, append-only raw
storage, Robinhood Chain read-only RPC capture, Uniswap V4 decoding and receipt
joins, Pons V2 lifecycle projection, resumable backfill, canonical/fork
recovery, quality reporting, discovery/timelines, export, local inspection UI,
deterministic replay, causal labels, constrained allocation and hashed replay
bundles.

The local dashboard/inspection UI exists, but there is no live trading signal.
The baseline and shadow decisions are research actions, not investment advice
or funded orders.

## Verification

```text
python3 -m pytest                  80 passed, 1 optional export skip
.venv/bin/python -m pytest         81 passed
PYTHONPATH=src python3 -m willfly fixture-check   passed
PYTHONPATH=src python3 -m willfly doctor          status: ok
PYTHONPATH=src python3 -m willfly shadow          blocked: shadow_config_not_frozen
```

The task JSON is valid and its statuses match the Markdown backlog exactly.

## Evidence gates still open

1. Pons V2 creation block, archive depth, lifecycle history and non-graduate
   coverage are not independently verified. The bounded live sample returned 34
   `TokenLaunched` events, zero lifecycle events and zero block timestamps.
2. The provider-independent 72-hour capture/completeness audit is not complete.
3. The connectome source release/license gate is not complete.
4. No LP pool family has sufficient observed mechanics/checkpoint evidence.
5. The prospective shadow window has not started; its config still has null
   `start_time` and `config_hash`.

These gaps remain visible rather than being converted into zero performance or
false-positive readiness.

## Recommended next action for Astra

Review this report together with `docs/implementation-log.md`, then decide
whether to begin a real read-only observation window. If authorized, freeze
`configs/shadow/config.json` immediately before collection, record the resulting
hash/start time, run the native collector, and leave LP disabled. Do not start
P9/P10 or add signing/broadcast behavior without a separate explicit decision.
