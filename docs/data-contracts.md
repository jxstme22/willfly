# Canonical data contracts

Version 0.1.0 | 13 September 2026 | implemented in `src/willfly/domain/contracts.py`

All records carry `schema_version: 0.1.0` when serialized. The Python contracts
reject missing identity, timezone-free timestamps, non-canonical unsigned integer
strings and unsupported status values. Unknown is represented by `null` plus a
quality/missingness field; it is never silently converted to zero or false.

## Identity and lineage

`RawEvent` records chain ID, source and source schema version, block number/hash,
parent context, transaction hash, log index, event time, received time, payload,
ingestion run and canonical status. The logical key is
`(chain_id, block_hash, transaction_hash, log_index)`. Provisional, canonical,
orphaned and quarantined evidence remain distinct.

`PoolIdentity` requires a pool address for V3 and a `(manager, pool_id)` identity
for V4. Two V4 pools sharing a PoolManager therefore remain distinct. Currency
ordering, fee, tick spacing and hook identity are preserved. The zero address is
the only native-currency sentinel; WETH is a separate ERC-20 address.

`Launch` keeps creation time, first-seen time, origin confidence, lifecycle state,
creator (possibly unknown), creation evidence and linked pool IDs separate. A
launch with no linked pool is valid and remains queryable.

## Trade evidence

`TradeEvidence.classification` is exactly one of:

- `genuine_swap`: requires a readable payment leg and receipt leg;
- `transfer`: token movement without asserted payment;
- `gift_or_airdrop`: a transfer classified as non-purchase with evidence;
- `ambiguous`: unresolved cash-flow or route attribution.

Payment legs use exact atomic integer strings and retain asset, direction, sender,
recipient and raw evidence reference. A quoted or estimated USD value is separate
from quote-asset spend and requires an explicit valuation method. A vendor label
or `BUY` badge cannot satisfy the payment-leg requirement. Multi-hop route logs
are lineage, not separate wallet purchases. The V4 receipt join only admits exact
ERC-20 transfer legs or native ETH transaction value when the receipt and swap
transaction hashes agree; failed, malformed, indirect or missing cash flow remains
quarantined or ambiguous. Non-zero V4 hooks carry an unsupported-behavior flag and
are not treated as standard pool mechanics.

Trade evidence version `v0.2` additionally records `route_status`
(`verified`, `uncertain` or `unsupported`), a wallet-facing `buy`/`sell`
direction and explicit inbound refund legs. `genuine_swap` requires all three:
matched V4 issuer/pool/receipt-log evidence, a known wallet direction, and a
positive net input after refunds. Legacy records remain losslessly readable but
are excluded from verified timeline flow until revalidated. Unrelated multicall
transfers, unproved wrapped-native paths and native input without refund coverage
remain ambiguous rather than increasing a signal.

`VendorAssessment` stores reason flags, method version, source as-of time,
retrieval time, freshness, raw reference and unavailable state. Missing vendor
history cannot be backdated. `WalletCohort` stores membership and relationship
uncertainty as observed at a specific time; multiple wallets are not assumed to be
independent people.

`Observation` stores event and arrival cutoffs, feature version, values,
missingness, quality state and lineage. It is an as-of snapshot, not a mutable
view of the latest database.

## Exactness rules

- EVM quantities use canonical decimal strings, never floating-point numbers.
- Addresses, transaction hashes and V4 pool IDs are validated by byte length.
- Symbols are display-only and are not identity.
- Native ETH and WETH remain distinct.
- Raw suspicious or excluded activity is preserved; display filtering cannot delete
  evidence or change training eligibility implicitly.

The fixture suite covers V3/V4 identity, orphaned logs, missing creator metadata,
no-payment receipts, a genuine routed swap, estimated USD, stale vendor flags and
unknown cohort history.
