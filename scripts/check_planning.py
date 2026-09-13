"""Validate catalogue dependencies, evidence references and generated Markdown."""
import json
from pathlib import Path
from render_planning import ROOT, CATALOGUES, render


ALLOWED_STATUSES = {"TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CONDITIONAL"}


def _validate_tasks(path: Path, *, require_markdown: bool) -> set[str]:
    catalogue = json.loads(path.read_text())
    tasks = catalogue["tasks"]
    assert catalogue["task_count"] == len(tasks)
    by_id = {task["id"]: task for task in tasks}
    assert len(by_id) == len(tasks)
    complete = set()
    visiting = set()

    def visit(task_id):
        assert task_id in by_id, task_id
        assert task_id not in visiting, f"cycle at {task_id}"
        if task_id in complete:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id]["depends_on"]:
            visit(dependency)
        visiting.remove(task_id)
        complete.add(task_id)

    for task in tasks:
        visit(task["id"])
        assert task["status"] in ALLOWED_STATUSES
        if task["status"] == "DONE":
            assert task.get("status_evidence"), task["id"]
            assert all(by_id[d]["status"] == "DONE" for d in task["depends_on"]), task["id"]
            for evidence in task["status_evidence"]:
                assert (ROOT / evidence).exists(), (task["id"], evidence)
    if require_markdown:
        assert path.with_suffix(".md").read_text() == render(catalogue), f"stale {path.name}.md"
    return set(by_id)


def _validate_brain_catalogue() -> set[str]:
    path = ROOT / "docs" / "brain-product-tasks.json"
    task_ids = _validate_tasks(path, require_markdown=False)
    catalogue = json.loads(path.read_text())
    assert Path(ROOT / catalogue["product_brief"]).exists()
    assert Path(ROOT / catalogue["execution_plan"]).exists()
    assert catalogue["implementation_model_id"] == "gpt-5.6-luna"
    assert catalogue["reasoning_effort"] == "xhigh"
    return task_ids


def _validate_loop_plan(brain_task_ids: set[str]) -> None:
    path = ROOT / "docs" / "luna-build-loops.json"
    plan = json.loads(path.read_text())
    assert plan["handoff"] == "docs/luna-extra-high-handoff.md"
    assert (ROOT / plan["handoff"]).exists()
    assert plan["loop"]
    assert plan["model"]["id"] == "gpt-5.6-luna"
    assert plan["model"]["reasoning_effort"] == "xhigh"
    assert len({goal["id"] for goal in plan["goals"]}) == len(plan["goals"])
    for goal in plan["goals"]:
        assert goal.get("goal") and goal.get("done_when")
        assert all(task_id in brain_task_ids for task_id in goal.get("tasks", [])), goal["id"]
    for authority in plan["authorities"]:
        assert (ROOT / authority).exists(), authority
    repair = plan["repair_stage"]
    assert (ROOT / repair["checkpoint"]).exists()
    assert (ROOT / repair["coordinator_review"]).exists()


def main():
    for name in CATALOGUES:
        path = ROOT / "docs" / f"{name}.json"
        task_ids = _validate_tasks(path, require_markdown=True)
        print(f"{name}: {len(task_ids)} tasks; dependencies, DONE evidence and Markdown agree")
    brain_task_ids = _validate_brain_catalogue()
    _validate_loop_plan(brain_task_ids)
    print(f"brain-product-tasks: {len(brain_task_ids)} tasks; dependencies and references agree")
    print("luna-build-loops: goal/task identities, authorities and repair references agree")


if __name__ == "__main__":
    main()
