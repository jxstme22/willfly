from willfly.domain import Launch, Observation
from willfly.features.discovery import DiscoverySnapshot
from willfly.ui.dashboard import render_dashboard


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
