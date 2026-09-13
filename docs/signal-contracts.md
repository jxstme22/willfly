# Brain signal contracts

Version `signal-contract-v0.1.0` | B0 freeze | 14 September 2026

The machine-readable contract is
[`configs/experiments/signal-contracts-v0.1.json`](../configs/experiments/signal-contracts-v0.1.json),
and its executable validation lives in
`src/willfly/domain/signal_contracts.py`.

## Identity and targets

Every prediction and proposal carries a chain, token/pool identity, target ID,
model version, evidence cutoff, creation time and expiry. The contract freezes
15-second decision intervals, 15-second proposal TTL, and 60/300/900-second
horizons with a five-minute primary horizon.

The target IDs are `spot_entry_net_return`, `spot_hold_net_return`,
`spot_exit_net_return`, `lp_entry_net_return`, `lp_hold_net_return` and
`lp_exit_net_return`. Spot targets require a token identity; LP targets require a
pool identity and remain behind the separate LP execution-evidence gate.

Exit identity is explicit: spot exits may sell the token or convert residual
inventory; LP exits may remove liquidity, collect fees or convert residual
inventory. A generic “exit” cannot hide which inventory operation is intended.

## Confidence and states

`uncalibrated_score` is an ordinal model score and is never displayed as a
probability. `calibrated_probability` requires an integer basis-point value and
a versioned calibration reference. `unavailable` carries neither. Missing or
stale inputs remain visible through portfolio quality and evidence references.

Predictions are `research_prediction` records. Proposals are `research_only`
unless a later economic and evidence gate explicitly qualifies them. Proposal
expiry is bounded and refresh creates a new identity; expiry does not silently
extend an old signal.

## Manual execution and outcomes

The only execution scope is `manual_only`; signing and funding are disabled.
`ManualAction` records describe a user-reported external action, preserving
overrides, partial/failed/ambiguous status, optional transaction and wallet
references, and source evidence. They do not construct or submit transactions.

Outcomes remain separate as `actual_manual`, `simulated_counterfactual` or
`observed_market`. Actual outcomes require a manual action ID; simulated and
market observations cannot claim one. This prevents a user trade, a hypothetical
fill and a directly observed market result from being merged into one label.
