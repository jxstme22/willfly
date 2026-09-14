# Durable learning watcher

B9 adds a persisted scheduler state for observation, label maturation, model
training and evaluation. Tasks are idempotently enqueued and completed in
SQLite; the last heartbeat and snapshot survive restart. A tick can reconcile
the B3 feedback queue, reports mature/eligible counts, and records a zero
personal-trade count explicitly. A gap between heartbeats is reported as an
outage interval rather than silently counted as uptime.

The state database records the watcher configuration hash. Reopening it with a
different configuration fails closed; start a new state database after an
intentional scheduler-contract change so the interval and resource lineage is
unambiguous.

Intervals and resource limits are configuration, not evidence that a service is
running. The watcher returns `waiting` when a source, label queue or callback
is unavailable, and it never fabricates observations, labels, training or
evaluation results. The configuration keeps personal trades out of the trigger
path and keeps execution read-only.

`watcher-tick --schedule` adds a durable due-slot planner for all four stages.
It records one queued task per due stage, persists the last scheduled instant,
and coalesces a still-pending task after a gap. This is queue evidence only:
the task worker, source callbacks, automatic training/evaluation execution and
real 24/7 acceptance remain separate gates.

The library also exposes a callback boundary for a local service. On startup,
`run_pending_tasks` requeues tasks left `running` by an interrupted process,
claims one task at a time, leaves stages without a supplied callback queued,
and records callback completion, waiting or failure. Callback exceptions are
stored as `callback_failed:<ExceptionType>` so a worker failure cannot erase
the queue or masquerade as a completed stage. The watcher still does not ship
source, training or evaluation callbacks; those integrations must supply their
own read-only implementations and evidence.

This is scheduler and restart fixture evidence. A fresh Windows/WSL2 install,
real 24/7 observation period, resource benchmark, automatic candidate cycle,
and outage/recovery run against live sources remain open B9/B10 gates.

The operator surface can record one explicit, timezone-aware heartbeat and read
it back after restart. The tick is intentionally state-only: integrations pass
their observed stage states to it, while missing observations, labels or
callbacks remain waiting/degraded rather than being synthesized.

```text
.venv/bin/willfly watcher-tick \
  --state-db /path/to/watcher.sqlite3 \
  --feedback-dir /path/to/feedback \
  --observed-at 2026-09-14T00:00:00Z \
  --schedule
.venv/bin/willfly watcher-status --state-db /path/to/watcher.sqlite3
```

`watcher-status` includes both the pending task rows and `scheduled_slots` for
observation, labels, training and evaluation. A `null` slot means that stage
has not yet been scheduled in that state database; it is not evidence that the
stage is healthy or that a callback is running.

The command records `personal_trade_count: 0` by default and rejects watcher
configs that require a personal trade or widen the read-only execution scope.
Its exit status reports command success even when the persisted snapshot is
`waiting` or `degraded`; inspect the snapshot status and reason for the actual
health state.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_watcher.py
.venv/bin/python -m pytest -q tests/test_cli.py -k watcher
```
