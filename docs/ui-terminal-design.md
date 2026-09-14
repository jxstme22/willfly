# Willfly terminal monitoring UI

User-approved direction: a terminal art style inspired by RHTrenches, with a fully working, data-rich monitoring interface. This is a product requirement for M1-06 and subsequent experiment views, not just a visual mockup.

## Visual direction

Use a near-black background, restrained charcoal panels, thin rules, compact spacing, monospace typography and aligned tabular numbers. Use off-white primary text, legible muted labels, and limited green/red/amber/cyan accents for states. Status must also have a text label or icon: color alone cannot convey buy/sell, freshness or errors.

Favor dense tables, a persistent status strip and split-pane inspection. Terminal character borders or small ASCII accents may appear in the title or separators, but the content remains semantic HTML with real links, buttons and inputs. Use practical readable text sizes, clear keyboard focus and sufficient contrast. No CRT distortion, scanlines, blinking text or animation that compromises reading data. Respect reduced-motion preferences.

Reference: [RHTrenches](https://rhtrenches.com/) provides a compact tape, time/size filters and separate trader/position views. Use that information density and operator-oriented feel as inspiration; Willfly must express its own data scope, lineage and uncertainty. Do not claim its feed is integrated unless supported access is verified.

## Monitor layout

```text
WILLFLY  /  OBSERVATORY        CHAIN 4663   SOURCE STATE   LAST UPDATE
HEAD / CAPTURED / CANONICAL    LAG   GAPS   QUARANTINE   RUN VERSION
[LAUNCHES] [TAPE] [POOLS] [DATA HEALTH] [EXPERIMENTS*] [SHADOW*]
Search token / pool / tx       Time range   Filters   Columns   Pause view
----------------------------------------------------------------------
SORTABLE DATA TABLE                         SELECTED ITEM / EVIDENCE
rows with exact IDs and source timestamps   lifecycle, receipt, flags
stable selection during refresh             raw evidence / explorer
----------------------------------------------------------------------
Rows / source coverage / exclusions         last refresh / connection
```

Starred views arrive with the corresponding validated research phase. Their absence must be stated clearly instead of rendering invented metrics.

## Data surfaces and availability

| View | Initial useful fields | Later additions / prerequisites |
|---|---|---|
| Launches | Token identity, creator if observed, creation versus first-seen time, lifecycle, linked pools, supported protocol, coverage and evidence | USD price, market cap/FDV and other vendor estimates only with their own source, valuation definition and as-of time |
| Tape | Event/arrival times, transaction, token/pool, action/direction, exact asset amounts, swap versus ambiguous receipt, origin flags, evidence | Net wallet flow after route/refund/deduplication validation; tracked-wallet cohort data after verified adapter access |
| Pools | Pool ID, currencies, fee/hook identity, supported status, liquidity-change events and last observation | Price/volume/depth after validated calculations; numeric V4 liquidity must not be mislabeled USD TVL or executable depth |
| Data health | Source connectivity, latest head, captured/canonical checkpoints, arrival lag, gaps, retries, quarantines and run/config IDs | Measured independent capture coverage and endurance-window progress when audits exist |
| Experiments | Explicit not-run / unavailable state until enabled | Dataset, model, config and split versions, comparison metrics and costs from actual reproducible experiment results |
| Shadow | Explicit not-started / blocked state until enabled | Hypothetical decisions, reconciled modeled inventory, equity, failures and explanations; never treat a proposal as a fill |

Use `unknown`, `unavailable`, `stale`, `unsupported` and `not yet collected` distinctly. Zero requires observed zero. Show capture scope and cohort limits; selected-source activity is not automatically chainwide activity. Never fill empty views with fabricated tokens, PnL or live-status indicators. Label synthetic demonstration mode conspicuously if used for tests or previews.

## Functional behavior

- Search by exact token address, pool ID and transaction; optional symbols/handles cannot replace identity.
- Filters and sortable column headings operate on the underlying query, with stable pagination/tie-breaking. Display active filters and excluded counts; clearing a filter restores results.
- Persist useful view state in URL parameters where practical. Refresh must preserve filters, keyboard focus, selected row and scroll position.
- Pause/resume controls pause the viewport, not background ingestion. Show pending new-row count while paused and provide a deliberate jump to latest.
- Support bounded polling or a supported streaming API. Show update time, reconnect state and stale data during outages; keep the last useful snapshot visible with a warning state.
- Selecting a row opens a detail pane with full IDs, source and arrival times, provenance, classification reasons and raw/explorer references. Copy controls confirm what was copied.
- Make window presets, search, filters, columns, sort, pagination, detail close, retry and export controls genuinely functional. Explain unavailable actions; do not ship decorative controls.
- Export the requested scope with a provenance manifest. Clearly distinguish the visible page, filtered results and full dataset, including limits and generation errors.
- Keyboard shortcuts: `/` focuses search, Escape closes detail, and documented nonconflicting navigation shortcuts may select tabs/rows. Never intercept normal text entry or browser shortcuts. Every shortcut has a mouse/touch equivalent and visible help.
- On narrow screens, prioritize essential columns and move detail into a separate view. Horizontal table scrolling is acceptable; do not shrink text into unreadability. Touch controls need usable hit areas.

## Acceptance evidence

M1-06 must demonstrate the terminal layout using persisted Observatory records in a fresh server process. Verify search, sort, pagination, row details, evidence links, copy, filters and refresh behavior with real backend responses; explicitly test loading, empty, error, outage and stale states. Assert there is no browser injection from untrusted token metadata.

Test keyboard-only operation and inspect desktop, tablet and narrow mobile layouts. Confirm long addresses and large atomic values remain available without rounding loss, focus survives refresh and viewport pause does not stop collection. Exercise an active launch, a non-graduate, a suspicious receipt and a gap/reorg case. Screenshots support visual review; integration tests establish the behavior.

Do not require trading buttons, wallet connection or funded execution to call this monitoring UI functional. Preserve the read-only scope. Keep the existing Python backend; a separate frontend framework is an implementation choice only if the required interactions justify it. Document any added build/deployment dependency.

## M1-06 implementation checkpoint

The local implementation now serves an escaped terminal monitor directly from
the Python read-only server. The first response includes the persisted
snapshot and explicit empty, unavailable and stale/degraded states. Its
browser layer queries `/launches`, `/pools`, `/timelines`, `/signals`,
`/positions`, `/exclusions`, `/actions` and `/health` using bounded cursor
pagination. Search is applied to the returned contract fields before sorting
and paging; filters, sort direction, view, page, selected detail and pause
state are kept in URL parameters. A paused viewport keeps the last useful
rows visible and reports pending rows when a refresh observes a newer page.

Row details expose exact IDs and evidence references. Evidence is loaded only
through the read-only `/evidence/<reference>` route, and copy controls use the
exact text without formatting or numeric rounding. The client creates dynamic
cells with `textContent`; server HTML and the inert initial-state JSON escape
HTML-significant characters, including hostile metadata. `POST` requests are
rejected with `405`.

The model and training panes report attached state or `unavailable`; they do
not infer metrics from an empty registry. The monitor remains display-only:
no wallet connection, signer, trade route or execution control was added.
Live evidence remains bounded by the supplied projection cutoff and source
lineage. See [the UI checkpoint report](reports/luna-ui-checkpoint.md) for
the verification record and remaining product limits.

## Implementation ownership

The continuing implementation task owns the dashboard, API, JSON catalogue, rendered backlog and implementation log. Incorporate this requirement into M1-06 work/acceptance and later M3/M4 views without overwriting current changes. Keep advanced financial fields gated by their actual data/valuation implementation. This brief records user intent; it does not assert that the UI is already built.
