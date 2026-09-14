# Selective LP laboratory scope

LP is a separate simulated policy action. The initial laboratory uses one
verified V3/V4 pool family, discrete ranges, fixed allocation and minimum
dwell time. It records acquisition, opening, resizing, fee collection, removal,
conversion, gas, residual inventory, failures and unsupported hooks.

The current scope remains `pending_pool_family_verification`, with LP
recommendations disabled. Linearized tick amounts are counterfactual
diagnostics only; exact integer helpers still require caller-supplied protocol
state and are not claims that Robinhood's deployment matches Uniswap's
reference implementation. Unknown hooks or unsupported tokens are excluded
from canonical LP episodes. LP is eligible for shadow only after live
deployment/bytecode, token order, TickMath, hook behavior, position
checkpoints, complete receipts and gas denomination all have independent
evidence and the lifecycle audit has no supported-case accounting discrepancy.
