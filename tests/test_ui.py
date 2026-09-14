from willfly.domain import Launch, Observation
from willfly.features.discovery import DiscoverySnapshot
from willfly.ui.dashboard import render_dashboard
from willfly.ui.signals import SignalInboxEntry


def test_dashboard_shows_cutoffs_lifecycle_quality_and_excluded_counts():
    launch = Launch(4663, "0x" + "1" * 40, None, None, ("https://example.test/event/1",), None, None, "2026-01-01T00:00:00Z", "unknown", (), "unknown")
    timeline = Observation(
        "token",
        launch.token,
        "2026-01-01T00:05:00Z",
        "2026-01-01T00:04:00Z",
        "2026-01-01T00:04:01Z",
        "timeline.v0.1",
        {"verified_buy_count": 1, "verified_token_in_atomic": "100", "ambiguous_activity_count": 1, "transfer_activity_count": 1, "gift_or_airdrop_count": 0},
        {"ambiguous_activity_excluded_from_verified_flow": "unknown"},
        "degraded",
        ("tx:1",),
    )
    snapshot = DiscoverySnapshot("2026-01-01T00:05:00Z", (launch,), (), 3, 1, ("launch_lifecycle_unknown",), "degraded", ("tx:1",))
    page = render_dashboard(snapshot, (timeline,))
    assert "2026-01-01T00:05:00Z" in page
    assert "unknown" in page
    assert "excluded activity 2" in page
    assert "https://example.test/event/1" in page


def test_dashboard_renders_manual_action_status_on_signal_row():
    snapshot = DiscoverySnapshot("2026-01-01T00:05:00Z", (), (), 0, 0, (), "healthy", ("fixture:dashboard",))
    signal = SignalInboxEntry(
        "proposal-1",
        "prediction-1",
        "model-1",
        "model-v1",
        "spot",
        "enter",
        "abstain",
        "research_only",
        {},
        "2026-01-01T00:00:00Z",
        "2026-01-01T01:00:00Z",
        {},
        (),
        "matched",
        ("spot_economic_readiness_gate_open",),
    )
    page = render_dashboard(snapshot, signals=(signal,))
    assert "Manual status" in page
    assert "matched" in page


def test_dashboard_renders_attached_model_registry_state():
    snapshot = DiscoverySnapshot("2026-01-01T00:05:00Z", (), (), 0, 0, (), "healthy", ("fixture:dashboard",))
    page = render_dashboard(
        snapshot,
        model_state={"active_version": "candidate-v2", "known_versions": ["active-v1", "candidate-v2"], "history": []},
    )
    assert "Model registry" in page
    assert "candidate-v2" in page
