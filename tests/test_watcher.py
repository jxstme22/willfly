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
