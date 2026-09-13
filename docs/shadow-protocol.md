# Prospective shadow protocol v0.6

The shadow agent is read-only and hypothetical. It consumes observations at
their recorded `received_at` time, uses the frozen ordinary baseline until a
later evidence review changes that choice, applies the shared fixed-ticket
cash and position limits, and records proposed actions without a signer,
transaction builder or broadcast path.

Before the first observation, `configs/shadow/config.json` must be frozen with
a canonical config hash and timezone-aware start time. The registered study
requires at least 14 calendar days, 200 eligible launches and 99% decision
availability during healthy intervals. Missing launches, degraded intervals,
provider gaps and missed deadlines remain visible and extend the study rather
than becoming zeros.

LP is disabled in the frozen configuration because the P7 pool-family gate is
still open. Spot, wait and exit decisions remain independently eligible.

On stale, contradictory or unknown data, new entries are paused. Existing
hypothetical positions are held and marked for reconciliation; an unknown
execution state can never be reported as a successful exit. SQLite decision
IDs and checkpoints make restarts idempotent.
