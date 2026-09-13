# Trading laboratory release note

Status: `RESEARCH_RELEASE_ONLY` — draft checkpoint, 2026-09-14.

The local laboratory can replay declared fixed-policy cases, preserve explicit
failure and missing-state outcomes, calculate averages and paired block
uncertainty, calculate percentage drawdown from ordered atomic equity, and rerun
the same quote path under declared cost and delay stress. It can compare idle,
confirmation, verified-flow and prior-information-only tracked-wallet policies
over the same cases with dataset/config/code hashes.

The laboratory is not a live trading system and does not claim profitability.
No observed transaction sample sufficient for economic acceptance, verified
launch-history completeness, elapsed prospective window, or final holdout
result is present. The strongest practical baseline and any fly-specific
advantage remain unselected. LP is disabled pending pool-family and position
evidence; optional vendor and historical text sources are not operational.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_baselines.py tests/test_replay_audit.py tests/test_scenario_runner.py tests/test_lp.py
```

