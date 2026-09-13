# M5 LP mechanics checkpoint

Status: M5-01 and M5-02 are `IN_PROGRESS` as of 2026-09-14. LP remains
`DISABLED_PENDING_EVIDENCE` in the product configuration.

The LP replay boundary now provides exact integer Q96 amount calculations from
caller-supplied protocol sqrt prices, rather than requiring a float tick
approximation. Fee-growth deltas use uint256 modular subtraction, so a valid
counter wrap does not erase accrued fees. Position identity and optional owner
identity are carried through lifecycle events; resize, collect, remove and
convert require an active matching position. Replayed action IDs are
idempotent and do not credit balances twice. Fee totals remain per token rather
than summing unlike assets as money, and gas is retained in an explicit
per-asset map (or `unknown:gas` when a fixture does not provide a denomination).
When a gas denomination is present in the supplied starting balances, the
amount is debited before the lifecycle action. Otherwise it remains in
`unreconciled_gas_by_asset` as a liability rather than becoming free balance;
unknown gas is never silently charged to token0 or token1.

The older `amounts_for_liquidity` linearized tick helper remains available as a
named counterfactual diagnostic for compatibility. It is not used as proof of
deployed V4 mechanics. The stress screen and policy selectors remain modeled
research artifacts until one pool family, hook behavior, observed position
checkpoints, gas denomination and complete receipts are verified.

Fixture evidence covers in-range/out-of-range behavior, exact sqrt-price
amounts, uint256 wrap, owner/position mismatch, orphan lifecycle events,
duplicate delivery, residual inventory, gas denomination debits and
unreconciled gas liabilities. No LP action can be submitted or funded by this
code.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_lp.py
```
