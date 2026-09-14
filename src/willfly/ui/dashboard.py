"""Dependency-free HTML dashboard for the local observatory."""

from __future__ import annotations

from html import escape
from typing import Mapping

from willfly.domain import Observation
from willfly.features.discovery import DiscoverySnapshot
from willfly.ui.signals import SignalInboxEntry


def render_dashboard(
    snapshot: DiscoverySnapshot,
    timelines: tuple[Observation, ...] = (),
    exclusions: tuple[Mapping[str, object], ...] = (),
    *,
    signals: tuple[SignalInboxEntry, ...] = (),
    positions: tuple[Mapping[str, object], ...] = (),
    training_state: Mapping[str, object] | None = None,
    model_state: Mapping[str, object] | None = None,
) -> str:
    """Render evidence and exclusions without changing the underlying dataset."""

    launch_rows = "".join(
        "<tr>"
        f"<td>{escape(launch.token)}</td>"
        f"<td>{escape(launch.lifecycle_state)}</td>"
        f"<td>{escape(launch.created_at or 'unknown')}</td>"
        f"<td>{escape(launch.first_seen_at)}</td>"
        f"<td>{escape(', '.join(launch.creation_evidence))}</td>"
        "</tr>"
        for launch in snapshot.launches
    ) or '<tr><td colspan="5">No launches available at this cutoff.</td></tr>'
    timeline_sections = "".join(_timeline_section(timeline) for timeline in timelines)
    missing = ", ".join(escape(item) for item in snapshot.missingness) or "none"
    exclusion_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('kind', 'unknown')))}</td>"
        f"<td>{escape(str(item.get('reason', 'unknown')))}</td>"
        f"<td><code>{escape(str(item.get('transaction_hash', item.get('logical_key', 'unknown'))))}</code></td>"
        "</tr>"
        for item in exclusions
    ) or '<tr><td colspan="3">No excluded rows in this projection.</td></tr>'
    signal_rows = "".join(
        "<tr>"
        f"<td>{escape(entry.market)}</td>"
        f"<td>{escape(entry.proposed_action)}</td>"
        f"<td>{escape(entry.displayed_action)}</td>"
        f"<td>{escape(entry.display_state)}</td>"
        f"<td>{escape(entry.model_version)}</td>"
        f"<td>{escape(entry.manual_status)}</td>"
        f"<td>{escape(', '.join(entry.reason_flags) or 'none')}</td>"
        "</tr>"
        for entry in signals
    ) or '<tr><td colspan="7">No signals available.</td></tr>'
    position_rows = "".join(
        "<tr>"
        f"<td>{escape(str(position.get('wallet', 'unknown')))}</td>"
        f"<td>{escape(str(position.get('pool_id', 'unknown')))}</td>"
        f"<td>{escape(str(position.get('position_id', 'unknown')))}</td>"
        f"<td>{escape(str(position.get('liquidity', 'unknown')))}</td>"
        f"<td>{escape(str(position.get('lifecycle_state', 'unknown')))}</td>"
        "</tr>"
        for position in positions
    ) or '<tr><td colspan="5">No observed positions.</td></tr>'
    training = training_state or {"status": "unknown", "reason": "training_state_unavailable"}
    models = model_state or {"status": "unknown", "reason": "model_registry_unavailable"}
    model_history = models.get("history", [])
    history_count = len(model_history) if isinstance(model_history, list) else 0
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Willfly Observatory</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:.45rem;text-align:left}}
.quality{{padding:.7rem;border-radius:.35rem;background:#f3f3f3}} .degraded{{background:#fff1d6}}
small{{color:#666}}</style></head><body>
<h1>Willfly Observatory</h1>
<p class="quality {escape(snapshot.quality_state)}"><strong>Quality: {escape(snapshot.quality_state)}</strong>
 &middot; cutoff {escape(snapshot.as_of_time)} &middot; canonical events {snapshot.canonical_event_count}
 &middot; unknown lifecycle {snapshot.unknown_lifecycle_count}</p>
<p><strong>Missingness:</strong> {missing}</p>
<h2>Launches</h2><table><thead><tr><th>Token</th><th>Lifecycle</th><th>Creation time</th>
<th>First observed</th><th>Evidence</th></tr></thead><tbody>{launch_rows}</tbody></table>
<h2>Token timelines</h2>{timeline_sections or '<p>No timeline available.</p>'}
<h2>Signal inbox</h2><table><thead><tr><th>Market</th><th>Proposed</th><th>Displayed</th><th>State</th><th>Model</th><th>Manual status</th><th>Reasons</th></tr></thead>
<tbody>{signal_rows}</tbody></table>
<h2>Observed positions</h2><table><thead><tr><th>Wallet</th><th>Pool</th><th>Position</th><th>Liquidity</th><th>State</th></tr></thead>
<tbody>{position_rows}</tbody></table>
<h2>Training</h2><p class="quality">Status: {escape(str(training.get('status', 'unknown')))} &middot; {escape(str(training.get('reason', 'none')))}</p>
<h2>Model registry</h2><p class="quality">Active: {escape(str(models.get('active_version', 'unknown')))}
 &middot; known versions: {escape(str(len(models.get('known_versions', []))))}
 &middot; history entries: {history_count}
 &middot; {escape(str(models.get('reason', 'local registry attached')))}</p>
<h2>Excluded evidence</h2><table><thead><tr><th>Kind</th><th>Reason</th><th>Reference</th></tr></thead>
<tbody>{exclusion_rows}</tbody></table>
<p><small>Raw rows and source claims remain available through their lineage references and the read-only evidence endpoint.</small></p>
</body></html>"""


def _timeline_section(timeline: Observation) -> str:
    values = timeline.values
    excluded = sum(
        int(values.get(key, 0))
        for key in ("ambiguous_activity_count", "transfer_activity_count", "gift_or_airdrop_count")
    )
    return (
        f"<section><h3>{escape(timeline.subject_id)}</h3>"
        f"<p>event cutoff {escape(timeline.as_of_time)}; latest arrival "
        f"{escape(timeline.latest_included_arrival_time or 'unknown')}; "
        f"verified buys {values.get('verified_buy_count', 0)}; excluded activity {excluded}</p>"
        f"<p>verified token inflow (atomic): {escape(str(values.get('verified_token_in_atomic', 'unknown')))}; "
        f"verified sells {values.get('verified_sell_count', 0)}; "
        f"token outflow (atomic): {escape(str(values.get('verified_token_out_atomic', 'unknown')))}; "
        f"missingness: {escape(', '.join(timeline.missingness) or 'none')}</p></section>"
    )
