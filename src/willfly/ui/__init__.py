"""Minimal inspection UI rendering."""

from willfly.ui.dashboard import render_dashboard

__all__ = ["render_dashboard"]
from willfly.ui.signals import SignalInboxEntry, build_signal_inbox

__all__ = ["SignalInboxEntry", "build_signal_inbox"]
