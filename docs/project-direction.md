# Current project direction

Updated: 13 September 2026. This document records the user's decisions and research already discussed. No new research was required to make this update.

## Objective and scope

Build toward an adaptive agent that discovers and evaluates early crypto opportunities. Start with Robinhood Chain, new token launches, new pairs and memecoins. Spot trading is the initial decision task; selective LP is a distinct candidate action whose economics must be evaluated. Waiting and exiting are first-class actions. Later expansion should reuse data contracts and evaluation while adding chain-specific discovery and execution adapters.

The ambition is strong net financial performance, including with small capital. No guaranteed-return claim is justified. Measure capital recovered after complete entry and exit costs; reported volume, nominal APR and position win rate are insufficient objectives.

The user initially deferred PDFs while brainstorming, then explicitly requested an updated PDF and detailed build roadmap on 13 September 2026. The current PDF now packages this direction, training design, roadmap and complete task backlog. The original LP-range experiment remains useful background but is no longer the primary project plan.

## Working scientific thesis

Test whether a connectome-derived recurrent representation improves decisions from sequences of market observations: buyer arrivals, selling pressure, holder changes, liquidity additions/removals and execution conditions. Biological wiring supplies a candidate structural constraint. Market meaning, neural dynamics, training rules and action interfaces are engineered.

A useful target is recognizing when an opportunity changes: initial launch activity becomes sustained demand, liquidity deteriorates despite rising price, or a directional trade becomes a plausible fee-earning opportunity. These are hypotheses, not validated signals. Wallet relationships are clues rather than proof of common ownership or intent.

The proposed neural controller can participate in decision making. It is a computational model using biological measurements, not living tissue or an established uploaded mind. An LLM can interpret text and operate research tools; deterministic software should implement accounting, action validation and eventual transaction mechanics.

## Data choice

The existing literature review recommends FAFB with the Shiu implementation as a separate scientific reference and MaleCNS v1.0 as the initial commercially extensible data candidate. Its reviewed release uses CC BY 4.0, while the reviewed FAFB release uses CC BY-NC 4.0. Recheck exact release and dependency licenses before implementation. MaleCNS is not a drop-in reproduction of the FAFB model.

Start with an explicitly documented subnetwork or compact representation if sufficient. Whole-network size is not a success metric. Preserve IDs, graph orientation, filtering, signs, weight transformations and provenance.

## Robinhood Chain context

The prior research verified public mainnet documentation for chain ID 4663, native ETH and EVM compatibility. This is distinct from Robinhood's brokerage Crypto API. Mainnet was announced in July 2026. Chainwide activity snapshots supported investigating the ecosystem, but were not independently audited organic-volume measurements or evidence of liquidity in any particular new coin.

