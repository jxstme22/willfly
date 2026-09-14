"""Dependency-free terminal dashboard for the local observatory.

The dashboard deliberately has two layers: a useful, escaped server-side
snapshot for the first paint, and a small browser client for stateful queries
against the read-only HTTP contracts.  No values are invented by this module.
Missing values remain visibly ``unknown`` or ``unavailable``.
"""

from __future__ import annotations

import json
from html import escape
from typing import Mapping, Sequence

from willfly.domain import Observation
from willfly.features.discovery import DiscoverySnapshot
from willfly.ui.signals import SignalInboxEntry


_UNAVAILABLE = "unavailable"


def render_dashboard(
    snapshot: DiscoverySnapshot,
    timelines: tuple[Observation, ...] = (),
    exclusions: tuple[Mapping[str, object], ...] = (),
    *,
    signals: tuple[SignalInboxEntry, ...] = (),
    positions: tuple[Mapping[str, object], ...] = (),
    training_state: Mapping[str, object] | None = None,
    model_state: Mapping[str, object] | None = None,
    actions: tuple[Mapping[str, object], ...] = (),
    health_state: Mapping[str, object] | None = None,
) -> str:
    """Render an escaped terminal monitor from an as-of projection."""

    training = dict(training_state or {"status": _UNAVAILABLE, "reason": "training_state_unavailable"})
    models = dict(model_state or {"status": _UNAVAILABLE, "reason": "model_registry_unavailable"})
    health = dict(health_state or {})
    chain_id = health.get("chain_id")
    if chain_id is None and snapshot.launches:
        chain_id = snapshot.launches[0].chain_id
    state = _initial_state(
        snapshot,
        timelines,
        exclusions,
        signals=signals,
        positions=positions,
        training=training,
        models=models,
        actions=actions,
        health=health,
    )
    quality = _status(snapshot.quality_state)
    missing = ", ".join(snapshot.missingness) if snapshot.missingness else "none"
    counts = {
        "launches": len(snapshot.launches),
        "pools": len(snapshot.pools),
        "timelines": len(timelines),
        "signals": len(signals),
        "positions": len(positions),
        "exclusions": len(exclusions),
    }
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Willfly / Observatory</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0b0d0e; --panel:#121617; --panel-raised:#181d1e;
      --line:#2a3233; --line-strong:#3b4849; --ink:#e7ece8; --muted:#aab7b2;
      --quiet:#81918c; --green:#83d6a5; --amber:#f0c674; --red:#ff8e85; --cyan:#80d5df;
      --focus:#f0c674; --radius:4px; }}
    * {{ box-sizing:border-box; }} html {{ background:var(--bg); }}
    body {{ margin:0; min-width:320px; background:var(--bg); color:var(--ink);
      font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
      -webkit-font-smoothing:antialiased; }}
    button,input,select {{ border:1px solid var(--line-strong); border-radius:var(--radius);
      background:var(--panel-raised); color:var(--ink); font:inherit; min-height:40px; }}
    button {{ cursor:pointer; padding:.55rem .75rem; }} button:hover {{ border-color:var(--cyan); }}
    button:disabled,[aria-disabled="true"] {{ cursor:not-allowed; opacity:.55; }}
    button:focus-visible,input:focus-visible,select:focus-visible,[tabindex="0"]:focus-visible {{
      outline:2px solid var(--focus); outline-offset:2px; }}
    input,select {{ padding:.55rem .7rem; width:100%; }} label {{ color:var(--muted); display:grid; gap:.35rem; }}
    code,.mono {{ overflow-wrap:anywhere; }} .shell {{ margin:0 auto; max-width:1440px; padding:1rem; }}
    .masthead {{ align-items:baseline; display:flex; flex-wrap:wrap; gap:.75rem 1.25rem; }}
    .brand {{ color:var(--green); font-size:clamp(1.2rem,3vw,1.8rem); letter-spacing:.08em; }}
    .eyebrow {{ color:var(--quiet); font-size:.78rem; letter-spacing:.11em; text-transform:uppercase; }}
    .status-strip {{ align-items:center; border:1px solid var(--line); display:flex; flex-wrap:wrap;
      gap:.45rem 1.1rem; margin-top:1rem; padding:.65rem .75rem; background:var(--panel); }}
    .status-strip strong {{ color:var(--green); }} .status-strip[data-state="degraded"],.status-strip[data-state="stale"] {{ border-color:var(--amber); }}
    .status-strip[data-state="degraded"] strong,.status-strip[data-state="stale"] strong {{ color:var(--amber); }}
    .status-strip[data-state="unknown"] strong {{ color:var(--red); }} .status-item {{ color:var(--muted); }}
    .status-item b {{ color:var(--ink); font-weight:600; }} .tabs {{ display:flex; flex-wrap:wrap; gap:.5rem; margin:1rem 0 .75rem; }}
    .tab {{ color:var(--muted); }} .tab[aria-selected="true"] {{ background:var(--green); border-color:var(--green); color:var(--bg); }}
    .controls {{ align-items:end; display:grid; gap:.7rem; grid-template-columns:minmax(220px,2fr) repeat(3,minmax(120px,1fr)) auto; }}
    .control-actions {{ display:flex; flex-wrap:wrap; gap:.5rem; }} .control-actions button {{ white-space:nowrap; }}
    .hint {{ color:var(--quiet); font-size:.78rem; margin:.45rem 0 0; }}
    .notice {{ border:1px solid var(--line); margin:.75rem 0; padding:.7rem .8rem; }}
    .notice.warning {{ border-color:var(--amber); color:var(--amber); }} .notice.error {{ border-color:var(--red); color:var(--red); }}
    .notice.success {{ border-color:var(--green); color:var(--green); }} .notice[hidden],.view[hidden],.detail[hidden] {{ display:none; }}
    .view-heading {{ align-items:baseline; display:flex; flex-wrap:wrap; gap:.8rem; justify-content:space-between; margin:1.25rem 0 .55rem; }}
    .view-heading h2 {{ font-size:1rem; letter-spacing:.08em; margin:0; text-transform:uppercase; }} .view-heading span {{ color:var(--muted); font-size:.78rem; }}
    .table-wrap {{ border:1px solid var(--line); overflow-x:auto; }} table {{ border-collapse:collapse; min-width:760px; width:100%; }}
    th,td {{ border-bottom:1px solid var(--line); padding:.65rem .7rem; text-align:left; vertical-align:top; }}
    th {{ background:var(--panel); color:var(--muted); font-size:.76rem; letter-spacing:.06em; position:sticky; text-transform:uppercase; top:0; z-index:1; }}
    tr:last-child td {{ border-bottom:0; }} tbody tr:hover {{ background:#1b2222; }}
    .sort-button {{ background:transparent; border:0; color:inherit; min-height:32px; padding:.1rem 0; text-align:left; text-transform:uppercase; }}
    .sort-button[aria-sort="ascending"]::after {{ content:"  ↑"; color:var(--cyan); }} .sort-button[aria-sort="descending"]::after {{ content:"  ↓"; color:var(--cyan); }}
    .detail-trigger,.copy-button {{ color:var(--cyan); min-height:36px; padding:.35rem .5rem; }} .state {{ font-weight:600; }}
    .state.healthy,.state.active,.state.matched,.state.confirmed {{ color:var(--green); }} .state.stale,.state.degraded,.state.unknown,.state.pending,.state.research_only {{ color:var(--amber); }}
    .state.error,.state.invalidated,.state.expired,.state.failed {{ color:var(--red); }} .state.unsupported,.state.unavailable {{ color:var(--quiet); }}
    .detail {{ background:var(--panel); border:1px solid var(--line-strong); margin-top:1rem; padding:1rem; }}
    .detail-header {{ align-items:center; display:flex; gap:.75rem; justify-content:space-between; }} .detail-header h2 {{ font-size:1rem; margin:0; }}
    .detail-grid {{ display:grid; gap:.7rem 1rem; grid-template-columns:repeat(2,minmax(0,1fr)); margin-top:.8rem; }} .detail-field {{ border-top:1px solid var(--line); padding-top:.5rem; }}
    .detail-field dt {{ color:var(--quiet); font-size:.75rem; text-transform:uppercase; }} .detail-field dd {{ margin:.2rem 0 0; overflow-wrap:anywhere; }}
    .evidence-list {{ display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.75rem; }} .evidence-list button {{ color:var(--cyan); font-size:.8rem; overflow-wrap:anywhere; text-align:left; }}
    .pager {{ align-items:center; display:flex; flex-wrap:wrap; gap:.6rem; justify-content:space-between; padding:.75rem 0; }} .pager-controls {{ display:flex; gap:.5rem; }}
    footer {{ color:var(--quiet); display:flex; flex-wrap:wrap; gap:.5rem 1.2rem; margin-top:1rem; }}
    .sr-only {{ clip:rect(0,0,0,0); clip-path:inset(50%); height:1px; overflow:hidden; position:absolute; white-space:nowrap; width:1px; }}
    @media (max-width:900px) {{ .controls {{ grid-template-columns:minmax(220px,1fr) repeat(2,minmax(120px,1fr)); }} .control-actions {{ grid-column:1/-1; }} }}
    @media (max-width:600px) {{ .shell {{ padding:.75rem; }} .controls {{ grid-template-columns:1fr; }} .control-actions {{ grid-column:auto; }}
      .control-actions button {{ flex:1 1 42%; }} .detail-grid {{ grid-template-columns:1fr; }} th,td {{ padding:.55rem; }} }}
    @media (prefers-reduced-motion:no-preference) {{ button,input,select,tbody tr {{ transition:border-color 120ms ease,background-color 120ms ease; }} }}
  </style>
</head>
<body>
  <main class="shell" id="monitor">
    <header><div class="masthead"><span class="brand">WILLFLY</span><span class="eyebrow">/ observatory / read-only monitor</span></div>
      <div class="status-strip" data-state="{escape(quality)}" id="status-strip" role="status" aria-live="polite">
        <strong id="quality-label">SOURCE {escape(quality.upper())}</strong><span class="status-item">CHAIN <b id="chain-id">{escape(_display(chain_id))}</b></span>
        <span class="status-item">CUTOFF <b id="as-of">{escape(snapshot.as_of_time)}</b></span><span class="status-item">CANONICAL <b id="canonical-count">{snapshot.canonical_event_count}</b></span>
        <span class="status-item">UNKNOWN LIFECYCLE <b id="unknown-count">{snapshot.unknown_lifecycle_count}</b></span><span class="status-item">PENDING <b id="pending-count">0</b></span><span class="status-item">LAST REFRESH <b id="last-refresh">server snapshot</b></span>
      </div><p class="hint">Capture scope is bounded by this cutoff. Color is paired with a text state; unknown never means zero.</p>
    </header>
    <nav class="tabs" aria-label="Observatory views" role="tablist">
      <button class="tab" data-view="launches" role="tab" aria-selected="true">LAUNCHES</button><button class="tab" data-view="signals" role="tab" aria-selected="false">SIGNALS</button>
      <button class="tab" data-view="pools" role="tab" aria-selected="false">POOLS</button><button class="tab" data-view="timelines" role="tab" aria-selected="false">TAPE</button>
      <button class="tab" data-view="health" role="tab" aria-selected="false">DATA HEALTH</button><button class="tab" data-view="positions" role="tab" aria-selected="false">POSITIONS</button>
      <button class="tab" data-view="exclusions" role="tab" aria-selected="false">EXCLUSIONS</button><button class="tab" data-view="training" role="tab" aria-selected="false">EXPERIMENTS · UNAVAILABLE</button>
      <button class="tab" data-view="actions" role="tab" aria-selected="false">MANUAL STATUS</button>
    </nav>
    <form class="controls" id="query-controls"><label>Search token / pool / tx<input id="search" name="search" type="search" inputmode="search" autocomplete="off" placeholder="0x… or evidence ref" aria-describedby="search-help"></label>
      <label>Lifecycle / state<select id="state-filter" name="state"><option value="">All states</option><option value="active">active</option><option value="graduated">graduated</option><option value="non_graduate">non_graduate</option><option value="unknown">unknown</option></select></label>
      <label>Sort<select id="sort" name="sort"><option value="first_seen_at">first seen</option><option value="token">identity</option><option value="created_at">created</option><option value="lifecycle_state">state</option></select></label>
      <label>Window<select id="limit" name="limit"><option value="25">25 rows</option><option value="50">50 rows</option><option value="100">100 rows</option></select></label>
      <div class="control-actions"><button id="refresh" type="submit">Refresh</button><button id="pause" type="button" aria-pressed="false">Pause view</button><button id="help" type="button" aria-expanded="false">Keyboard help</button></div>
    </form><p class="hint" id="search-help">Press <kbd>/</kbd> to focus. Enter applies the query; URL state survives refresh.</p>
    <div class="notice" id="message" role="status" aria-live="polite" hidden></div><div class="notice" id="loading" role="status" aria-live="polite" hidden>Loading the selected source snapshot…</div><div class="notice warning" id="help-panel" hidden><strong>Keyboard:</strong> <kbd>/</kbd> search · <kbd>Esc</kbd> close detail · <kbd>?</kbd> toggle this help. Buttons and row details are keyboard reachable.</div>
    <p class="hint" id="active-filters">Filters: none · page 1</p>
    <section class="view" id="view-launches" data-view="launches" role="tabpanel" aria-label="Launches"><div class="view-heading"><h2>Launch registry</h2><span id="count-launches">{counts["launches"]} records · source evidence attached</span></div>
      <div class="table-wrap"><table><thead><tr><th><button class="sort-button" data-sort="token" aria-sort="none">Token identity</button></th><th>Lifecycle</th><th>Created</th><th>First seen</th><th>Linked pools / evidence</th><th>Inspect</th></tr></thead><tbody id="rows-launches">{_launch_rows(snapshot.launches)}</tbody></table></div></section>
    <section class="view" id="view-signals" data-view="signals" role="tabpanel" aria-label="Signals" hidden><div class="view-heading"><h2>Signal inbox</h2><span id="count-signals">{counts["signals"]} proposals · displayed action is gated</span></div>
      <div class="table-wrap"><table><thead><tr><th>Market</th><th>Proposed</th><th>Displayed</th><th>State</th><th>Model</th><th>Manual status</th><th>Reasons</th><th>Inspect</th></tr></thead><tbody id="rows-signals">{_signal_rows(signals)}</tbody></table></div></section>
    <section class="view" id="view-pools" data-view="pools" role="tabpanel" aria-label="Pools" hidden><div class="view-heading"><h2>Pool registry</h2><span id="count-pools">{counts["pools"]} records · numeric liquidity is not USD TVL</span></div>
      <div class="table-wrap"><table><thead><tr><th>Pool identity</th><th>Pair</th><th>Fee / hook</th><th>First observed</th><th>Trading state</th><th>Inspect</th></tr></thead><tbody id="rows-pools">{_pool_rows(snapshot.pools)}</tbody></table></div></section>
    <section class="view" id="view-timelines" data-view="timelines" role="tabpanel" aria-label="Tape" hidden><div class="view-heading"><h2>Token tape</h2><span id="count-timelines">{counts["timelines"]} observations · ambiguous activity stays excluded</span></div>
      <div class="table-wrap"><table><thead><tr><th>Subject</th><th>As of / latest arrival</th><th>Verified buys</th><th>Verified sells</th><th>Atomic flow</th><th>Quality</th><th>Inspect</th></tr></thead><tbody id="rows-timelines">{_timeline_rows(timelines)}</tbody></table></div></section>
    <section class="view" id="view-health" data-view="health" role="tabpanel" aria-label="Data health" hidden><div class="view-heading"><h2>Data health</h2><span>source checkpoints and missingness remain explicit</span></div>
      <div class="notice" id="health-summary">Quality is <strong>{escape(quality)}</strong>; missingness: {escape(missing)}.</div><dl class="detail-grid" id="health-fields"><div class="detail-field"><dt>Canonical events</dt><dd>{snapshot.canonical_event_count}</dd></div><div class="detail-field"><dt>Unknown lifecycle</dt><dd>{snapshot.unknown_lifecycle_count}</dd></div><div class="detail-field"><dt>Lineage refs</dt><dd>{len(snapshot.lineage)}</dd></div><div class="detail-field"><dt>Missingness</dt><dd>{escape(missing)}</dd></div></dl></section>
    <section class="view" id="view-positions" data-view="positions" role="tabpanel" aria-label="Positions" hidden><div class="view-heading"><h2>Observed positions</h2><span>{counts["positions"]} records · liquidity remains exact atomic state</span></div>
      <div class="table-wrap"><table><thead><tr><th>Wallet</th><th>Pool</th><th>Position</th><th>Liquidity</th><th>Lifecycle</th><th>Last observed</th><th>Inspect</th></tr></thead><tbody id="rows-positions">{_position_rows(positions)}</tbody></table></div></section>
    <section class="view" id="view-exclusions" data-view="exclusions" role="tabpanel" aria-label="Excluded evidence" hidden><div class="view-heading"><h2>Excluded evidence</h2><span>{counts["exclusions"]} rows · exclusions remain inspectable</span></div>
      <div class="table-wrap"><table><thead><tr><th>Kind</th><th>Reason</th><th>Reference</th><th>Inspect</th></tr></thead><tbody id="rows-exclusions">{_exclusion_rows(exclusions)}</tbody></table></div></section>
    <section class="view" id="view-training" data-view="training" role="tabpanel" aria-label="Experiments" hidden><div class="view-heading"><h2>Model registry / experiments</h2><span>research results only when a real registry is attached</span></div>
      <div class="notice warning">No experiment metrics are inferred from an empty registry. The attached state is shown below.</div><dl class="detail-grid"><div class="detail-field"><dt>Training</dt><dd id="training-status" class="state {_status(training.get("status"))}">{escape(_display(training.get("status")))}</dd></div><div class="detail-field"><dt>Training reason</dt><dd id="training-reason">{escape(_display(training.get("reason")))}</dd></div><div class="detail-field"><dt>Active model</dt><dd id="active-model">{escape(_display(models.get("active_version")))}</dd></div><div class="detail-field"><dt>Known versions</dt><dd id="known-model-count">{escape(_display(len(models.get("known_versions", [])) if isinstance(models.get("known_versions", []), list) else None))}</dd></div></dl></section>
    <section class="view" id="view-actions" data-view="actions" role="tabpanel" aria-label="Manual action status" hidden><div class="view-heading"><h2>Manual action status</h2><span>reported external actions; no execution controls</span></div>
      <div class="table-wrap"><table><thead><tr><th>Action</th><th>Instrument</th><th>Execution</th><th>Link state</th><th>Transaction</th><th>Inspect</th></tr></thead><tbody id="rows-actions">{_action_rows(actions)}</tbody></table></div></section>
    <aside class="detail" id="detail" aria-label="Selected item details" hidden><div class="detail-header"><h2 id="detail-title">Selected item</h2><button id="close-detail" type="button">Close detail</button></div><div class="detail-grid" id="detail-fields"></div><div><p class="eyebrow">Evidence and provenance</p><div class="evidence-list" id="detail-evidence"></div></div><div class="notice" id="evidence-result" hidden></div></aside>
    <div class="pager"><span id="page-status">Showing server snapshot</span><div class="pager-controls"><button id="prev-page" type="button" disabled>Previous</button><button id="next-page" type="button" disabled>Next</button></div></div>
    <footer><span id="footer-scope">Rows are exact contract values; atomic quantities are never rounded.</span><span id="footer-connection">Connection: initial snapshot</span><span>POST actions: rejected by read-only server.</span></footer>
  </main>
  <script type="application/json" id="initial-state">{_safe_json(state)}</script>
  <script>
  (() => {{
    "use strict";
    const initial = JSON.parse(document.getElementById("initial-state").textContent || "{{}}");
    const root = document.getElementById("monitor"), controls = document.getElementById("query-controls"), message = document.getElementById("message"), detail = document.getElementById("detail");
    const state = {{ view:"launches", page:0, sort:"first_seen_at", direction:"asc", paused:false, selected:null, nextCursor:null }};
    const viewNames = ["launches","signals","pools","timelines","health","positions","exclusions","training","actions"];
    const endpointFor = {{ launches:"/launches", signals:"/signals", pools:"/pools", timelines:"/timelines", positions:"/positions", exclusions:"/exclusions", actions:"/actions" }};
    const records = {{ launches:initial.launches || [], signals:initial.signals || [], pools:initial.pools || [], timelines:initial.timelines || [], positions:initial.positions || [], exclusions:initial.exclusions || [], actions:initial.actions || [] }};
    const rowBodies = {{ launches:document.getElementById("rows-launches"), signals:document.getElementById("rows-signals"), pools:document.getElementById("rows-pools"), timelines:document.getElementById("rows-timelines"), positions:document.getElementById("rows-positions"), exclusions:document.getElementById("rows-exclusions"), actions:document.getElementById("rows-actions") }};
    const filterValues = {{ launches:["active","graduated","non_graduate","unknown"], signals:["research_only","qualified_manual_proposal","expired","invalidated","abstain"], pools:["active","inactive","unknown"], timelines:["healthy","stale","degraded","unknown"], positions:["open","closed","unknown"], exclusions:[], actions:["reported","matched","ambiguous","failed","partial","not_executed"] }};
    const sortValues = {{ launches:[["first_seen_at","first seen"],["token","identity"],["created_at","created"],["lifecycle_state","state"]], pools:[["first_observed_at","first observed"],["pool_id","identity"],["trading_status","state"]], signals:[["created_at","created"],["expires_at","expires"],["market","market"],["display_state","state"],["manual_status","manual status"]], timelines:[["as_of_time","as of"],["subject_id","subject"],["quality_state","quality"]], positions:[["last_observed_at","last observed"],["liquidity","liquidity"],["lifecycle_state","state"],["wallet","wallet"]], exclusions:[["kind","kind"],["reason","reason"],["reference","reference"]], actions:[["action_time","action time"],["execution_status","execution"]] }};
    function text(value) {{ return value === null || value === undefined || value === "" ? "unknown" : String(value); }}
    function cell(value, className) {{ const node=document.createElement("td"); node.textContent=text(value); if(className) node.className=className; return node; }}
    function stateCell(value) {{ return cell(value,"state "+String(value || "unknown").replace(/[^a-z0-9_-]/gi,"_")); }}
    function inspect(label, action, id) {{ const node=document.createElement("button"); node.type="button"; node.className="detail-trigger"; node.dataset.action=action; node.dataset.id=id || ""; node.textContent=label; return node; }}
    function appendInspect(row, kind, id) {{ const td=document.createElement("td"); td.appendChild(inspect("View",kind,id)); row.appendChild(td); }}
    function clear(node) {{ while(node.firstChild) node.removeChild(node.firstChild); }}
    function empty(tbody, columns, copy) {{ clear(tbody); const row=document.createElement("tr"), td=cell(copy); td.colSpan=columns; row.appendChild(td); tbody.appendChild(row); }}
    function renderLaunches(items) {{ const body=rowBodies.launches; if(!items.length) return empty(body,6,"No launches match this query at the selected cutoff."); clear(body); items.forEach(item=>{{ const row=document.createElement("tr"); row.append(cell(item.token,"mono"),stateCell(item.lifecycle_state),cell(item.created_at),cell(item.first_seen_at),cell((item.linked_pool_ids || []).concat(item.creation_evidence || []).join(" · "))); appendInspect(row,"launch",item.token); body.appendChild(row); }}); }}
    function renderPools(items) {{ const body=rowBodies.pools; if(!items.length) return empty(body,6,"No pools match this query at the selected cutoff."); clear(body); items.forEach(item=>{{ const identity=item.identity || {{}}, row=document.createElement("tr"), id=identity.pool_id || identity.pool_address; row.append(cell(id,"mono"),cell([identity.currency0,identity.currency1].filter(Boolean).join(" / ")),cell([identity.fee,identity.hook ? "hook "+identity.hook : ""].filter(Boolean).join(" · ")),cell(item.first_observed_at),stateCell(item.trading_status)); appendInspect(row,"pool",id); body.appendChild(row); }}); }}
    function renderSignals(items) {{ const body=rowBodies.signals; if(!items.length) return empty(body,8,"No signals are available for this cutoff; readiness is not inferred."); clear(body); items.forEach(item=>{{ const row=document.createElement("tr"); row.append(cell(item.market),cell(item.proposed_action),cell(item.displayed_action),stateCell(item.display_state),cell(item.model_version),stateCell(item.manual_status),cell((item.reason_flags || []).join(" · "))); appendInspect(row,"signal",item.proposal_id); body.appendChild(row); }}); }}
    function renderTimelines(items) {{ const body=rowBodies.timelines; if(!items.length) return empty(body,7,"No token tape observations are available at this cutoff."); clear(body); items.forEach(item=>{{ const values=item.values || {{}}, row=document.createElement("tr"), flow=[values.verified_token_in_atomic ? "in "+values.verified_token_in_atomic : "",values.verified_token_out_atomic ? "out "+values.verified_token_out_atomic : ""].filter(Boolean).join(" · "); row.append(cell(item.subject_id,"mono"),cell([item.as_of_time,item.latest_included_arrival_time || "arrival unknown"].join(" · ")),cell(values.verified_buy_count),cell(values.verified_sell_count),cell(flow || "unknown"),stateCell(item.quality_state)); appendInspect(row,"timeline",item.subject_id); body.appendChild(row); }}); }}
    function renderActions(items) {{ const body=rowBodies.actions; if(!items.length) return empty(body,6,"No manually reported actions are attached to this snapshot."); clear(body); items.forEach(item=>{{ const action=item.action || {{}}, link=item.link || {{}}, row=document.createElement("tr"), instrument=action.instrument || {{}}; row.append(cell([action.market,action.action].filter(Boolean).join(" / ")),cell(instrument.identifier,"mono"),stateCell(action.execution_status),stateCell(link.status),cell(action.transaction_hash,"mono")); appendInspect(row,"action",action.action_id); body.appendChild(row); }}); }}
    function renderPositions(items) {{ const body=rowBodies.positions; if(!items.length) return empty(body,7,"No observed positions are attached to this snapshot."); clear(body); items.forEach(item=>{{ const row=document.createElement("tr"); row.append(cell(item.wallet,"mono"),cell(item.pool_id,"mono"),cell(item.position_id,"mono"),cell(item.liquidity,"mono"),stateCell(item.lifecycle_state),cell(item.last_observed_at)); appendInspect(row,"position",item.position_id); body.appendChild(row); }}); }}
    function renderExclusions(items) {{ const body=rowBodies.exclusions; if(!items.length) return empty(body,4,"No excluded rows in this projection."); clear(body); items.forEach((item,index)=>{{ const row=document.createElement("tr"), ref=item.transaction_hash || item.logical_key || "exclusion-"+index; row.append(cell(item.kind),cell(item.reason),cell(ref,"mono")); appendInspect(row,"exclusion",String(ref)); body.appendChild(row); }}); }}
    function renderView(view,items) {{ if(view==="launches") renderLaunches(items); else if(view==="signals") renderSignals(items); else if(view==="pools") renderPools(items); else if(view==="timelines") renderTimelines(items); else if(view==="positions") renderPositions(items); else if(view==="exclusions") renderExclusions(items); else if(view==="actions") renderActions(items); }}
    function showMessage(copy,kind) {{ message.textContent=copy; message.className="notice "+(kind || ""); message.hidden=!copy; }}
    function updateUrl() {{ const params=new URLSearchParams(location.search); params.set("view",state.view); params.set("page",String(state.page)); params.set("sort",state.sort); params.set("dir",state.direction); params.set("limit",document.getElementById("limit").value); const search=document.getElementById("search").value.trim(), filter=document.getElementById("state-filter").value; if(search) params.set("search",search); else params.delete("search"); if(filter) params.set("state",filter); else params.delete("state"); if(state.selected) params.set("selected",state.selected); else params.delete("selected"); if(state.paused) params.set("paused","1"); else params.delete("paused"); document.getElementById("active-filters").textContent="Filters: "+(search ? "search="+search : "none")+(filter ? " · state="+filter : "")+" · page "+(state.page+1); history.replaceState(null,"",location.pathname+"?"+params.toString()); }}
    function setFilterOptions(view) {{ const select=document.getElementById("state-filter"), old=select.value, values=filterValues[view] || []; while(select.options.length>1) select.remove(1); values.forEach(value=>{{ const option=document.createElement("option"); option.value=value; option.textContent=value; select.appendChild(option); }}); select.value=values.includes(old) ? old : ""; }}
    function setSortOptions(view) {{ const select=document.getElementById("sort"), values=sortValues[view] || sortValues.launches; while(select.options.length) select.remove(0); values.forEach(([value,label])=>{{ const option=document.createElement("option"); option.value=value; option.textContent=label; select.appendChild(option); }}); if(!values.some(([value])=>value===state.sort)) state.sort=values[0][0]; select.value=state.sort; }}
    function setView(view) {{ if(!viewNames.includes(view)) view="launches"; state.view=view; setFilterOptions(view); setSortOptions(view); document.querySelectorAll(".tab").forEach(tab=>tab.setAttribute("aria-selected",String(tab.dataset.view===view))); document.querySelectorAll(".view").forEach(panel=>panel.hidden=panel.dataset.view!==view); if(view==="training") showMessage("Experiments and shadow metrics are unavailable until a validated run is attached.","warning"); else if(view!=="health") showMessage("",""); updateUrl(); }}
    function queryFor(view) {{ const params=new URLSearchParams(), search=document.getElementById("search").value.trim(), filter=document.getElementById("state-filter").value, choices={{ launches:["first_seen_at","token","created_at","lifecycle_state"], pools:["first_observed_at","pool_id","trading_status"], signals:["created_at","expires_at","market","display_state","manual_status"], timelines:["as_of_time","subject_id","quality_state"], positions:["last_observed_at","liquidity","lifecycle_state","wallet"], exclusions:["kind","reason","reference"], actions:["action_time","execution_status"] }}, defaults={{ launches:"first_seen_at", pools:"first_observed_at", signals:"created_at", timelines:"as_of_time", positions:"last_observed_at", exclusions:"kind", actions:"action_time" }}; if(search) params.set("search",search); params.set("cursor",String(state.page*Number(document.getElementById("limit").value))); params.set("limit",document.getElementById("limit").value); if(!choices[view].includes(state.sort)) state.sort=defaults[view]; params.set("sort",state.sort); params.set("direction",state.direction); if(filter && ["launches","signals","pools","timelines","positions","exclusions","actions"].includes(view)) params.set(view==="signals" ? "state" : view==="timelines" ? "quality_state" : view==="pools" ? "trading_status" : view==="positions" ? "lifecycle" : view==="exclusions" ? "kind" : view==="actions" ? "execution_status" : "lifecycle",filter); return params.toString(); }}
    async function fetchCatalog() {{ try {{ const response=await fetch("/catalog",{{headers:{{Accept:"application/json"}}}}); if(!response.ok) throw new Error("server returned "+response.status); const catalog=await response.json(), counts=catalog.counts || {{}}, training=catalog.training || {{}}, models=catalog.models || {{}}; document.getElementById("as-of").textContent=text(catalog.as_of_time); document.getElementById("canonical-count").textContent=text(counts.canonical_events); document.getElementById("training-status").textContent=text(training.status); document.getElementById("training-reason").textContent=text(training.reason); document.getElementById("active-model").textContent=text(models.active_version); document.getElementById("known-model-count").textContent=text(Array.isArray(models.known_versions) ? models.known_versions.length : "unknown"); }} catch(error) {{ /* keep the last good catalog visible */ }} }}
    async function refresh() {{ await fetchCatalog(); if(state.view==="health" || state.view==="training") {{ await fetchHealth(); updateUrl(); return; }} const endpoint=endpointFor[state.view]; if(!endpoint) return; const scrollY=window.scrollY; root.setAttribute("aria-busy","true"); document.getElementById("loading").hidden=false; document.getElementById("footer-connection").textContent="Connection: refreshing…"; try {{ const response=await fetch(endpoint+"?"+queryFor(state.view),{{headers:{{Accept:"application/json"}}}}); if(!response.ok) throw new Error("server returned "+response.status); const payload=await response.json(), items=payload.items || []; state.nextCursor=payload.next_cursor; if(state.paused) {{ document.getElementById("pending-count").textContent=String(items.length); document.getElementById("page-status").textContent="Viewport paused · "+items.length+" newer rows pending"; }} else {{ records[state.view]=items; renderView(state.view,items); document.getElementById("pending-count").textContent="0"; document.getElementById("page-status").textContent="Showing "+items.length+" of "+text(payload.total); }} document.getElementById("footer-connection").textContent="Connection: read-only · updated "+new Date().toLocaleTimeString(); document.getElementById("last-refresh").textContent=new Date().toLocaleTimeString(); showMessage("",""); window.scrollTo(0,scrollY); }} catch(error) {{ document.getElementById("footer-connection").textContent="Connection: error"; showMessage("Could not refresh this view. The last useful snapshot remains visible; retry when the source is reachable.","error"); }} finally {{ document.getElementById("loading").hidden=true; root.removeAttribute("aria-busy"); updatePager(); updateUrl(); }} }}
    async function fetchHealth() {{ try {{ const response=await fetch("/health",{{headers:{{Accept:"application/json"}}}}); if(!response.ok) throw new Error("server returned "+response.status); const health=await response.json(); document.getElementById("quality-label").textContent="SOURCE "+text(health.quality_state || health.status).toUpperCase(); document.getElementById("status-strip").dataset.state=health.quality_state || "unknown"; document.getElementById("health-summary").textContent="Quality is "+text(health.quality_state)+"; details remain attached to the source response."; showMessage("",""); }} catch(error) {{ showMessage("Data health is unavailable. The previous projection remains visible.","error"); }} }}
    function findRecord(kind,id) {{ const list=kind==="launch" ? records.launches : kind==="pool" ? records.pools : kind==="signal" ? records.signals : kind==="timeline" ? records.timelines : kind==="position" ? records.positions : kind==="exclusion" ? records.exclusions : records.actions; return list.find(item=>{{ if(kind==="pool") {{ const identity=item.identity || {{}}; return (identity.pool_id || identity.pool_address)===id; }} if(kind==="action") return (item.action || {{}}).action_id===id; if(kind==="exclusion") return String(item.transaction_hash || item.logical_key || "")===id; return (item.token || item.proposal_id || item.subject_id || item.position_id)===id; }}); }}
    function field(label,value) {{ const wrap=document.createElement("div"), dt=document.createElement("dt"), dd=document.createElement("dd"); wrap.className="detail-field"; dt.textContent=label; dd.textContent=text(value); if(typeof value==="string" && value) {{ const copy=document.createElement("button"); copy.type="button"; copy.className="copy-button"; copy.dataset.copyText=value; copy.textContent="Copy"; dd.append(" ",copy); }} wrap.append(dt,dd); return wrap; }}
    async function copyValue(value,button) {{ try {{ await navigator.clipboard.writeText(value); button.textContent="Copied"; showMessage("Copied the exact value to the clipboard.","success"); window.setTimeout(()=>button.textContent="Copy",1200); }} catch(error) {{ showMessage("Clipboard access is unavailable; select the exact value in the detail pane.","warning"); }} }}
    function openDetail(kind,id) {{ const record=findRecord(kind,id); if(!record) return; state.selected=kind+":"+id; document.getElementById("detail-title").textContent=kind.toUpperCase()+" · "+id; const fields=document.getElementById("detail-fields"), evidence=document.getElementById("detail-evidence"); clear(fields); clear(evidence); const data=kind==="action" ? Object.assign({{}},record.action || {{}},{{link:record.link || {{}}}}) : kind==="pool" ? Object.assign({{}},record.identity || {{}},{{first_observed_at:record.first_observed_at,trading_status:record.trading_status,raw_event_refs:record.raw_event_refs}}) : record; Object.entries(data).forEach(([key,value])=>{{ if(["schema_version","instrument","confidence","portfolio_context","values","missingness","lineage","reason_flags","evidence_refs","creation_evidence","raw_event_refs","linked_pool_ids","link"].includes(key)) return; fields.appendChild(field(key,value)); }}); const refs=[].concat(record.evidence_refs || [],record.creation_evidence || [],record.raw_event_refs || [],record.lineage || [],record.source_refs || [],record.transaction_hash || [],record.evidence_ref || []); [...new Set(refs.filter(ref=>typeof ref==="string"))].forEach(ref=>{{ const item=document.createElement("button"); item.type="button"; item.dataset.evidenceRef=ref; item.textContent=ref; evidence.appendChild(item); }}); if(!evidence.childElementCount) {{ const emptyNode=document.createElement("span"); emptyNode.textContent="No evidence references attached."; evidence.appendChild(emptyNode); }} detail.hidden=false; detail.scrollIntoView({{block:"nearest"}}); updateUrl(); }}
    async function loadEvidence(ref) {{ const output=document.getElementById("evidence-result"); output.hidden=false; output.textContent="Loading evidence…"; try {{ const response=await fetch("/evidence/"+encodeURIComponent(ref),{{headers:{{Accept:"application/json"}}}}); if(!response.ok) throw new Error("server returned "+response.status); output.textContent=JSON.stringify(await response.json(),null,2); }} catch(error) {{ output.textContent="Evidence is unavailable for this reference; the identifier is preserved."; }} }}
    function readUrl() {{ const params=new URLSearchParams(location.search); state.view=params.get("view") || "launches"; state.page=Math.max(0,Number(params.get("page") || 0) || 0); state.sort=params.get("sort") || "first_seen_at"; state.direction=params.get("dir")==="desc" ? "desc" : "asc"; state.paused=params.get("paused")==="1"; document.getElementById("search").value=params.get("search") || ""; document.getElementById("state-filter").value=params.get("state") || ""; if(["25","50","100"].includes(params.get("limit"))) document.getElementById("limit").value=params.get("limit"); if([...document.getElementById("sort").options].some(option=>option.value===state.sort)) document.getElementById("sort").value=state.sort; const pause=document.getElementById("pause"); pause.setAttribute("aria-pressed",String(state.paused)); pause.textContent=state.paused ? "Resume view" : "Pause view"; setView(state.view); const selected=params.get("selected") || ""; if(selected.includes(":")) {{ const split=selected.indexOf(":"); window.setTimeout(()=>openDetail(selected.slice(0,split),selected.slice(split+1)),0); }} }}
    controls.addEventListener("submit",event=>{{ event.preventDefault(); state.page=0; refresh(); }});
    document.getElementById("sort").addEventListener("change",event=>{{ state.sort=event.target.value; state.page=0; refresh(); }});
    document.getElementById("limit").addEventListener("change",()=>{{ state.page=0; refresh(); }});
    document.getElementById("state-filter").addEventListener("change",()=>{{ state.page=0; refresh(); }});
    document.getElementById("pause").addEventListener("click",()=>{{ state.paused=!state.paused; const node=document.getElementById("pause"); node.setAttribute("aria-pressed",String(state.paused)); node.textContent=state.paused ? "Resume view" : "Pause view"; showMessage(state.paused ? "Viewport paused. Background collection continues; refresh or resume to apply new rows." : "Viewport resumed.",state.paused ? "warning" : "success"); updateUrl(); }});
    document.getElementById("help").addEventListener("click",()=>{{ const panel=document.getElementById("help-panel"); panel.hidden=!panel.hidden; document.getElementById("help").setAttribute("aria-expanded",String(!panel.hidden)); }});
    function updatePager() {{ document.getElementById("prev-page").disabled=state.page<=0; document.getElementById("next-page").disabled=!state.nextCursor; }}
    document.getElementById("close-detail").addEventListener("click",()=>{{ detail.hidden=true; state.selected=null; updateUrl(); }});
    document.getElementById("next-page").addEventListener("click",()=>{{ if(state.nextCursor) {{ state.page+=1; refresh(); }} }});
    document.getElementById("prev-page").addEventListener("click",()=>{{ if(state.page>0) {{ state.page-=1; refresh(); }} }});
    document.querySelectorAll(".tab").forEach(node=>node.addEventListener("click",()=>{{ state.page=0; state.nextCursor=null; setView(node.dataset.view); refresh(); }}));
    document.querySelectorAll(".sort-button").forEach(node=>node.addEventListener("click",()=>{{ const field=node.dataset.sort; state.direction=state.sort===field && state.direction==="asc" ? "desc" : "asc"; state.sort=field; state.page=0; refresh(); }}));
    root.addEventListener("click",event=>{{ const target=event.target.closest("[data-action],[data-evidence-ref],[data-copy-text]"); if(!target) return; if(target.dataset.copyText) return copyValue(target.dataset.copyText,target); if(target.dataset.evidenceRef) return loadEvidence(target.dataset.evidenceRef); openDetail(target.dataset.action,target.dataset.id); }});
    document.addEventListener("keydown",event=>{{ const tag=document.activeElement && document.activeElement.tagName; if(event.key==="/" && !["INPUT","TEXTAREA","SELECT"].includes(tag)) {{ event.preventDefault(); document.getElementById("search").focus(); }} else if(event.key==="Escape" && !detail.hidden) {{ detail.hidden=true; state.selected=null; updateUrl(); }} else if(event.key==="?" && !["INPUT","TEXTAREA","SELECT"].includes(tag)) document.getElementById("help").click(); }});
    const hadQuery=Boolean(location.search); readUrl(); if(hadQuery) refresh(); window.setInterval(()=>{{ if(document.visibilityState!=="hidden") refresh(); }},30000);
  }})();
  </script>
</body>
</html>"""


def _initial_state(snapshot: DiscoverySnapshot, timelines: Sequence[Observation], exclusions: Sequence[Mapping[str, object]], *, signals: Sequence[SignalInboxEntry], positions: Sequence[Mapping[str, object]], training: Mapping[str, object], models: Mapping[str, object], actions: Sequence[Mapping[str, object]], health: Mapping[str, object]) -> dict[str, object]:
    return {
        "as_of_time": snapshot.as_of_time, "quality_state": snapshot.quality_state,
        "canonical_event_count": snapshot.canonical_event_count, "unknown_lifecycle_count": snapshot.unknown_lifecycle_count,
        "missingness": list(snapshot.missingness), "lineage": list(snapshot.lineage),
        "launches": [launch.to_dict() for launch in snapshot.launches], "pools": [pool.to_dict() for pool in snapshot.pools],
        "timelines": [timeline.to_dict() for timeline in timelines], "exclusions": [dict(row) for row in exclusions],
        "signals": [entry.to_dict() for entry in signals], "positions": [dict(row) for row in positions],
        "training": dict(training), "models": dict(models), "actions": [dict(row) for row in actions], "health": dict(health),
    }


def _safe_json(value: object) -> str:
    """Embed JSON safely in an inert script element."""

    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return encoded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("/", "\\u002f")


def _status(value: object) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in {"healthy", "stale", "degraded", "unknown", "unsupported", "unavailable", "active", "matched", "confirmed", "pending", "research_only", "error", "invalidated", "expired", "failed"} else "unknown"


def _display(value: object) -> str:
    if value is None or value == "": return "unknown"
    if isinstance(value, (list, tuple)): return " · ".join(_display(item) for item in value) or "none"
    if isinstance(value, Mapping): return json.dumps(dict(value), sort_keys=True, ensure_ascii=True)
    return str(value)


def _launch_rows(launches: Sequence[object]) -> str:
    rows = []
    for launch in launches:
        pools = ", ".join(launch.linked_pool_ids) or "none"; refs = ", ".join(launch.creation_evidence) or "none"
        rows.append("<tr>" + f"<td class=\"mono\">{escape(_display(launch.token))}</td>" + f"<td class=\"state {_status(launch.lifecycle_state)}\">{escape(_display(launch.lifecycle_state))}</td>" + f"<td>{escape(_display(launch.created_at))}</td>" + f"<td>{escape(_display(launch.first_seen_at))}</td>" + f"<td><span class=\"mono\">{escape(pools)}</span><br><small>{escape(refs)}</small></td>" + f"<td><button class=\"detail-trigger\" type=\"button\" data-action=\"launch\" data-id=\"{escape(launch.token, quote=True)}\">View</button></td></tr>")
    return "".join(rows) or '<tr><td colspan="6">No launches match this query at the selected cutoff.</td></tr>'


def _pool_rows(pools: Sequence[object]) -> str:
    rows = []
    for pool in pools:
        identity = pool.identity; pool_id = identity.pool_id or identity.pool_address or "unknown"; pair = f"{identity.currency0} / {identity.currency1}"; fee = f"{identity.fee} · hook {identity.hook}" if identity.hook else str(identity.fee)
        rows.append("<tr>" + f"<td class=\"mono\">{escape(pool_id)}</td><td class=\"mono\">{escape(pair)}</td><td>{escape(fee)}</td><td>{escape(_display(pool.first_observed_at))}</td><td class=\"state {_status(pool.trading_status)}\">{escape(_display(pool.trading_status))}</td><td><button class=\"detail-trigger\" type=\"button\" data-action=\"pool\" data-id=\"{escape(pool_id, quote=True)}\">View</button></td></tr>")
    return "".join(rows) or '<tr><td colspan="6">No pools match this query at the selected cutoff.</td></tr>'


def _timeline_rows(timelines: Sequence[Observation]) -> str:
    rows = []
    for timeline in timelines:
        values = timeline.values; flow = []
        if values.get("verified_token_in_atomic") is not None: flow.append(f"in {values['verified_token_in_atomic']}")
        if values.get("verified_token_out_atomic") is not None: flow.append(f"out {values['verified_token_out_atomic']}")
        excluded = sum(int(values.get(key, 0) or 0) for key in ("ambiguous_activity_count", "transfer_activity_count", "gift_or_airdrop_count"))
        rows.append("<tr>" + f"<td class=\"mono\">{escape(timeline.subject_id)}</td><td>{escape(_display(timeline.as_of_time))}<br><small>arrival {escape(_display(timeline.latest_included_arrival_time))}</small></td><td>{escape(_display(values.get('verified_buy_count')))}</td><td>{escape(_display(values.get('verified_sell_count')))}</td><td class=\"mono\">{escape(' · '.join(flow) or 'unknown')}<br><small>excluded activity {excluded}</small></td><td class=\"state {_status(timeline.quality_state)}\">{escape(_display(timeline.quality_state))}</td><td><button class=\"detail-trigger\" type=\"button\" data-action=\"timeline\" data-id=\"{escape(timeline.subject_id, quote=True)}\">View</button></td></tr>")
    return "".join(rows) or '<tr><td colspan="7">No token tape observations are available at this cutoff.</td></tr>'


def _signal_rows(signals: Sequence[SignalInboxEntry]) -> str:
    rows = []
    for entry in signals:
        rows.append("<tr>" + f"<td>{escape(_display(entry.market))}</td><td>{escape(_display(entry.proposed_action))}</td><td>{escape(_display(entry.displayed_action))}</td><td class=\"state {_status(entry.display_state)}\">{escape(_display(entry.display_state))}</td><td>{escape(_display(entry.model_version))}</td><td class=\"state {_status(entry.manual_status)}\">{escape(_display(entry.manual_status))}</td><td>{escape(_display(entry.reason_flags) if entry.reason_flags else 'none')}</td><td><button class=\"detail-trigger\" type=\"button\" data-action=\"signal\" data-id=\"{escape(entry.proposal_id, quote=True)}\">View</button></td></tr>")
    return "".join(rows) or '<tr><td colspan="8">No signals are available for this cutoff; readiness is not inferred.</td></tr>'


def _position_rows(positions: Sequence[Mapping[str, object]]) -> str:
    rows = []
    for position in positions:
        position_id = str(position.get("position_id", "unknown"))
        rows.append(
            "<tr>"
            f"<td class=\"mono\">{escape(_display(position.get('wallet')))}</td>"
            f"<td class=\"mono\">{escape(_display(position.get('pool_id')))}</td>"
            f"<td class=\"mono\">{escape(position_id)}</td>"
            f"<td class=\"mono\">{escape(_display(position.get('liquidity')))}</td>"
            f"<td class=\"state {_status(position.get('lifecycle_state'))}\">{escape(_display(position.get('lifecycle_state')))}</td>"
            f"<td>{escape(_display(position.get('last_observed_at')))}</td>"
            f"<td><button class=\"detail-trigger\" type=\"button\" data-action=\"position\" data-id=\"{escape(position_id, quote=True)}\">View</button></td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="7">No observed positions are attached to this snapshot.</td></tr>'


def _exclusion_rows(exclusions: Sequence[Mapping[str, object]]) -> str:
    rows = []
    for index, item in enumerate(exclusions):
        reference = item.get("transaction_hash", item.get("logical_key", f"exclusion-{index}"))
        reference_text = _display(reference)
        rows.append(
            "<tr>"
            f"<td>{escape(_display(item.get('kind')))}</td><td>{escape(_display(item.get('reason')))}</td>"
            f"<td class=\"mono\">{escape(reference_text)}</td>"
            f"<td><button class=\"detail-trigger\" type=\"button\" data-action=\"exclusion\" data-id=\"{escape(reference_text, quote=True)}\">View</button></td></tr>"
        )
    return "".join(rows) or '<tr><td colspan="4">No excluded rows in this projection.</td></tr>'


def _action_rows(actions: Sequence[Mapping[str, object]]) -> str:
    rows = []
    for item in actions:
        action = item.get("action", item); link = item.get("link", {}) if isinstance(item, Mapping) else {}; action = action if isinstance(action, Mapping) else {}; link = link if isinstance(link, Mapping) else {}; instrument = action.get("instrument", {}); instrument = instrument if isinstance(instrument, Mapping) else {}; action_id = str(action.get("action_id", "unknown"))
        rows.append("<tr>" + f"<td>{escape(_display(action.get('market')))} / {escape(_display(action.get('action')))}</td><td class=\"mono\">{escape(_display(instrument.get('identifier')))}</td><td class=\"state {_status(action.get('execution_status'))}\">{escape(_display(action.get('execution_status')))}</td><td class=\"state {_status(link.get('status'))}\">{escape(_display(link.get('status')))}</td><td class=\"mono\">{escape(_display(action.get('transaction_hash')))}</td><td><button class=\"detail-trigger\" type=\"button\" data-action=\"action\" data-id=\"{escape(action_id, quote=True)}\">View</button></td></tr>")
    return "".join(rows) or '<tr><td colspan="6">No manually reported actions are attached to this snapshot.</td></tr>'


__all__ = ["render_dashboard"]
