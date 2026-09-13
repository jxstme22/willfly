# Initial evaluation contract

Version 0.1.0 | frozen 13 September 2026 before holdout access

The authoritative machine-readable proposal is
`configs/experiments/initial.yaml`. It freezes a 15-second decision interval,
1/5/15-minute horizons with 5 minutes primary, $100/$500/$1,000 hypothetical
capital scenarios, a 5% entry allocation, three-position cap, no borrowing and
no adding. These are controlled simulations, not investment recommendations or
authorization to spend.

Snapshots use only information received by the decision time while preserving
chain event time. Labels must record executable entry/exit feasibility, costs,
net return, adverse excursion, residual inventory and censoring. Quoted midpoint
is never a fill. Unsupported hooks and missing execution state remain observed
episodes but are excluded from validated execution claims.

The chronological split reserves a final untouched holdout. Within the earlier
80% window, calibration/train/validation/test are constructed chronologically,
purged by the maximum label horizon plus execution delay, and grouped across
correlated launch or wallet episodes. Normalization is fit on train only. Wallet
cohorts are selected using information available before each window; a later
leaderboard cannot rewrite earlier membership.

The primary financial comparison is paired net portfolio return against the
strongest preselected practical baseline. Drawdown and failure rate are reported
alongside it. A candidate with drawdown more than five percentage points worse
does not advance on return alone. A fly-specific advantage requires a positive
paired 95% block-bootstrap interval against both the strong practical and matched
nonbiological baselines and positive excess return in at least three of four
chronological test windows. Multiple seeds are not independent markets; an
underpowered sample is inconclusive.

The follower experiment is separate from leader economics. It replays our entry
at signal receipt plus processing/submission delay, requotes the available fill,
liquidates at the horizon under the shared ledger and includes gas, fees, delay,
slippage and failure/residual-inventory outcomes. A leader's fill price, PnL or
current mark cannot stand in for a follower outcome. Missing historical cohort
membership or execution state is reported as an inference limit.
