# M2-05 reproducible baseline laboratory checkpoint

Status: `IN_PROGRESS` as of 2026-09-14.

`run_baseline_laboratory` evaluates every registered fixed policy over the same
chronologically ordered `BaselineCase` rows. The case carries one
execution-aware hypothetical entry/liquidation result; a policy can consume it
only by returning `enter`. This keeps idle, confirmation momentum, fixed-horizon
hold, verified-flow filtering and prior-information-only tracked-wallet follow
comparable without giving any policy a different dataset.

Each run records:

- ordered case and policy decisions;
- episode diagnostics and a compounded atomic hypothetical equity path;
- dataset, config and implementation hashes;
- per-policy metrics, including failure rate, exposure, turnover and drawdown;
- an explicit `baseline_selection: null` field.

The laboratory is deterministic and can report `pass` for fixture data when the
minimum independent-block requirement is met. It does not select a strongest
baseline, open the final holdout, promote a model, or imply live or profitable
trading. A real report still requires credible observed execution coverage,
declared chronological windows and the external M1/M2 evidence gates.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_baselines.py
```

