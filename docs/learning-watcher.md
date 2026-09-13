# Durable learning watcher

B9 adds a persisted scheduler state for observation, label maturation, model
training and evaluation. Tasks are idempotently enqueued and completed in
SQLite; the last heartbeat and snapshot survive restart. A tick can reconcile
the B3 feedback queue, reports mature/eligible counts, and records a zero
personal-trade count explicitly. A gap between heartbeats is reported as an
outage interval rather than silently counted as uptime.

Intervals and resource limits are configuration, not evidence that a service is
running. The watcher returns `waiting` when a source, label queue or callback
is unavailable, and it never fabricates observations, labels, training or
evaluation results. The configuration keeps personal trades out of the trigger
path and keeps execution read-only.

This is scheduler and restart fixture evidence. A fresh Windows/WSL2 install,
real 24/7 observation period, resource benchmark, automatic candidate cycle,
and outage/recovery run against live sources remain open B9/B10 gates.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_watcher.py
```
