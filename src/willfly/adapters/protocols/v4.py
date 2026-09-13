"""Uniswap V4 event decoding and evidence-preserving trade classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from willfly.domain import PaymentLeg, PoolIdentity, RawEvent, TradeEvidence


INITIALIZE_TOPIC = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
MODIFY_LIQUIDITY_TOPIC = "0xf208f4912782fd25c7f114ca3723a2d5dd6f3bcc3ac8db5af63baa85f711d5ec"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

EVENT_TOPICS = {
    INITIALIZE_TOPIC: "Initialize",
    SWAP_TOPIC: "Swap",
    MODIFY_LIQUIDITY_TOPIC: "ModifyLiquidity",
}


class DecodeError(ValueError):
    """Raised when a supported event cannot be decoded safely."""


class UnsupportedV4Event(DecodeError):
    """Raised when a PoolManager log is outside the supported event subset."""


@dataclass(frozen=True)
class DecodedV4Event:
    event_type: str
    pool_id: str
    sender: str | None
    fields: Mapping[str, Any]
    raw_event_key: tuple[int, str | None, str | None, int | None]
    raw_lineage: tuple[str, ...]
    reason_flags: tuple[str, ...] = ()


def decode_v4_event(event: RawEvent) -> DecodedV4Event:
    """Decode one raw PoolManager log and retain its raw logical lineage."""

    payload = event.payload
    topics = payload.get("topics")
    data = payload.get("data")
    if not isinstance(topics, list) or not topics or not all(isinstance(topic, str) for topic in topics):
        raise DecodeError("V4 event topics are missing or malformed")
    if not isinstance(data, str):
        raise DecodeError("V4 event data is missing or malformed")
    topic0 = topics[0].lower()
    event_type = EVENT_TOPICS.get(topic0)
    if event_type is None:
        raise UnsupportedV4Event(f"unsupported PoolManager topic: {topic0}")
    pool_id = _topic_bytes32(topics, 1, "pool_id")
    words = _data_words(data)
    lineage = (_raw_ref(event),)

    if event_type == "Initialize":
        _require_lengths(topics, words, topic_count=4, word_count=5)
        hooks = _word_address(words[2], "hooks")
        fields = {
            "currency0": _topic_address(topics, 2, "currency0"),
            "currency1": _topic_address(topics, 3, "currency1"),
            "fee": _unsigned(words[0], 24, "fee"),
            "tick_spacing": _signed(words[1], 24, "tick_spacing"),
            "hooks": hooks,
            "sqrt_price_x96": str(_unsigned(words[3], 160, "sqrt_price_x96")),
            "tick": _signed(words[4], 24, "tick"),
        }
        reason_flags = () if hooks == "0x" + "0" * 40 else ("unsupported_hook_behavior",)
        return DecodedV4Event(event_type, pool_id, None, fields, event.logical_key, lineage, reason_flags)

    sender = _topic_address(topics, 2, "sender")
    if event_type == "Swap":
        _require_lengths(topics, words, topic_count=3, word_count=6)
        fields = {
            "amount0": _signed(words[0], 128, "amount0"),
            "amount1": _signed(words[1], 128, "amount1"),
            "sqrt_price_x96": str(_unsigned(words[2], 160, "sqrt_price_x96")),
            "liquidity": str(_unsigned(words[3], 128, "liquidity")),
            "tick": _signed(words[4], 24, "tick"),
            "fee": _unsigned(words[5], 24, "fee"),
        }
        return DecodedV4Event(event_type, pool_id, sender, fields, event.logical_key, lineage)

    _require_lengths(topics, words, topic_count=3, word_count=4)
    fields = {
        "tick_lower": _signed(words[0], 24, "tick_lower"),
        "tick_upper": _signed(words[1], 24, "tick_upper"),
        "liquidity_delta": _signed(words[2], 256, "liquidity_delta"),
        "salt": _word_bytes32(words[3], "salt"),
    }
    return DecodedV4Event(event_type, pool_id, sender, fields, event.logical_key, lineage)


def pool_identity_from_initialize(event: DecodedV4Event, *, chain_id: int, manager: str) -> PoolIdentity:
    if event.event_type != "Initialize":
        raise DecodeError("pool identity requires an Initialize event")
    return PoolIdentity(
        chain_id=chain_id,
        protocol="uniswap_v4",
        manager_or_factory=manager,
        pool_address=None,
        pool_id=event.pool_id,
        currency0=event.fields["currency0"],
        currency1=event.fields["currency1"],
        fee=event.fields["fee"],
        tick_spacing=event.fields["tick_spacing"],
        hook=event.fields["hooks"],
    )


def deduplicate_decoded_events(events: Iterable[DecodedV4Event]) -> tuple[DecodedV4Event, ...]:
    """Deduplicate overlapping source delivery without losing lineage."""

    result: dict[tuple[int, str | None, str | None, int | None], DecodedV4Event] = {}
    for event in events:
        existing = result.get(event.raw_event_key)
        if existing is None:
            result[event.raw_event_key] = event
            continue
        if (existing.event_type, existing.pool_id, existing.sender, dict(existing.fields)) != (
            event.event_type,
            event.pool_id,
            event.sender,
            dict(event.fields),
        ):
            raise DecodeError(f"conflicting duplicate event: {event.raw_event_key}")
        if existing.reason_flags != event.reason_flags:
            raise DecodeError(f"conflicting duplicate event flags: {event.raw_event_key}")
        result[event.raw_event_key] = DecodedV4Event(
            existing.event_type,
            existing.pool_id,
            existing.sender,
            existing.fields,
            existing.raw_event_key,
            tuple(dict.fromkeys(existing.raw_lineage + event.raw_lineage)),
            existing.reason_flags,
        )
    return tuple(result.values())


def classify_trade_origin(
    *,
    transaction_hash: str,
    wallet: str,
    token: str,
    swap_events: Sequence[DecodedV4Event],
    payment_legs: Sequence[PaymentLeg],
    receipt_legs: Sequence[PaymentLeg],
    as_of_time: str,
    retrieved_time: str,
    raw_event_refs: Sequence[str],
    activity_kind: str = "transfer",
    vendor_claims: Sequence[str] = (),
    estimated_usd_value: str | None = None,
    valuation_method: str | None = None,
) -> TradeEvidence:
    """Create one trade-evidence record for a transaction, not one per route leg."""

    if activity_kind not in {"transfer", "gift_or_airdrop"}:
        raise ValueError("activity_kind must be transfer or gift_or_airdrop")
    if estimated_usd_value is not None and valuation_method is None:
        raise ValueError("estimated USD requires valuation_method")
    refs = list(dict.fromkeys([*raw_event_refs, *(ref for event in swap_events for ref in event.raw_lineage)]))
    if not refs:
        raise ValueError("raw_event_refs cannot be empty")
    reason_flags = list(vendor_claims)
    if len(swap_events) > 1:
        reason_flags.append("multi_hop_route_collapsed_to_one_wallet_purchase")

    if swap_events and payment_legs and receipt_legs:
        classification = "genuine_swap"
    elif swap_events and receipt_legs and not payment_legs:
        classification = "ambiguous"
        reason_flags.extend(["no_readable_cash_leg", "vendor_or_swap_label_is_not_spend"])
    elif not swap_events and receipt_legs and not payment_legs:
        classification = activity_kind
        reason_flags.append("no_swap_payment_evidence")
    else:
        classification = "ambiguous"
        reason_flags.append("unsupported_or_unresolved_cash_flow")

    quote_asset = payment_legs[0].asset if payment_legs and all(leg.asset == payment_legs[0].asset for leg in payment_legs) else None
    estimated = estimated_usd_value is not None
    return TradeEvidence(
        transaction_hash=transaction_hash,
        wallet=wallet,
        token=token,
        classification=classification,
        payment_legs=tuple(payment_legs),
        receipt_legs=tuple(receipt_legs),
        quote_asset=quote_asset,
        valuation_method=valuation_method,
        estimated_usd=estimated,
        estimated_usd_value=estimated_usd_value,
        reason_flags=tuple(reason_flags),
        method_version="trade-evidence.v0.1",
        as_of_time=as_of_time,
        retrieved_time=retrieved_time,
        raw_event_refs=tuple(refs),
    )


def trade_evidence_from_receipt(
    *,
    transaction_hash: str,
    wallet: str,
    token: str,
    receipt: Mapping[str, Any],
    transaction: Mapping[str, Any] | None,
    swap_events: Sequence[DecodedV4Event],
    quote_assets: Sequence[str],
    as_of_time: str,
    retrieved_time: str,
    vendor_claims: Sequence[str] = (),
    estimated_usd_value: str | None = None,
    valuation_method: str | None = None,
) -> TradeEvidence:
    """Join a receipt's exact cash/receipt legs to supported swap evidence.

    The join is intentionally conservative. A missing transaction object or an
    indirect router payment does not get replaced with a midpoint, vendor label,
    or displayed estimate; the resulting activity stays ambiguous.
    """

    if not isinstance(receipt, Mapping):
        raise DecodeError("receipt is not an object")
    receipt_hash = receipt.get("transactionHash")
    if receipt_hash is not None and (
        not isinstance(receipt_hash, str) or receipt_hash.lower() != transaction_hash.lower()
    ):
        raise DecodeError("receipt transaction hash does not match requested hash")
    status = receipt.get("status")
    if status is not None and _hex_int_quantity(status, "receipt.status") == 0:
        raise DecodeError("receipt indicates a failed transaction")
    if any(
        event.raw_event_key[2] is not None
        and event.raw_event_key[2].lower() != transaction_hash.lower()
        for event in swap_events
    ):
        raise DecodeError("swap event transaction hash does not match receipt")
    logs = receipt.get("logs", [])
    if not isinstance(logs, list):
        raise DecodeError("receipt logs are not an array")
    if not all(isinstance(asset, str) for asset in quote_assets):
        raise DecodeError("quote assets must be strings")
    if transaction is not None and not isinstance(transaction, Mapping):
        raise DecodeError("transaction is not an object")
    payment_legs: list[PaymentLeg] = []
    receipt_legs: list[PaymentLeg] = []
    raw_refs = [f"rpc:receipt:{transaction_hash}"]
    normalized_quotes = {asset.lower() for asset in quote_assets}
    for index, log in enumerate(logs):
        if not isinstance(log, Mapping):
            raise DecodeError("receipt log is not an object")
        topics = log.get("topics")
        if not isinstance(topics, list) or not topics:
            continue
        if not isinstance(topics[0], str) or topics[0].lower() != TRANSFER_TOPIC:
            continue
        if len(topics) != 3:
            raise DecodeError("ERC-20 Transfer log has an unexpected topic count")
        asset = log.get("address")
        if not isinstance(asset, str):
            raise DecodeError("ERC-20 Transfer log has no token address")
        from_address = _topic_address(topics, 1, "transfer_from")
        to_address = _topic_address(topics, 2, "transfer_to")
        words = _data_words(log.get("data", ""))
        if len(words) != 1:
            raise DecodeError("ERC-20 Transfer log has an unexpected data shape")
        amount = str(_unsigned(words[0], 256, "transfer_amount"))
        ref = f"rpc:receipt:{transaction_hash}:log:{log.get('logIndex', index)}"
        raw_refs.append(ref)
        if to_address.lower() == wallet.lower() and asset.lower() == token.lower():
            receipt_legs.append(PaymentLeg(asset, amount, "in", from_address, to_address, ref))
        if from_address.lower() == wallet.lower() and asset.lower() in normalized_quotes:
            payment_legs.append(PaymentLeg(asset, amount, "out", from_address, to_address, ref))

    if transaction is not None:
        tx_from = transaction.get("from")
        tx_to = transaction.get("to")
        tx_value = transaction.get("value", "0x0")
        if tx_from is not None and not isinstance(tx_from, str):
            raise DecodeError("transaction.from is not an address string")
        if tx_to is not None and not isinstance(tx_to, str):
            raise DecodeError("transaction.to is not an address string")
        if tx_from is not None and tx_from.lower() == wallet.lower() and tx_to is not None:
            value = _hex_int_quantity(tx_value, "transaction.value")
            if value > 0:
                ref = f"rpc:transaction:{transaction_hash}:native_value"
                payment_legs.append(PaymentLeg("native:ETH", str(value), "out", tx_from, tx_to, ref))
                raw_refs.append(ref)

    return classify_trade_origin(
        transaction_hash=transaction_hash,
        wallet=wallet,
        token=token,
        swap_events=swap_events,
        payment_legs=payment_legs,
        receipt_legs=receipt_legs,
        as_of_time=as_of_time,
        retrieved_time=retrieved_time,
        raw_event_refs=raw_refs,
        vendor_claims=vendor_claims,
        estimated_usd_value=estimated_usd_value,
        valuation_method=valuation_method,
    )


def _raw_ref(event: RawEvent) -> str:
    return "raw:" + event.source + ":" + ":".join(str(part) for part in event.logical_key)


def _data_words(data: str) -> list[str]:
    if not data.startswith("0x"):
        raise DecodeError("event data must start with 0x")
    body = data[2:]
    if len(body) % 64 != 0 or any(character not in "0123456789abcdefABCDEF" for character in body):
        raise DecodeError("event data is not ABI-word aligned hex")
    return [body[index : index + 64] for index in range(0, len(body), 64)]


def _require_lengths(topics: list[str], words: list[str], *, topic_count: int, word_count: int) -> None:
    if len(topics) != topic_count or len(words) != word_count:
        raise DecodeError(f"expected {topic_count} topics and {word_count} data words")


def _topic_bytes32(topics: list[str], index: int, field_name: str) -> str:
    if len(topics) <= index:
        raise DecodeError(f"missing indexed {field_name}")
    return _word_bytes32(topics[index], field_name)


def _topic_address(topics: list[str], index: int, field_name: str) -> str:
    if len(topics) <= index:
        raise DecodeError(f"missing indexed {field_name}")
    return _word_address(topics[index], field_name)


def _word_bytes32(word: str, field_name: str) -> str:
    if word.startswith("0x"):
        word = word[2:]
    if len(word) != 64 or any(character not in "0123456789abcdefABCDEF" for character in word):
        raise DecodeError(f"{field_name} is not bytes32")
    return "0x" + word


def _word_address(word: str, field_name: str) -> str:
    raw = _word_bytes32(word, field_name)
    if raw[2:26] != "0" * 24:
        raise DecodeError(f"{field_name} is not canonical ABI address encoding")
    return "0x" + raw[26:]


def _unsigned(word: str, bits: int, field_name: str) -> int:
    value = int(_word_bytes32(word, field_name)[2:], 16)
    if value >= 1 << bits:
        raise DecodeError(f"{field_name} exceeds uint{bits}")
    return value


def _signed(word: str, bits: int, field_name: str) -> int:
    value = int(_word_bytes32(word, field_name)[2:], 16)
    if value >= 1 << 255:
        value -= 1 << 256
    if not -(1 << (bits - 1)) <= value < 1 << (bits - 1):
        raise DecodeError(f"{field_name} exceeds int{bits}")
    return value


def _hex_int_quantity(value: Any, field_name: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise DecodeError(f"{field_name} is not a hex quantity")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise DecodeError(f"{field_name} is not a hex quantity") from exc
