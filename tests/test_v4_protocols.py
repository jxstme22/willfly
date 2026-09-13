from dataclasses import replace
from typing import Any

import pytest

from willfly.adapters.protocols.v4 import (
    INITIALIZE_TOPIC,
    MODIFY_LIQUIDITY_TOPIC,
    SWAP_TOPIC,
    TRANSFER_TOPIC,
    DecodeError,
    UnsupportedV4Event,
    classify_trade_origin,
    deduplicate_decoded_events,
    decode_v4_event,
    pool_identity_from_initialize,
    trade_evidence_from_receipt,
)
from willfly.domain import PaymentLeg, RawEvent


MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
TOKEN = "0x1111111111111111111111111111111111111111"
WALLET = "0x2222222222222222222222222222222222222222"
TX = "0x" + "44" * 32
POOL_ID = "0x" + "11" * 32
ZERO_ADDRESS = "0x" + "0" * 40


def _word(value: int) -> str:
    if value < 0:
        value = (1 << 256) + value
    return f"{value:064x}"


def _address_word(address: str) -> str:
    return address[2:].rjust(64, "0")


def _event(
    topic: str,
    topics: list[str],
    words: list[str],
    *,
    index: int = 0,
    source: str = "fixture.rpc",
    transaction_hash: str = TX,
) -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": source,
            "source_schema_version": "rpc-log.v0.1",
            "block_number": 100,
            "block_hash": "0x" + "22" * 32,
            "parent_hash": "0x" + "33" * 32,
            "transaction_hash": transaction_hash,
            "log_index": index,
            "event_time": "2026-09-13T00:00:00Z",
            "received_time": "2026-09-13T00:00:01Z",
            "payload": {
                "address": MANAGER,
                "topics": [topic, *topics],
                "data": "0x" + "".join(words),
            },
            "ingestion_run": "protocol-test",
            "canonical_status": "canonical",
        }
    )


def _initialize(pool_id: str = POOL_ID, hooks: str = ZERO_ADDRESS) -> RawEvent:
    return _event(
        INITIALIZE_TOPIC,
        [pool_id, _address_word(ZERO_ADDRESS), _address_word(TOKEN)],
        [
            _word(10000),
            _word(10),
            _address_word(hooks),
            _word(1 << 96),
            _word(0),
        ],
    )


def _swap(index: int = 0, source: str = "fixture.rpc", transaction_hash: str = TX) -> RawEvent:
    return _event(
        SWAP_TOPIC,
        [POOL_ID, _address_word(WALLET)],
        [_word(-1000), _word(2500), _word(1 << 96), _word(123456), _word(-5), _word(3000)],
        index=index,
        source=source,
        transaction_hash=transaction_hash,
    )


def _transfer_log(asset: str, sender: str, recipient: str, amount: int, index: int = 0) -> dict[str, Any]:
    return {
        "address": asset,
        "topics": [TRANSFER_TOPIC, _address_word(sender), _address_word(recipient)],
        "data": "0x" + _word(amount),
        "logIndex": hex(index),
    }


def test_initialize_swap_and_modify_liquidity_decode_with_exact_fields():
    initialized = decode_v4_event(_initialize())
    assert initialized.event_type == "Initialize"
    assert initialized.pool_id == POOL_ID
    assert initialized.fields["currency0"] == "0x0000000000000000000000000000000000000000"
    assert initialized.fields["currency1"] == TOKEN
    assert initialized.fields["fee"] == 10000
    assert initialized.fields["tick_spacing"] == 10
    assert initialized.reason_flags == ()
    identity = pool_identity_from_initialize(initialized, chain_id=4663, manager=MANAGER)
    assert identity.pool_id == POOL_ID
    assert identity.manager_or_factory == MANAGER

    swap = decode_v4_event(_swap())
    assert swap.sender == WALLET
    assert swap.fields["amount0"] == -1000
    assert swap.fields["amount1"] == 2500
    assert swap.fields["liquidity"] == "123456"

    modified = decode_v4_event(
        _event(
            MODIFY_LIQUIDITY_TOPIC,
            [POOL_ID, _address_word(WALLET)],
            [_word(-120), _word(120), _word(-100000), _word(7)],
        )
    )
    assert modified.event_type == "ModifyLiquidity"
    assert modified.fields["tick_lower"] == -120
    assert modified.fields["liquidity_delta"] == -100000
    assert modified.fields["salt"] == "0x" + "0" * 63 + "7"


def test_nonzero_hook_is_explicitly_flagged_for_review():
    initialized = decode_v4_event(_initialize(hooks=MANAGER))
    assert initialized.fields["hooks"] == MANAGER
    assert initialized.reason_flags == ("unsupported_hook_behavior",)


