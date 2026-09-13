# M3 prospective shadow loop checkpoint

Status: M3-01 and M3-02 are `IN_PROGRESS` as of 2026-09-14. M3-03 remains
open because its duration, launch-count and healthy-availability gates require
actual prospective evidence.

The shadow store now binds a persistent run to supplied config/source/feature/
policy identities. Restarting without the recorded identity, or with a changed
identity, fails closed. Observations, decisions and last-received/last-decision
checkpoints are published in one SQLite transaction. Observation identity is
unique, so a duplicate delivery with changed prediction data returns the
original hypothetical decision instead of creating a second action.

When `model_execution=True`, the runner independently requotes the fixed-ticket
entry or the reconciled token inventory at the supplied execution delay. It
stores modeled fill status, exact input/output amounts, output asset and quote
source reference alongside the proposal. Missing state, unsupported hooks and
reverts remain non-positions; `execution_state` remains `not_submitted`. The
default mode remains proposal-only for callers that have not supplied a
modeled execution request.

The local checks cover restart identity, atomic persistence, changed-prediction
deduplication, shared cash, filled entry/exit inventory, missing-entry handling,
stale/contradictory health and read-only API behavior. The loop does not submit,
sign or fund transactions.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_shadow.py tests/test_api.py
```

