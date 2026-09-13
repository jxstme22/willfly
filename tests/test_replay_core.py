import pytest

from willfly.replay.ledger import PortfolioLedger
from willfly.replay.scheduler import ReplayEvent, ReplayScheduler, ReplayTick


def test_replay_is_deterministic_and_withholds_late_events():
    events = [
        ReplayEvent("b", "2026-01-01T00:00:02Z", "2026-01-01T00:00:05Z", {"n": 2}),
        ReplayEvent("a", "2026-01-01T00:00:01Z", "2026-01-01T00:00:05Z", {"n": 1}),
        ReplayEvent("future", "2026-01-01T00:00:03Z", "2026-01-01T00:00:20Z", {"n": 3}),
    ]
    ticks = [ReplayTick("t1", "2026-01-01T00:00:10Z"), ReplayTick("t2", "2026-01-01T00:00:30Z")]
    first = ReplayScheduler(events).run(ticks)
    second = ReplayScheduler(events).run(ticks)
    assert first == second
    assert [event.event_id for event in first[0].newly_available] == ["a", "b"]
    assert [event.event_id for event in first[0].available_events] == ["a", "b"]
    assert [event.event_id for event in first[1].newly_available] == ["future"]


def test_ledger_separates_deposits_and_deducts_trade_fee_once():
    ledger = PortfolioLedger({"ETH": 1000})
    ledger.deposit("deposit", "ETH", 500, "funding:fixture")
    ledger.apply_trade("buy", spend_asset="ETH", spend_atomic=100, receive_asset="TOKEN", receive_atomic=250, source_ref="tx:buy", fee_asset="ETH", fee_atomic=3)
    ledger.apply_fee("withdraw", "ETH", 2, "tx:withdraw")
    assert ledger.balances == {"ETH": 1395, "TOKEN": 250}
    assert ledger.accounting_summary()["deposits"] == {"ETH": 500}
    assert ledger.accounting_summary()["fees"] == {"ETH": 5}
    assert sum(entry.delta_atomic for entry in ledger.entries if entry.entry_type == "fee") == -5
    with pytest.raises(ValueError):
        ledger.apply_trade("overspend", spend_asset="ETH", spend_atomic=10000, receive_asset="TOKEN", receive_atomic=1, source_ref="tx:bad")
    assert ledger.entries[-1].failed is True