def test_two_pool_ids_under_one_manager_remain_distinct():
    first = pool_identity_from_initialize(decode_v4_event(_initialize()), chain_id=4663, manager=MANAGER)
    second_id = "0x" + "12" * 32
    second = pool_identity_from_initialize(
        decode_v4_event(_initialize(pool_id=second_id)), chain_id=4663, manager=MANAGER
    )
    assert first.manager_or_factory == second.manager_or_factory == MANAGER
    assert first.pool_id != second.pool_id


def test_malformed_and_unsupported_events_are_not_silently_decoded():
    malformed = replace(_swap(), payload={"topics": [SWAP_TOPIC, POOL_ID], "data": "0x00"})
    with pytest.raises(DecodeError):
        decode_v4_event(malformed)
    unsupported = replace(_swap(), payload={"topics": ["0x" + "ff" * 32, POOL_ID], "data": "0x"})
    with pytest.raises(UnsupportedV4Event):
        decode_v4_event(unsupported)


def test_overlapping_delivery_deduplicates_but_keeps_source_lineage():
    first = decode_v4_event(_swap(source="rpc"))
    second = decode_v4_event(_swap(source="provider-replay"))
    result = deduplicate_decoded_events([first, second])
    assert len(result) == 1
    assert set(result[0].raw_lineage) == {first.raw_lineage[0], second.raw_lineage[0]}


def _payment(asset: str, amount: str, direction: str, sender: str, recipient: str, ref: str) -> PaymentLeg:
    return PaymentLeg(asset, amount, direction, sender, recipient, ref)


def test_routed_swap_becomes_one_verified_wallet_purchase():
    trade = classify_trade_origin(
        transaction_hash="0x" + "55" * 32,
        wallet=WALLET,
        token=TOKEN,
        swap_events=[decode_v4_event(_swap()), decode_v4_event(_swap(index=1))],
        payment_legs=[_payment("native:ETH", "1000", "out", WALLET, MANAGER, "raw:payment")],
        receipt_legs=[_payment(TOKEN, "2500", "in", MANAGER, WALLET, "raw:receipt")],
        as_of_time="2026-09-13T00:00:02Z",
        retrieved_time="2026-09-13T00:00:03Z",
        raw_event_refs=["raw:payment", "raw:receipt"],
    )
    assert trade.classification == "genuine_swap"
    assert len(trade.payment_legs) == 1
    assert "multi_hop_route_collapsed_to_one_wallet_purchase" in trade.reason_flags


def test_no_payment_receipt_stays_ambiguous_even_with_vendor_buy_claim():
    trade = classify_trade_origin(
        transaction_hash="0x" + "66" * 32,
        wallet=WALLET,
        token=TOKEN,
        swap_events=[decode_v4_event(_swap())],
        payment_legs=[],
        receipt_legs=[_payment(TOKEN, "2500", "in", MANAGER, WALLET, "raw:receipt")],
        as_of_time="2026-09-13T00:00:02Z",
        retrieved_time="2026-09-13T00:00:03Z",
        raw_event_refs=["raw:receipt"],
        vendor_claims=["vendor_buy_label_only"],
        estimated_usd_value="123456",
        valuation_method="vendor_display_estimate",
    )
    assert trade.classification == "ambiguous"
    assert not trade.payment_legs
    assert trade.estimated_usd is True
    assert "no_readable_cash_leg" in trade.reason_flags


def test_transfer_and_airdrop_are_not_verified_swaps():
    trade = classify_trade_origin(
        transaction_hash="0x" + "77" * 32,
        wallet=WALLET,
        token=TOKEN,
        swap_events=[],
        payment_legs=[],
        receipt_legs=[_payment(TOKEN, "500", "in", MANAGER, WALLET, "raw:airdrop")],
        as_of_time="2026-09-13T00:00:02Z",
        retrieved_time="2026-09-13T00:00:03Z",
        raw_event_refs=["raw:airdrop"],
        activity_kind="gift_or_airdrop",
    )
    assert trade.classification == "gift_or_airdrop"


