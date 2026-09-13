# M2 execution and accounting checkpoint

Status: M2-01 and M2-02 are `IN_PROGRESS` as of 2026-09-14.

The local execution boundary supports exact-input constant-product benchmark
fills, explicit quote availability/future-state checks, unsupported hooks,
price-impact and delay outcomes, and a follower round-trip that never copies a
leader fill. The exact-atomic portfolio ledger tracks per-asset spend/receive,
fees, deposits and failed attempts; candidate allocation enforces shared cash,
fixed tickets, position caps and no adding.

These are replay mechanics and fixture oracles. The benchmark is not the
verified deployed V4 path required for an economic claim, and complete observed
execution examples, gas denomination, historical state, partial-exit and live
source gates remain open. Missing and unsupported paths remain visible and
inconclusive.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_execution.py tests/test_replay_core.py tests/test_accounting.py tests/test_constraints.py
```

