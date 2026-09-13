# Scanner integration specification

Version 1.1 | 13 September 2026 | Accepted planning amendment; optional integration implementation pending

## Evidence and intended role

RHTrenches loaded a live tracked-wallet tape, closed positions, trader PnL, follow activity and fresh pools during browser inspection. It describes itself as read-only. Some displayed buy rows carried receipt/airdrop warnings and estimated values without a readable cash leg. These are UI observations, not independent transaction audits. The tracked-wallet cohort is not complete market coverage. Source: [RHTrenches](https://rhtrenches.com/).

Mezzanine advertises honeypot/rug heuristics and an X/KOL graph paid through FLORK credits. Its scanner was region-blocked in the research browsing environment. No scan result, accuracy metric or supported API was verified. The access result says nothing definitive about the user's location. Sources: [product descriptions](https://mezzanine.fund/), [scanner](https://scanner.mezzanine.fund/).

RHTrenches is an observation/comparison candidate; Mezzanine is an optional risk/social enrichment candidate. Neither is a required dependency for native collection. No public integration API has been verified for either. Browser-visible streaming does not establish permission or a stable contract for automated ingestion. Do not infer scanner availability from another Mezzanine product's status.

## Access investigation in P0-03

For each source record: official URL and dated evidence, supported API/export and authentication, usage/storage rights, pricing and limits, chain/protocol scope, cohort definition, historical depth, pagination, source/arrival timestamps, revisions, and stale/error behavior. Distinguish advertised, observed in UI, tested through a supported interface, and unavailable. Record observed response samples without credentials where access allows.

Use bounded reads. No subscription purchase, credit purchase, account creation or region-block workaround is needed for this assessment. If supported access cannot be established, document the gap and continue native collection and synthetic adapter fixtures. A completed source assessment is not a completed live integration. Native chain data remains the foundation; scanner comparison does not alone certify complete launch coverage.

## Required behavior and mapped tasks

| Requirement | Implementation tasks | Completion evidence |
|---|---|---|
| Classify actual swaps versus transfers, gifts and ambiguous receipts | P0-04, P0-06, P1-03 | Receipt/log fixtures reconcile payment and receipt legs, route attribution and token identity; uncertain classifications remain unknown |
| Keep quoted/estimated value separate from spend | P0-04, P1-03, P2-02 | A no-payment receipt cannot inflate verified spend or buying pressure; valuation method and quote asset are retained |
| Preserve raw suspicious activity and display exclusions | P1-01, P2-02, P2-05 | UI filtering changes display only; exclusions are counted and evidence remains queryable |
| Track source cohort and relationship uncertainty as of observation | P0-04, P2-02, P3-06 | Today's leaderboard cannot select yesterday's cohort; multiple wallets are not automatically independent people |
| Evaluate follower economics | P0-05, P3-03, P3-07, P4-01 | Signal-arrival replay uses our available fill and exit, with costs; leader profit can coexist with follower loss |
| Integrate optional supported read sources | P0-03, P6-02 | Timestamped normalized observations, raw lineage, method versions, duplicate handling, cache/retry and unavailable-source behavior |
| Separate contribution of each data source | P6-06 | No-scanner comparison, separate trader/risk/social ablations, cost and delay accounting across ordinary and fly-derived models |

Data contracts are defined in P0-04 before adapters. Use versioned trade evidence, vendor assessments and wallet cohorts; keep vendor payloads outside model-specific code. A later adapter can change without changing the meaning of a verified trade.

## Follower experiment

Research question: does confirmed buying interest remain actionable after we observe it?

Select cohorts using information available before evaluation. Record actual receipt time where possible; any reconstructed historical availability is explicitly modeled. Requote at signal receipt plus processing/submission delay, apply the shared allocation policy, and account for executable exit, gas, fees, failures and residual inventory. Never substitute a leader's entry price or displayed mark for our achievable outcome.

Compare simple following, confirmed flow and ordinary learned policies with the fly-derived candidate using identical information and costs. Candidate observations include verified net buying, concentration, retention, liquidity deterioration and independent evidence of wallet relationships. These are proposed features, not established alpha. Missing history may require prospective collection. Vendor PnL, aggregate safety scores and unverified buy labels are not training ground truth.

For LP, use scanner output only to nominate observations for the separately validated P7 pool ledger. Social activity alone cannot establish fee profitability or executable exit depth.

## Scope and sequencing

P0-P2 add access assessment, canonical evidence, validation and inspection. The full optional vendor read adapters and feature ablations remain in P6. The initial release remains a local read-only Observatory; this amendment adds no signer, trading route or autonomous capital allocation. The existing 77 IDs remain stable; acceptance criteria were expanded in the Markdown/JSON catalogue. Estimates are reviewed after P0 rather than assuming these additions are free.
