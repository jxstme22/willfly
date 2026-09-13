# Provider access and budget

Version 1.1 | 13 September 2026 | P0-03 in progress

## Bounded probe record

On 13 September 2026, a bounded read-only verification session queried the public
Robinhood RPC with `eth_chainId`, `eth_blockNumber`, `eth_getCode` for the V4
PoolManager and Pons V2 candidate, `eth_getTransactionReceipt` for the published
V4 deployment, and a 101-block `eth_getLogs` range for the PoolManager. The probe observed:

- chain ID `0x1237` (`4663`);
- head `0x3a93f54` (`61,423,444`) at probe time;
- non-empty code at both configured contract addresses;
- successful V4 deployment receipt at block `9070`;
- one early-range ownership log, not a trading coverage sample.

This establishes connectivity and identity only. It does not establish archive
history, event completeness, latency guarantees, rate limits or production
suitability. The raw facts and endpoint are recorded in the source manifest.

The subsequent bounded decoder check captured blocks `61436940`–`61437618`:
2,791 raw PoolManager logs produced 2,742 supported decodes (`Swap` 2,319,
`ModifyLiquidity` 405, `Initialize` 18), with 49 unsupported logs and no
malformed supported logs. A separate 20-block receipt check found 73 logs and
one successful receipt/log match. These are implementation and consistency
checks, not completeness, archive-depth or latency guarantees.

## Access matrix

| Source | Interface status | Auth/subscription | History/limits | v0.1 fallback |
|---|---|---|---|---|
| Robinhood public RPC | read endpoint tested | no key in probe | rate-limited per official terms; archive depth unmeasured | bounded polling and explicit gaps |
| Robinhood sequencer feed | URL documented; subscription not tested | likely provider/network access; not assumed | retention and arrival semantics unmeasured | RPC block/log reads with arrival time when received |
| Alchemy/QuickNode/Blockdaemon/dRPC/Validation Cloud | documented provider options | account/key required; no account created | plan limits and archive retention must be measured after selection | public RPC for bounded checks only |
| Bitquery pools.trade API | documented endpoint/source | access and plan not configured | pagination, retention and rate limits unmeasured | native logs; provider remains comparison/backfill candidate |
| RHTrenches | browser UI observed; public API unverified | no subscription purchased | cohort/history/terms not verified | native wallet evidence and unknown fields |
| Mezzanine | product pages advertised; scanner inaccessible in research environment | no credits or region workaround | API, history, accuracy and terms unverified | omit enrichment; mark source unavailable |

## Initial 24-hour estimate

This is a capacity estimate, not a measured vendor quote. For `C` configured
contract addresses, `B` blocks per day, and a polling interval of `p` seconds,
the conservative public-RPC polling budget is:

```text
blockNumber calls = ceil(86400 / p)
log calls          = ceil(86400 / p)
receipt calls      = observed event count (only for candidate swaps/launches)
```

The offline default uses `p = 15` seconds and no receipt calls until a log is
selected for decoding. That is 11,520 block-number calls plus 5,760 log calls
per contract range if a provider requires separate calls. A 101-block log probe
is the only historical range used in P0. A production plan must measure provider
limits before enabling this schedule; public RPC is not accepted as a
latency-sensitive or high-throughput guarantee.

Raw storage estimate uses the measured compressed fixture size plus a 3x planning
factor for payload variability. The budget remains `TBD` until a real 24-hour
sample is captured. No subscription or credits were purchased.

## Explicit blockers

1. Pons V2 ABI/source is pinned, but historical code at creation block `26841846` is unavailable via public RPC (`metadata is not found`); logs/headers at creation are available. An archive-code provider remains unselected.
2. Non-graduate window coverage and 72-hour completeness remain open (M1-07).
3. RHTrenches has no verified public integration API in this research.
4. Mezzanine scanner access/API was not verified; region restrictions are not bypassed.

## 13 September 2026 archive verification

Pons logs carry `blockTimestamp 0x0`; event time must come from hash-matched
`eth_getBlockByNumber` headers (verified on block `61691574`). A 39-page
2000-block scan demonstrates paged history access for all four Pons lifecycle
families, but sustained throughput, rate limits and a 72-hour completeness
audit remain unmeasured. Public RPC is a bounded-check source, not a
production archive guarantee.
