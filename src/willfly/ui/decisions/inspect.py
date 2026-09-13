"""Show why an action was permitted using recorded evidence only."""

from __future__ import annotations

from html import escape
from typing import Mapping


def render_decision_inspection(decision: Mapping[str, object]) -> str:
    fields = "".join(f"<li><strong>{escape(str(key))}</strong>: {escape(str(value))}</li>" for key, value in sorted(decision.items()))
    return f"<section><h2>Decision evidence</h2><ul>{fields}</ul><p>LLM prose is a summary of recorded evidence, not an authority.</p></section>"
