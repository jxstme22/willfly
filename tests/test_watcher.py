import time

from willfly.learning.watcher import LearningWatcher, WatcherConfig


def test_watcher_persists_tasks_and_explicit_outage_state(tmp_path) -> None:
    path = tmp_path / "watcher.sqlite3"
    config = WatcherConfig(observation_interval_seconds=15)
    with LearningWatcher(path, config=config) as watcher:
        assert watcher.enqueue(task_id="observe-1", kind="observation", created_at="2026-09-14T00:00:00Z")
        assert not watcher.enqueue(task_id="observe-1", kind="observation", created_at="2026-09-14T00:00:00Z")
        watcher.finish_task(task_id="observe-1", status="completed", finished_at="2026-09-14T00:00:10Z")
        first = watcher.tick(observed_at="2026-09-14T00:00:15Z", personal_trade_count=0)
        assert first.status == "waiting"
        assert first.personal_trade_count == 0
        later = watcher.tick(observed_at="2026-09-14T00:01:00Z", personal_trade_count=0)
        assert later.status == "degraded"
        assert later.outage_seconds_since_previous_tick == 45
        assert later.waiting_reason == "outage_since_previous_tick"
    with LearningWatcher(path, config=config) as restarted:
        assert restarted.snapshot().outage_seconds_since_previous_tick == 45
        assert restarted.pending_tasks() == ()


def test_watcher_rejects_changed_persisted_config_identity(tmp_path) -> None:
    path = tmp_path / "watcher.sqlite3"
    with LearningWatcher(path, config_identity="config-a"):
        pass
    try:
        LearningWatcher(path, config=WatcherConfig(observation_interval_seconds=30), config_identity="config-b")
    except ValueError as exc:
        assert "config identity changed" in str(exc)
    else:  # pragma: no cover - assertion keeps the close path obvious
        raise AssertionError("changed watcher config identity was accepted")


def test_watcher_due_scheduler_persists_slots_and_coalesces_pending_work(tmp_path) -> None:
    path = tmp_path / "watcher.sqlite3"
    config = WatcherConfig(
        observation_interval_seconds=15,
        label_interval_seconds=60,
        training_interval_seconds=900,
        evaluation_interval_seconds=900,
    )
    with LearningWatcher(path, config=config) as watcher:
        first = watcher.schedule_due_tasks(observed_at="2026-09-14T00:00:00Z")
        assert {item.kind for item in first if item.scheduled} == {
            "observation",
            "labels",
            "training",
            "evaluation",
        }
        assert len(watcher.pending_tasks()) == 4
        immediate = watcher.schedule_due_tasks(observed_at="2026-09-14T00:00:01Z")
        assert {item.reason for item in immediate} == {"not_due"}
        for task in watcher.pending_tasks():
            watcher.finish_task(task_id=task["task_id"], status="completed", finished_at="2026-09-14T00:00:02Z")
        next_slot = watcher.schedule_due_tasks(observed_at="2026-09-14T00:00:15Z")
        assert {item.kind for item in next_slot if item.scheduled} == {"observation"}
        assert {item.reason for item in next_slot if not item.scheduled} == {"not_due"}
        coalesced = watcher.schedule_due_tasks(observed_at="2026-09-14T00:01:00Z")
        assert next(item for item in coalesced if item.kind == "observation").reason == "pending_task_coalesced"
        assert next(item for item in coalesced if item.kind == "labels").scheduled is True
        assert len(watcher.pending_tasks()) == 2
    with LearningWatcher(path, config=config) as restarted:
        assert len(restarted.pending_tasks()) == 2
        assert restarted.schedule_due_tasks(observed_at="2026-09-14T00:01:01Z")[0].reason == "pending_task_coalesced"


def test_watcher_recovers_running_tasks_and_executes_only_bound_callbacks(tmp_path) -> None:
    path = tmp_path / "watcher.sqlite3"
    with LearningWatcher(path) as watcher:
        watcher.enqueue(task_id="observation:1", kind="observation", created_at="2026-09-14T00:00:00Z")
        watcher.enqueue(task_id="labels:1", kind="labels", created_at="2026-09-14T00:00:00Z")
        with watcher._connection:
            watcher._connection.execute("UPDATE watcher_tasks SET status = 'running' WHERE task_id = 'observation:1'")
        executions = watcher.run_pending_tasks(
            observed_at="2026-09-14T00:00:10Z",
            callbacks={"observation": lambda row: None},
        )
        assert [item.to_dict() for item in executions] == [
            {
                "task_id": "observation:1",
                "kind": "observation",
                "status": "completed",
                "reason": None,
            }
        ]
        pending = watcher.pending_tasks()
        assert pending[0]["task_id"] == "labels:1"
        assert pending[0]["status"] == "queued"
        watcher.tick(observed_at="2026-09-14T00:00:11Z")
        assert watcher.snapshot().last_completed_stage == "observation"
        assert watcher.snapshot().last_completed_task_id == "observation:1"
    with LearningWatcher(path) as restarted:
        assert restarted.snapshot().last_completed_stage == "observation"
        assert restarted.snapshot().last_completed_task_id == "observation:1"
        assert restarted.snapshot().last_completed_at == "2026-09-14T00:00:10Z"


def test_watcher_records_callback_failure_without_losing_the_service_loop(tmp_path) -> None:
    path = tmp_path / "watcher.sqlite3"
    with LearningWatcher(path) as watcher:
        watcher.enqueue(task_id="training:1", kind="training", created_at="2026-09-14T00:00:00Z")

        def fail(_row):
            raise RuntimeError("training unavailable")

        executions = watcher.run_pending_tasks(
            observed_at="2026-09-14T00:00:10Z",
            callbacks={"training": fail},
        )
        assert executions[0].status == "failed"
        assert executions[0].reason == "callback_failed:RuntimeError"
        assert watcher.pending_tasks() == ()


def test_watcher_marks_overlong_training_callback_as_failed(tmp_path) -> None:
    path = tmp_path / "watcher.sqlite3"
    config = WatcherConfig(max_training_seconds=0.001)
    with LearningWatcher(path, config=config) as watcher:
        watcher.enqueue(task_id="training:budget", kind="training", created_at="2026-09-14T00:00:00Z")

        def overrun(_row):
            time.sleep(0.01)

        execution = watcher.run_pending_tasks(
            observed_at="2026-09-14T00:00:10Z",
            callbacks={"training": overrun},
        )[0]
        assert execution.status == "failed"
        assert execution.reason == "training_time_budget_exceeded"
