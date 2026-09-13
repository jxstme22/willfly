# Source matrix

Version 1.1 | 13 September 2026 | P0-02 in progress

This is an evidence ledger, not a promise of coverage. `observed` means a bounded
read probe returned the field. `documented` means a primary source describes it.
`candidate` means it is eligible for a later adapter but its acceptance gate is
still open.

| Source | Role | Status | What is established | Open gate |
|---|---|---|---|---|
| Robinhood public RPC | chain reads | observed + documented | Chain ID 4663, bounded live reads and receipt/log probes respond | archive depth, limits and production completeness |
| Robinhood sequencer feed | arrival-time context | documented only | Official docs publish the WSS endpoint | supported subscription behavior and timestamp semantics |
| Uniswap V4 PoolManager | pool initialization, swaps and liquidity logs | observed + documented | Address, successful deployment receipt, block 9070, runtime size/hash, ABI-manifest hash and a bounded live decode sample with all three supported families | independent 72-hour completeness audit and archive depth |
| Pons V2 | launch lifecycle candidate | candidate; gate open | Official source/ABI is pinned, current factory code is present at `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` (24,177 bytes), and a bounded 78k-block scan on 13 Sept 2026 decoded 1,130 `TokenLaunched`, 10 `LaunchSwept`, 10 `GraduationTokensPermanentlyLocked` and 10 `PoolGraduated` events (plus 127 unsupported logs) | historical-code archive unavailable via public RPC, non-graduate window coverage, 72-hour completeness |
| Pons V1 | historical comparison | documented candidate; retired | Project source publishes the V1 factory and describes its V3 launch flow | confirm historical coverage before any use; not selected for v0.1 |
| pools.trade | comparative launch source | documented comparison only | Uniswap support describes the product; Bitquery documentation lists four launch contracts | first-party deployment/ABI evidence, access terms and independent coverage |
| RHTrenches | optional trader/behavior comparison | UI observation only | Browser research observed tracked-wallet tape and warnings | no verified public integration API, cohort completeness, terms or history |
| Mezzanine | optional risk/social enrichment | advertised only | Product pages advertise scanner and graph capabilities | scanner was region-blocked in research environment; no API/result/accuracy verified |

## Verified network facts

Robinhood's official connection documentation states mainnet chain ID `4663`,
public RPC `https://rpc.mainnet.chain.robinhood.com`, sequencer feed
`wss://feed.mainnet.chain.robinhood.com`, sequencer URL
`https://sequencer.mainnet.chain.robinhood.com`, and ETH as the native gas asset.
The official contracts page lists WETH at
`0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73`.

Uniswap's official `contracts` deployment record lists Robinhood V4
PoolManager `0x8366a39cc670b4001a1121b8f6a443a643e40951` and deployment
transaction
`0x4fb28d4935866f462582c6c931c6f2705e55f5be5eb178c7d8d9329a95c44c41`.
The read receipt returned status `0x1`, block `9070`, and the current runtime
code probe returned 24,009 bytes with SHA-256
`6eb21c69298b064e37fcf8089a941ae096fe08c0f179b2d399567aef1b10585b`.
The code hash is an evidence fingerprint, not an EVM code identity claim.

The complete addresses and probe record are in
`configs/sources/robinhood-chain-v0.1.json`. The 13 Sept 2026 verification
decoded 1,249 `Swap`, 551 `ModifyLiquidity` and 12 `Initialize` logs from 1,853
raw PoolManager logs in a 679-block window (41 unsupported logs observed but not
claimed). A 39-page Pons scan over blocks `61616075`–`61694074` produced 1,130
`TokenLaunched`, 10 `LaunchSwept`, 10 `GraduationTokensPermanentlyLocked` and 10
`PoolGraduated` events (127 other logs observed). Pons logs carry a zero
`blockTimestamp` sentinel; hash-matched headers supply real event time
(sample block `61691574`). Logs and headers at the documented creation block
`26841846` are available (22 logs in the first 100 blocks), but historical code
at that block is unavailable via public RPC (`metadata is not found`). No signer,
broadcast endpoint or funded provider is configured.

## Evidence links

- [Robinhood connection documentation](https://docs.robinhood.com/chain/connecting/)
- [Robinhood token contracts](https://docs.robinhood.com/chain/contracts/)
- [Uniswap Robinhood deployment record](https://github.com/Uniswap/contracts/blob/main/deployments/4663.md)
- [Uniswap V4 source commit](https://github.com/Uniswap/v4-core/tree/56928a9)
- [Pons source and deployment notes](https://github.com/ponsdotdev/ponsfamily)
- [Pons V2 factory source at pinned commit](https://github.com/ponsdotdev/ponsfamily/blob/33c2281bfcf91f18ddc3e8497894ae764118ce37/contractsV2/src/v2/PonsV2LaunchFactory.sol)
- [Bitquery Pons API event reference](https://docs.bitquery.io/docs/blockchain/robinhood/pons-api/)
- [Pools.trade provider documentation](https://docs.bitquery.io/docs/blockchain/robinhood/pools-trade-api/)
- [RHTrenches](https://rhtrenches.com/)
- [Mezzanine](https://mezzanine.fund/)
