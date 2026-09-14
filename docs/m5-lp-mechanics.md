# M5 LP mechanics checkpoint

Status: M5-01 and M5-02 are `IN_PROGRESS` as of 2026-09-14. LP remains
`DISABLED_PENDING_EVIDENCE` in the product configuration.

The LP replay boundary now provides exact integer Q96 amount calculations and
integer TickMath from caller-supplied protocol state, rather than requiring a
float tick approximation. Fee-growth deltas use uint256 modular subtraction,
and are settled even when a position has subsequently left its range, so a
valid counter wrap or range crossing does not erase accrued fees. Position,
pool, range and optional owner identity are carried through lifecycle events;
resize, collect, remove and convert require an active matching position.
Replayed action IDs are idempotent, while a later canonical receipt can
supersede an orphan/provisional delivery. Fee totals remain per token rather
than summing unlike assets as money, and gas is retained in an explicit
per-asset map (or `unknown:gas` when a fixture does not provide a denomination).
When a gas denomination is present in the supplied starting balances, the
amount is debited before the lifecycle action. Otherwise it remains in
`unreconciled_gas_by_asset` as a liability rather than becoming free balance;
unknown gas is never silently charged to token0 or token1.

The older `amounts_for_liquidity` linearized tick helper remains available as a
named counterfactual diagnostic for compatibility. It is not used as proof of
deployed V4 mechanics. Unknown hooks and token sets are retained as unsupported
episodes. LP baseline policies return `watch` until a structured live evidence
record proves deployment, token order, TickMath, hooks, position checkpoints,
complete receipts and gas denomination; the evidence status string alone does
not enable policy selection.

Fixture evidence covers in-range/out-of-range behavior, exact sqrt-price
amounts, integer TickMath and boundary fee-growth state, uint256 wrap,
owner/position mismatch, unsupported hooks/tokens, orphan/provisional
receipts, canonical recovery, duplicate delivery, residual inventory, gas
denomination debits and unreconciled gas liabilities. These fixtures validate
mechanics only; no live Robinhood deployment or receipt sample has passed the
gate, and no LP action can be submitted or funded by this code.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_lp.py
```
