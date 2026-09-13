from willfly.policies.constraints import Candidate, allocate_candidates


def test_allocation_uses_one_shared_cash_ledger_and_deterministic_ties():
    result = allocate_candidates(
        [
            Candidate("b", "TOKEN-B", "2026-01-01T00:00:01Z", 100),
            Candidate("a", "TOKEN-A", "2026-01-01T00:00:01Z", 100),
            Candidate("c", "TOKEN-C", "2026-01-01T00:00:02Z", 200),
        ],
        cash_atomic=200,
        fixed_entry_atomic=100,
        max_positions=2,
    )
    assert [decision.candidate_id for decision in result.decisions if decision.accepted] == ["c", "a"]
    assert result.remaining_cash_atomic == 0
    assert result.decisions[2].reason == "max_concurrent_positions"


def test_no_adding_and_insufficient_cash_are_visible():
    result = allocate_candidates(
        [Candidate("same", "TOKEN-A", "2026-01-01T00:00:01Z", 100), Candidate("new", "TOKEN-B", "2026-01-01T00:00:02Z", 90)],
        cash_atomic=50,
        fixed_entry_atomic=100,
        max_positions=3,
        existing_positions=("TOKEN-A",),
    )
    assert result.decisions[0].reason == "position_already_open_no_adding"
    assert result.decisions[1].reason == "insufficient_simulation_cash"
