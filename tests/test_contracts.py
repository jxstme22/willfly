import json
from pathlib import Path

import pytest

from willfly.domain import AmbiguousContractError, TradeEvidence
from willfly.domain.contracts import (
    Launch,
    Observation,
    PoolIdentity,
    RawEvent,
    VendorAssessment,
    WalletCohort,
)


FIXTURES = Path(__file__).parent / "fixtures"
CONSTRUCTORS = {
    "raw_event": RawEvent.from_dict,
    "pool_identity": PoolIdentity.from_dict,
    "launch": Launch.from_dict,
    "trade_evidence": TradeEvidence.from_dict,
    "vendor_assessment": VendorAssessment.from_dict,
    "wallet_cohort": WalletCohort.from_dict,
    "observation": Observation.from_dict,
}


def _cases():
    return json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))


def test_valid_contracts_round_trip_and_preserve_large_quantities():
    for case in _cases()["valid"]:
        record = CONSTRUCTORS[case["type"]](case["record"])
        encoded = record.to_dict()
        assert encoded["schema_version"] == "0.1.0"
        if case["id"] == "canonical-raw-swap-log":
            assert encoded["payload"]["amount0_atomic"] == "90071992547409930000000000000000000001"
        assert CONSTRUCTORS[case["type"]](encoded).to_dict() == encoded


def test_invalid_contracts_reject_ambiguity():
    for case in _cases()["invalid"]:
        with pytest.raises(ValueError):
            CONSTRUCTORS[case["type"]](case["record"])


def test_no_payment_receipt_is_not_verified_spend():
    case = next(item for item in _cases()["valid"] if item["id"] == "flagged-buy-without-cash-leg")
    trade = TradeEvidence.from_dict(case["record"])
    assert trade.classification == "ambiguous"
    assert not trade.payment_legs
    assert trade.estimated_usd is True
    assert trade.valuation_method == "vendor_display_estimate"


def test_v4_pool_identity_does_not_collapse_to_manager():
    case = next(item for item in _cases()["valid"] if item["id"] == "v4-pool-with-native-currency")
    pool = PoolIdentity.from_dict(case["record"])
    assert pool.pool_id != pool.manager_or_factory
    assert pool.pool_address is None


def test_genuine_swap_requires_payment_and_receipt():
    case = next(item for item in _cases()["invalid"] if item["id"] == "genuine-swap-without-payment")
    with pytest.raises(AmbiguousContractError):
        TradeEvidence.from_dict(case["record"])
