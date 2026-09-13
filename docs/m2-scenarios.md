# M2-04 scenario and portfolio measurement checkpoint

Status: `IN_PROGRESS` as of 2026-09-14.

The laboratory now has two separate contracts:

- `calculate_metrics` accepts an explicitly ordered atomic equity curve and
  reports percentage drawdown in basis points. Episode returns remain inputs
  to averages and paired uncertainty; they are not treated as a portfolio
  path. If no equity curve is supplied, drawdown is `null` and a qualifying
  report is `missing_equity_curve`.
- `run_quote_stress_scenarios` reruns the same entry and exit quote path under
  declared delay, additional fee and slippage scenarios. A quote that is not
  available at the stressed execution time remains `missing_state`; unsupported
  hooks and failed fills remain explicit outcomes. No leader fill or unrelated
  mark is substituted.

`evaluate_walk_forward` exposes a `replay_window` boundary. An execution-aware
caller must apply each declared capital, delay and cost window there. When the
callback is absent, the helper reports `inconclusive_missing_replay` instead of
claiming that relabeled episodes represent changed economics.

The current fixture evidence proves deterministic mechanics and changed output
under a fee/delay/slippage stress. It does not establish observed transaction
coverage, profitability, or a live acceptance window. Those remain external
M1/M2 gates.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_baselines.py tests/test_replay_audit.py tests/test_scenario_runner.py
```

