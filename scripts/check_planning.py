"""Validate catalogue dependencies, evidence references and generated Markdown."""
import json
from render_planning import ROOT, CATALOGUES, render


def main():
    for name in CATALOGUES:
        path = ROOT / "docs" / f"{name}.json"
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
            assert task["status"] in {"TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CONDITIONAL"}
            if task["status"] == "DONE":
                assert task.get("status_evidence"), task["id"]
                assert all(by_id[d]["status"] == "DONE" for d in task["depends_on"]), task["id"]
                for evidence in task["status_evidence"]:
                    assert (ROOT / evidence).exists(), (task["id"], evidence)
        assert path.with_suffix(".md").read_text() == render(catalogue), f"stale {name}.md"
        print(f"{name}: {len(tasks)} tasks; dependencies, DONE evidence and Markdown agree")


if __name__ == "__main__":
    main()
