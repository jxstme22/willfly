from pathlib import Path

from willfly.release.check import build_brain_release_report


def test_brain_release_report_is_research_only_and_preserves_open_gates() -> None:
    report = build_brain_release_report(Path(__file__).parents[1])
    assert report.status == "research_release_only"
    assert report.capabilities["signal_contracts"] == "available_manual_only"
    assert report.capabilities["automatic_execution"] == "disabled"
    assert report.capabilities["lp_recommendations"].startswith("research_only")
    assert "live labelled MaleCNS training and held-out comparison" in report.open_gates