def test_receipt_join_builds_exact_erc20_payment_and_receipt_legs():
    transaction_hash = "0x" + "88" * 32
    quote = "0x3333333333333333333333333333333333333333"
    receipt = {
        "transactionHash": transaction_hash,
        "logs": [
            _transfer_log(quote, WALLET, MANAGER, 1000),
            _transfer_log(TOKEN, MANAGER, WALLET, 2500, index=1),
        ],
    }
    trade = trade_evidence_from_receipt(
        transaction_hash=transaction_hash,
        wallet=WALLET,
        token=TOKEN,
        receipt=receipt,
        transaction={"from": WALLET, "to": MANAGER, "value": "0x0"},
        swap_events=[decode_v4_event(_swap(transaction_hash=transaction_hash))],
        quote_assets=[quote],
        as_of_time="2026-09-13T00:00:02Z",
        retrieved_time="2026-09-13T00:00:03Z",
    )
    assert trade.classification == "genuine_swap"
    assert [(leg.asset, leg.amount_atomic, leg.direction) for leg in trade.payment_legs] == [(quote, "1000", "out")]
    assert [(leg.asset, leg.amount_atomic, leg.direction) for leg in trade.receipt_legs] == [(TOKEN, "2500", "in")]
    assert trade.quote_asset == quote


def test_receipt_join_accepts_native_eth_value_as_an_exact_payment_leg():
    transaction_hash = "0x" + "99" * 32
    trade = trade_evidence_from_receipt(
        transaction_hash=transaction_hash,
        wallet=WALLET,
        token=TOKEN,
        receipt={
            "transactionHash": transaction_hash,
            "logs": [_transfer_log(TOKEN, MANAGER, WALLET, 2500)],
        },
        transaction={"from": WALLET, "to": MANAGER, "value": "0x3e8"},
        swap_events=[decode_v4_event(_swap(transaction_hash=transaction_hash))],
        quote_assets=["native:ETH"],
        as_of_time="2026-09-13T00:00:02Z",
        retrieved_time="2026-09-13T00:00:03Z",
    )
    assert trade.classification == "genuine_swap"
    assert trade.payment_legs[0].asset == "native:ETH"
    assert trade.payment_legs[0].amount_atomic == "1000"


def test_receipt_join_keeps_missing_cash_flow_ambiguous():
    transaction_hash = "0x" + "aa" * 32
    trade = trade_evidence_from_receipt(
        transaction_hash=transaction_hash,
        wallet=WALLET,
        token=TOKEN,
        receipt={
            "transactionHash": transaction_hash,
            "logs": [_transfer_log(TOKEN, MANAGER, WALLET, 2500)],
        },
        transaction={"from": "0x4444444444444444444444444444444444444444", "to": MANAGER, "value": "0x0"},
        swap_events=[decode_v4_event(_swap(transaction_hash=transaction_hash))],
        quote_assets=["0x3333333333333333333333333333333333333333"],
        as_of_time="2026-09-13T00:00:02Z",
        retrieved_time="2026-09-13T00:00:03Z",
        vendor_claims=["vendor_buy_label_only"],
        estimated_usd_value="123456",
        valuation_method="vendor_display_estimate",
    )
    assert trade.classification == "ambiguous"
    assert not trade.payment_legs
    assert "no_readable_cash_leg" in trade.reason_flags


def test_receipt_join_quarantines_malformed_erc20_transfer():
    transaction_hash = "0x" + "bb" * 32
    with pytest.raises(DecodeError):
        trade_evidence_from_receipt(
            transaction_hash=transaction_hash,
            wallet=WALLET,
            token=TOKEN,
            receipt={
                "transactionHash": transaction_hash,
                "logs": [
                    {
                        "address": TOKEN,
                        "topics": [TRANSFER_TOPIC, _address_word(MANAGER), _address_word(WALLET)],
                        "data": "0x",
                    }
                ],
            },
            transaction=None,
            swap_events=[decode_v4_event(_swap(transaction_hash=transaction_hash))],
            quote_assets=[],
            as_of_time="2026-09-13T00:00:02Z",
            retrieved_time="2026-09-13T00:00:03Z",
        )


def test_receipt_join_rejects_failed_receipts_and_cross_transaction_events():
    transaction_hash = "0x" + "cc" * 32
    with pytest.raises(DecodeError, match="failed transaction"):
        trade_evidence_from_receipt(
            transaction_hash=transaction_hash,
            wallet=WALLET,
            token=TOKEN,
            receipt={"transactionHash": transaction_hash, "status": "0x0", "logs": []},
            transaction=None,
            swap_events=[],
            quote_assets=[],
            as_of_time="2026-09-13T00:00:02Z",
            retrieved_time="2026-09-13T00:00:03Z",
        )
    with pytest.raises(DecodeError, match="does not match receipt"):
        trade_evidence_from_receipt(
            transaction_hash=transaction_hash,
            wallet=WALLET,
            token=TOKEN,
            receipt={"transactionHash": transaction_hash, "logs": []},
            transaction=None,
            swap_events=[decode_v4_event(_swap())],
            quote_assets=[],
            as_of_time="2026-09-13T00:00:02Z",
            retrieved_time="2026-09-13T00:00:03Z",
        )
