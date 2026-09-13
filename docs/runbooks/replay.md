# Replay and labels runbook

Replay is a historical analysis surface only. It never signs, broadcasts,
funds, or substitutes a leader's fill for a follower's executable outcome.

## Reproduce the local checks

```text
.venv/bin/python -m pytest
.venv/bin/willfly fixture-check
```

The scheduler orders records by observed availability, then event time and
stable event ID. A strategy tick can only see records already available at that
tick. If arrival time is reconstructed, that fact must remain in the event's
availability field.

## Construct labels and splits

Use `build_forward_labels` with the observation availability time and the
declared 1/5/15-minute horizons. Failed or unsellable episodes are
`unresolved`; missing exits are `censored`; neither is silently converted into
a loss. Build `LabelReference` records with feature cutoffs no later than the
observation time, then create chronological `SplitWindow` partitions. The
split builder records group reuse and purged horizon overlap.

## Audit and bundle

`run_replay_audit` repeats ordering, counts exact/approximate/unsupported and
failed fills, records stressed delay/fee/slippage scenarios, and allocates data
charges once per replay dataset. Pass the observed transaction count and any
residual discrepancies; fewer than 20 observed examples leaves the audit
`inconclusive`.

`write_replay_bundle` stores dataset, labels, split, accounting and audit JSON
with SHA-256 hashes. The manifest explicitly blocks profitability claims until
the minimum sample and historical-state gates are met. An independent rerun
must verify every sidecar hash before interpreting labels.
