from willfly.replay.execution import PoolQuote, simulate_fill, simulate_follower_round_trip


def _quote(reserve_in: int, reserve_out: int, observed: str = "2026-01-01T00:00:00Z") -> PoolQuote:
    return PoolQuote("pool:1", "ETH", "TOKEN", reserve_in, reserve_out, 30, observed)


def test_fill_is_exact_and_explicitly_handles_unsupported_or_missing_state():
    fill = simulate_fill(_quote(1_000_000, 2_000_000), input_atomic=10_000, submitted_at="2026-01-01T00:00:01Z", processing_delay_seconds=2)
    assert fill.status == "filled"
    assert fill.output_atomic == 19743
    assert fill.fee_atomic == 30
    assert fill.available_at == "2026-01-01T00:00:03+00:00"
    assert simulate_fill(None, input_atomic=10, submitted_at="2026-01-01T00:00:01Z").status == "missing_state"
    assert simulate_fill(_quote(1000, 1000), input_atomic=10, submitted_at="2026-01-01T00:00:01Z").status == "filled"
    unsupported = PoolQuote("pool:hook", "ETH", "TOKEN", 1000, 1000, 30, "2026-01-01T00:00:00Z", False)
    result = simulate_fill(unsupported, input_atomic=10, submitted_at="2026-01-01T00:00:01Z")
    assert result.status == "unsupported"


def test_follower_can_be_unprofitable_even_when_entry_and_exit_state_exist():
    result = simulate_follower_round_trip(
        _quote(1_000_000, 2_000_000),
        PoolQuote("pool:1", "TOKEN", "ETH", 2_000_000, 900_000, 30, "2026-01-01T00:00:00Z"),
        quote_input_atomic=10_000,
        signal_received_at="2026-01-01T00:00:01Z",
        processing_delay_seconds=3,
    )
    assert result.status == "completed"
    assert result.net_quote_atomic is not None and result.net_quote_atomic < 0
