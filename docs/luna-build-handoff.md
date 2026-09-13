# GPT Luna implementation handoff

> Historical plan/report. The 13 September Astra audit found incomplete integration and correctness gaps. Use the current [audit](reports/astra-deep-audit.md) and the version 2.0 next roadmap before implementation or readiness decisions.

Prepared: 13 September 2026 | Plan version 1.1

## Start here

Open a new session in `/Users/welly/Documents/ChatGPT/willfly`, select GPT Luna, and use the prompt below. This document does not create a session or change the current model.

```text
Continue implementing the Willfly roadmap in this workspace from the recorded
checkpoint. If the workspace is still at the initial state, start with the
Observatory sequence below; otherwise preserve completed statuses and continue
the next dependency-ready loop.

Read README.md, docs/luna-build-handoff.md, docs/build-roadmap.md,
docs/build-tasks.json, docs/scanner-integration-plan.md and any applicable
AGENTS.md instructions. Use the maintained Markdown/JSON plan version 1.1;
the PDF is an older review snapshot.

Begin with P0-01 through P0-06 only when they are not already evidenced.
Then proceed through dependency-ready P1-P8 work toward the research-ready
prospective shadow milestone. Follow the phase gates and do not mark live-data
or time-window requirements complete from synthetic evidence.

Preserve exact EVM values, V4 pool IDs, event and arrival times, raw lineage,
unknowns and failed launches. Validate genuine swaps separately from token
transfers, gifts/airdrops and ambiguous estimated activity. RHTrenches and
Mezzanine are optional sources whose public integration APIs remain unverified.
Their access gaps must not stop independent native/offline work. Full optional
vendor adapters are P6 work; follower replay belongs to P3/P4.

Work in small verified batches. After each batch update the JSON and Markdown
task status consistently and record commands, evidence, unresolved issues and
the next dependency-ready task in docs/implementation-log.md. Preserve existing
research. Do not use the old backlog generator in a way that resets statuses.

Do not build a signer, submit transactions, fund accounts, buy subscriptions,
or enable funded trading. Do not start P9/P10, train the neural model before
the data/replay gates, or create additional sessions/agents automatically.
If an external prerequisite is missing, record the exact blocker and continue
useful independent work. Stop at the research-ready shadow milestone with a
candid gate report. P9/P10 remain conditional and require a separate
authorization; if the observation window has not elapsed, leave its status
explicitly in progress and provide a resumable checkpoint.
```

## Current state

- P0-P3 foundations are implemented with the launch-history, provider-independence and replay evidence gates still open.
- P4-P8 implementation machinery is present: baselines/evaluation, gated connectome package, causal optional-data/LLM boundaries, modeled LP laboratory and read-only hypothetical shadow loop.
- P4/P5/P6/P7/P8 review status and exact evidence are maintained in `docs/build-tasks.json`, `docs/build-tasks.md` and `docs/implementation-log.md`.
- The static shadow config remains unfrozen (`start_time` and `config_hash` are null). Freeze it immediately before a real observation window; do not fabricate or fund execution.
- Core build: 64 tasks across P0-P8. Conditional later work: 13 tasks across P9-P10.
- Primary operational milestone: a 14-day, 200-eligible-launch, 99%-healthy-availability prospective shadow window. LP remains disabled until P7 pool-family verification.
- Primary network scope: Robinhood Chain. Launch-history, archive/provider limits, connectome release/license, and LP pool-family evidence remain unresolved.
- The repository includes the local read-only collector/replay/UI and research machinery; observed-data and time-window gates are still not claims of profitability or execution readiness.

## Initial batch and evidence

1. **P0-01:** package/environment, lockfile, offline command, dataset/secret ignore rules and reproducible checks. Record Python/runtime choice. Preserve existing research files.
2. **P0-02/P0-03:** versioned deployment and provider/source matrix, bounded read probes, access gaps and estimated request/storage costs. Distinguish official documentation from observed live evidence.
3. **P0-04:** versioned identity/event/observation contracts including trade evidence, vendor assessments and as-of cohorts. Reject ambiguity or represent it explicitly.
4. **P0-05:** proposed targets, causal splits, simulation parameters and follower-outcome specification frozen before holdout inspection.
5. **P0-06:** observed fixtures where available, explicitly synthetic adversarial/recovery fixtures, and the v0.1 demo checklist.

A blocked deployment or key does not prevent drafting generic contracts and offline fixtures. Such drafts cannot satisfy live verification criteria or be presented as completed dependent deployment work. Record partial progress separately, then revalidate it once prerequisites are established.

## Progress contract

The JSON task catalogue is the structured tracker; the Markdown backlog must mirror it. Use TODO, IN_PROGRESS, BLOCKED, DONE or CONDITIONAL as appropriate and add evidence references for each status transition. DONE requires the task's full acceptance evidence; a documented unavailable scanner may complete its assessment while leaving its live adapter unresolved.

Create `docs/implementation-log.md` at the start of implementation. Each batch records task IDs, changes, exact verification commands/results, observed versus synthetic evidence, blockers, and the next task. Update phase gates and estimates when access or measurements change them. Keep task IDs stable.

`tmp/planning/write_backlog.py` regenerates the original planning catalogue with default statuses. It was synchronized for version 1.1, but rerunning it after implementation begins would reset progress. Replace that behavior with rendering from the canonical JSON before using it for future status updates, or update JSON/Markdown directly.

The PDF is a review snapshot predating scanner refinements. No PDF regeneration is required to begin development. Full neuroscience and LLM research can be read before the relevant later phases; do not let that defer the first working recorder.
