"""Render maintained task catalogues without resetting implementation status."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CATALOGUES = ("build-tasks", "next-build-tasks")


def render(catalogue):
    lines = [f"# {catalogue.get('title', 'Build task backlog')}",
             f"Version {catalogue['version']} | {catalogue['date']} | {len(catalogue['tasks'])} tasks",
             "The JSON catalogue is authoritative. DONE requires acceptance evidence and completed prerequisites; existing code and fixture coverage are tracked separately. Target paths may include planned files."]
    for phase in catalogue["phases"]:
        lines.append(f"## {phase['id']} - {phase['title']}")
        for task in catalogue["tasks"]:
            if task["phase"] != phase["id"]:
                continue
            lines += [f"### {task['id']} - {task['title']}",
                      f"**Status:** {task['status']} | **Owner role:** {task['owner_role']} | **Depends on:** " + (", ".join(task["depends_on"]) or "None"),
                      "**Target paths:** " + ", ".join(f"`{p}`" for p in task["target_paths"]),
                      task["work"], "**Done when:** " + task["acceptance"]]
            for key, label in (("status_evidence", "Evidence"), ("review_note", "Review note"), ("verification", "Verification")):
                if task.get(key):
                    value = task[key]
                    lines.append(f"**{label}:** " + ("; ".join(value) if isinstance(value, list) else value))
    return "\n\n".join(lines) + "\n"


if __name__ == "__main__":
    for name in CATALOGUES:
        source = ROOT / "docs" / f"{name}.json"
        if source.exists():
            source.with_suffix(".md").write_text(render(json.loads(source.read_text())))