- [Official mainnet announcement](https://robinhood.com/us/en/newsroom/robinhood-accelerates-global-expansion-robinhood-chain-mainnet-stock-tokens-agentic-trading/?lang=en)
- [Official connection documentation](https://docs.robinhood.com/chain/connecting/)
- [DefiLlama chain dashboard](https://defillama.com/chain/robinhood-chain)

## Tools identified with the user

The user's “zenith bo” and “LP agents” were interpreted as the following likely matches. The user subsequently named RHTrenches and Mezzanine Scanner; the assessment and build requirements are in [the scanner integration plan](scanner-integration-plan.md). Capabilities below were checked in public documentation, not exercised through authenticated APIs.

| Tool | Documented capabilities | Proposed use and limitations |
|---|---|---|
| Zenith LP Bot | Telegram LP operations for Robinhood Uniswap V3/V4; user selects pool/range; swap and position opening; public pool explorer, calculator and position viewer | Execution-workflow reference. No documented public automation API was found in the reviewed pages. The provider says it generates and holds wallet keys, with export available. |
| LP Agent | Portfolio and copy-LP product; authenticated read API for pools and wallet positions; opening-position endpoint explicitly lists Robinhood V3/V4 | Candidate LP observation and outcome source. Public transaction-building routes are documented as Solana-only. App support does not establish Robinhood execution API support. |
| RHTrenches | Live tracked-wallet tape, closed trades, PnL, social-follow activity and fresh pools observed in the public UI | Discovery/behavior comparison source. Selected cohort, not full-chain coverage; displayed labels/PnL need reconciliation. Public integration API remains unverified. |
| Mezzanine Scanner | Advertised honeypot/rug heuristics and X/KOL graph, paid through FLORK credits | Optional risk/social enrichment. Scanner access was region-blocked in the research environment; scan accuracy and API access remain unverified. |
| Bitquery | Robinhood pool events, trades and streaming query documentation | Candidate launch/event ingestion. Verify factory coverage, timestamp semantics, retention, delay and commercial terms. |
| GMGN | Public Robinhood discovery/trading product description; separate agent API documentation | Candidate scanner comparison and enrichment. Robinhood support needs checking for each required API endpoint. |
| DEX Screener / GeckoTerminal | Pair/token analytics and discovery interfaces | Enrichment and cross-checking candidates; neither newly indexed nor first observed necessarily means newly launched. |

Sources:

- [RHTrenches](https://rhtrenches.com/) and [Mezzanine product descriptions](https://mezzanine.fund/), inspected during the scanner assessment on 13 September 2026.

- [Zenith](https://lpzenith.com/), [public tools](https://lpzenith.com/tools), [Telegram identity](https://t.me/zenith_lp_bot).
- [LP Agent](https://lpagent.io/), [API overview](https://docs.lpagent.io/api-reference/introduction), [opening positions](https://docs.lpagent.io/api-reference/positions/get-opening-lp-positions-for-an-owner), [public CLI repository](https://github.com/lpagent/cli).
- [LP Agent documentation index](https://docs.lpagent.io/llms.txt). Documentation is inconsistent in places: the overview names V3 while the opening-position endpoint names V3 and V4. Verify live coverage before relying on it.
- [Bitquery Robinhood pool guide](https://docs.bitquery.io/docs/blockchain/robinhood/robinhood-new-pools-trending/).
- [GMGN Robinhood product description](https://gmgn.ai/blog/robinhood-chain-meme-coins-with-gmgn/), [agent API](https://docs.gmgn.ai/index/gmgn-agent-api).
- [DEX Screener API](https://docs.dexscreener.com/api/reference), [GeckoTerminal Robinhood pools](https://www.geckoterminal.com/robinhood/pools).

### Accounting findings

LP Agent's published methodology measures the interval from liquidity addition to removal. Initial acquisition and final conversion can change actual realized outcomes. Our ledger must include those steps, gas, platform charges, failed transactions and residual inventory. Treat vendor PnL as an observation to reconcile, not ground truth for training.

Zenith currently lists $0.30 per open and per close. Its stated $0.60 round trip alone equals 3% of a $20 position or 0.6% of a $100 position, before other costs. These are arithmetic illustrations, not recommended position sizes or complete cost estimates. Recheck pricing before execution.

Sources: [LP Agent methodology](https://docs.lpagent.io/data-methodology), [Zenith pricing and custody](https://lpzenith.com/).

## Decisions versus open questions

Decided: Robinhood first; launch discovery and spot decisions first; LP evaluated separately; preserve complete histories including failures; compare biological models with strong ordinary alternatives; update the PDF and detailed build plan; no funded operation now. P4-P8 implementation machinery is now present, while live source, connectome, LP-family and prospective-window gates remain open.

Build specification: [roadmap](build-roadmap.md) and [task backlog](build-tasks.md). The first implementation target is Observatory v0.1, and the current checkpoint extends through P8 shadow machinery. P0-02/P0-03, connectome verification, LP pool-family verification and the 14-day/200-launch/99%-availability shadow gates remain open. The 64 research-build tasks and 13 conditional later tasks remain the full scope.

Open: exact launchpad/factory and protocol version; data completeness and latency; API access and budget; executable exit modeling; model timescale and topology; training target; capital scenarios; whether fly-derived structure contributes anything beyond the surrounding tools.

No claim of live reliability, profitable learning or biological superiority has been established.

## Build-plan update: scanner evidence and Luna handoff

Accepted additions: validate swap origin before computing buying pressure; measure hypothetical follower returns after signal arrival and execution costs; assess optional scanner APIs and preserve their uncertainty. The 77-task backlog is now version 1.1, with expanded implementation and acceptance criteria. Implementation follows the handoff in small, evidence-backed batches; the current checkpoint is recorded in [implementation-log.md](implementation-log.md). The PDF remains the prior review snapshot and does not include these latest amendments.
