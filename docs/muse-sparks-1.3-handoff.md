# Muse Sparks 1.3 implementation handoff

Prepared 13 September 2026 | Active roadmap 2.0

## Paste into the new implementation session

```text
Continue Willfly using the reviewed roadmap in this repository.

Read README.md, docs/reports/astra-deep-audit.md,
docs/next-build-roadmap.md, docs/next-build-tasks.json and this handoff,
plus applicable repository instructions. The old GPT Astra handoff and
PDF are historical; neither proves operational readiness.

Inspect actual Git state and CI before editing. Start with the earliest
dependency-ready unfinished task in the next-build catalogue, normally
M1-01. Build an integrated read-only Observatory through M1-07 before
advancing acceptance of the trading or neural laboratory. Reuse existing
code where its behavior is correct; do not rewrite everything.

Critical facts: capture/backfill CLI currently return plan_only and exit 3;
serve uses an empty store; shadow remains blocked even with a valid frozen
config; modeled exits have no ledger bridge. Do not turn these into green
statuses by changing messages or filling placeholder config values.
LP mechanics, portfolio metrics, route attribution and real scenario
evaluation still have audit blockers. Read the exact findings.

Implement small connected slices with independent regression/integration
tests. Keep raw event time and received time distinct, preserve failed
launches and unknowns, and never equate transfers or vendor labels with
verified buying. Native collection must work without optional scanners.

After each batch update docs/next-build-tasks.json, cross-reference original
tasks when their full acceptance is met, and append evidence to
docs/implementation-log.md. Render Markdown with
python scripts/render_planning.py and validate with
python scripts/check_planning.py. Run relevant tests and the full suite at
release checkpoints. Do not run tmp/planning/write_backlog.py: it resets
the old tracker. Do not count fixture coverage as a live phase acceptance.

Continue independent offline work if external access is missing, but leave
the affected acceptance gate open and report the exact missing fact.
Do not buy subscriptions, bypass source access restrictions, create
additional sessions or agents automatically, add signing/broadcast,
or fund transactions. The requested scope is read-only research software.

Stop at the accepted Observatory milestone with its evidence report, or
leave an exact resumable checkpoint if the real observation gate remains
open. Later phases follow the roadmap when continued by the user.
```

## State at handoff

The audit expanded the local suite from 81 to 100 passing tests. Tests cover corrected storage idempotency, timestamp/split causality, source-time resolution, quote direction/time validation, shadow cash protection, config/package hashes, ridge fitting, lossless export and restricted text claims. They do not demonstrate an operational data pipeline, correct LP economics or profitable neural behavior.

The original 77-task catalogue preserves incoming statuses as `pre_audit_status` and fixture evidence separately from accepted completion. Its dependency gates were enforced; a large amount of implementation can exist while acceptance remains open. Use the new 26-task catalogue for build order and the audit for unresolved defects.

The read-only observation path must be usable first. A real data collection window and a formal prospective strategy window are different milestones. Do not start the latter until supported replay, ledger, scheduler and frozen-run persistence are validated.

The user chose the label **Muse Sparks 1.3** for the next build session. No API identifier, provider, capabilities, availability or model installation has been inferred. Select it through the user's intended environment; this repository does not depend on that label as a runtime LLM.
