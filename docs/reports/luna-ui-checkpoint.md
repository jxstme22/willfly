# Willfly terminal UI checkpoint

Date: 2026-09-14

This checkpoint covers the isolated M1-06 dashboard/API implementation. The
server continues to consume `ReadOnlyStore` and persisted `ObservatoryProjection`
records. Empty stores show unknown or unavailable states rather than synthetic
signals, tokens, liquidity or experiment metrics.

## Delivered behavior

- Terminal-style, responsive semantic HTML with accessible tabs, labeled
  controls, visible focus rings, keyboard shortcuts (`/`, `Escape`, `?`),
  touch-sized buttons and reduced-motion CSS.
- Escaped first paint plus safe inert JSON state. Browser-rendered values use
  DOM text nodes, protecting untrusted evidence and metadata from injection.
- Search, filters, deterministic sort/tie-breaking and bounded cursor paging
  for launches, pools, timelines, signals, positions, exclusions and manual
  action status. `/catalog` and richer `/health` expose source counts and
  missingness.
- Detail panes, evidence fetches, exact-value copy feedback, explicit empty,
  loading, error, stale/degraded and unsupported states, viewport pause and
  URL-preserved view state.
- GET-only HTTP surface with `POST` rejected as `405`; cache disabled for
  local inspection responses.

## Verification

Focused UI/API, persisted projection, signal and action-linking tests pass.
The full suite passes with `PYTHONPATH=src` (the worktree is intentionally not
installed as a package). A rendered dashboard script passes `node --check`.
A live loopback server was opened in the in-app browser: the empty launch,
data-health and unavailable-experiments views rendered with the expected
states and keyboard-safe controls. The existing socket-restricted sandbox
required elevated access for that temporary loopback process; it was stopped
after inspection.

## Limits

The server receives an immutable store at process start, so refresh observes
newly available records only when the hosting process supplies them. Advanced
valuation, experiment metrics, shadow outcomes and chain-wide coverage remain
unavailable until their validated backend contracts are attached. No execution
or wallet mutation is exposed.
