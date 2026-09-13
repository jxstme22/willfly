from willfly.features.labels import ForwardEpisode, build_forward_labels, outcome_from_forward_label


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


def test_forward_label_adapts_to_delayed_market_outcome_contract():
    label = build_forward_labels(
        observation_time="2026-01-01T00:00:00Z",
        observation_available_at="2026-01-01T00:00:02Z",
        episodes=[
            ForwardEpisode(
                "episode-adapt", "token", "2026-01-01T00:00:01Z", "2026-01-01T00:00:03Z",
                "2026-01-01T00:00:05Z", "2026-01-01T00:00:06Z", 100, 120, None, ("market:1",),
            )
        ],
        horizons_seconds=(60,),
    )[0]
    outcome = outcome_from_forward_label(label, prediction_id="prediction-1", target_id="spot_entry_net_return")
    assert outcome.outcome_kind == "observed_market"
    assert outcome.net_return_bps == 2000
    assert outcome.label_available_at == "2026-01-01T00:00:06Z"
