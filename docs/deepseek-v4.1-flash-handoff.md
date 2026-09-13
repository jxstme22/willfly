# DeepSeek V4.1 Flash continuation handoff

Prepared 13 September 2026. Active scope: complete the read-only Observatory implementation, explicitly including M1-06 and the terminal monitoring UI. This is an implementation-model choice, not a runtime model integration.

## Paste into the implementation session

```text
Continue Willfly in this repository using DeepSeek V4.1 Flash.
Read applicable repository instructions, README.md,
docs/reports/astra-deep-audit.md, docs/next-build-roadmap.md,
docs/next-build-tasks.json, docs/ui-terminal-design.md and this handoff.

Inspect Git state before editing. Preserve the existing GLM checkpoint;
Terra is paused. Be the only implementation writer. Do not reset, stash,
delete or replace others' changes, or spawn additional agents/tasks.
Verify the checkpoint and commit it if it is still uncommitted, describing
it as implementation evidence rather than completed M1 acceptance.

Work through these connected slices:
1. M1-03: define a source-verified starting-anchor policy for bounded
   canonical history. Persist chain, height, hash, qualification evidence
   and configuration identity. Require consecutive parent heights.
   An arbitrary oldest stored header is not a trusted root. Missing
   interior ancestry, conflicting anchors and forks reaching/crossing the
   boundary must invalidate or degrade affected projections explicitly.
   Verify bounded resolution, restart and fork recovery. Keep the existing
   RawBatchStore.persist_headers/rebuild_canonical_projection pipeline;
   do not introduce another parallel header store.
2. M1-05: complete fresh-process export/re-import verification. Preserve
   exact atomic integers, full identifiers, both event and arrival times,
   source evidence, classification versions and snapshot/revision identity.
   Verify manifests, corruption rejection and atomic publication. Preserve
   existing immutable snapshots when later data or reorg evidence arrives.
3. M1-07: implement coverage audit machinery and its runbook. Record actual
   observation intervals, independently sourced comparison manifests,
   numerator/denominator definitions, missing ranges, duplicates, delays,
   outages, restarts and code/config versions. Distinguish scaffold tests
   from the qualifying 72-hour run. No invented elapsed time or recall.
4. M1-06: BUILD THE FUNCTIONAL TERMINAL-STYLE WEB UI, not just a scaffold.
   Follow docs/ui-terminal-design.md. Implement launches, tape, pools and
   data-health views over persisted API records, with exact identity search,
   useful filters, stable sort/pagination, row detail/evidence, copy feedback,
   source freshness, exclusions and scoped exports with provenance.
   Preserve selection, filters, focus and scroll through refresh. Viewport
   pause must not pause ingestion; report pending rows and reconnect/stale
   states while retaining the last usable snapshot. Make every shipped
   control work. Keep terminal density readable on desktop and narrow screens.
   Use semantic HTML, keyboard access, safe rendering of hostile metadata,
   and exact values without JavaScript number precision loss.
   Keep the Python backend. A frontend framework is allowed when justified;
   document build dependencies and production serving. Do not duplicate
   attribution or financial logic in browser code.

UI implementation can proceed while external source gates are open.
Show uncertainty; do not silently omit provisional data or label it final.
Do not invent USD prices, TVL, executable depth, volume, PnL, live health,
scanner integrations or flybrain inference. Experiments/shadow remain
explicitly unavailable until their phases provide real results. No wallet
connection, trading buttons or signing are required for this monitoring UI.

Revisit M1-01 archive/non-graduate evidence with bounded read-only probes
when feasible. Preserve every unmet gate; the 72-hour Observatory and
14-day prospective shadow windows are separate. Continue independent
implementation rather than waiting out a clock or claiming timed success.

After each slice update JSON and append concrete evidence to
docs/implementation-log.md. Preserve historical findings and task statuses;
DONE requires full acceptance and completed prerequisites. Run:
  python3 scripts/render_planning.py
  python3 scripts/check_planning.py
  .venv/bin/python -m pytest -rs
  .venv/bin/python -m compileall -q src
  git diff --check
Also run relevant fresh-process and browser integration checks. Exercise
loading, empty, outage, stale, hostile metadata, reorg and failed/non-graduate
cases; record whether each is synthetic or live. Inspect desktop, tablet and
mobile layouts. A skipped socket/browser test is missing evidence, not a pass.
Do not run tmp/planning/write_backlog.py; it resets historical statuses.

Use small checkpoint commits, exclude secrets/raw datasets/temp files and
push to the existing private repository when checks pass. Record commit and
CI outcomes separately. No new repository is needed. Stop this batch with
a precise reviewable report: implemented behavior, verification, remaining
source/timed gates, UI launch command and next task. Do not advance into
funded execution, financial-model rewrites or neural training in this batch.
```

## Checkpoint and acceptance boundaries

The preceding GLM report describes 121 passing tests, sampled live receipt attribution, durable quiet-block headers, immutable launch snapshots and fresh-process HTTP evidence. The local continuation review reproduced 120 passing tests with one HTTP test skipped for unavailable loopback binding, plus green planning checks. A subsequent permitted localhost run passed the remaining HTTP test, verifying all 121 tests across the two runs. Live claims are retained in the implementation log; this handoff does not independently recertify their RPC samples.

The inspected worktree initially contained 31 modified tracked files and six untracked files, all unstaged. Inspect current Git state rather than assuming those counts remain current. Preserve the checkpoint before new implementation work.

M1-03 has a substantive additional acceptance issue: `canonicalize_events` walks backward until a known root, and one missing ancestor keeps every non-quarantined event unresolved. Extending a finite live window alone cannot settle its starting boundary. A documented, verified anchor and deep-fork policy are needed; clearing the missing-parent flag would conceal the problem.

M1-06 already has persisted dashboard/API plumbing. That does not establish the complete terminal design or interaction requirements. The new assignment explicitly includes those requirements; they are not deferred to the neural or trading phases.

M1-01 archive/non-graduate gates remain open. M1-05 export round-trip evidence and M1-07 measured qualification remain open. Acceptance dependencies still apply even when implementation work is complete. The project has not established a working flybrain financial model or profitable strategy.

## Repository and execution environment

Use the existing private [jxstme22/willfly repository](https://github.com/jxstme22/willfly), currently on `codex/astra-reviewed-baseline`; inspect the actual branch and remote before pushing. The selected external implementation session must provide DeepSeek. This file does not launch it, configure credentials, change the Codex model or authorize paid services.
