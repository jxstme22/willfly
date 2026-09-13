from willfly.features.labels import ForwardEpisode, build_forward_labels


def _episode(**overrides):
    values = {
        "episode_id": "episode-1",
        "subject_id": "token-1",
        "entry_event_time": "2026-01-01T00:00:10Z",
        "entry_available_at": "2026-01-01T00:00:11Z",
        "exit_event_time": "2026-01-01T00:04:00Z",
        "exit_available_at": "2026-01-01T00:04:01Z",
        "cost_atomic": 100,
        "proceeds_atomic": 90,
        "adverse_excursion_bps": 1500,
        "source_refs": ("episode:1",),
    }
    values.update(overrides)
    return ForwardEpisode(**values)


def test_forward_labels_are_causal_and_preserve_censored_and_unresolved_states():
    labels = build_forward_labels(
        observation_time="2026-01-01T00:00:00Z",
        observation_available_at="2026-01-01T00:00:01Z",
        episodes=[
            _episode(),
            _episode(episode_id="late", entry_event_time="2026-01-01T00:20:00Z"),
            _episode(episode_id="failed", failed=True),
            _episode(episode_id="censored", exit_event_time=None),
        ],
        horizons_seconds=(300, 900),
    )
    by_id = {label.episode_id: label for label in labels}
    assert by_id["episode-1"].status == "observed"
    assert by_id["episode-1"].net_return_bps == -1000
    assert by_id["censored"].status == "censored"
    assert by_id["failed"].status == "unresolved"
    assert by_id["failed"].net_return_bps is None
    assert "late" not in by_id
