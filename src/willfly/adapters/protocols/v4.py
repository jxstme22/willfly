"""Uniswap V4 event decoding and evidence-preserving trade classification."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    emitter: str
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
    emitter = _address(payload.get("address"), "V4 event emitter")
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
        return DecodedV4Event(event_type, pool_id, None, emitter, fields, event.logical_key, lineage, reason_flags)

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
        return DecodedV4Event(event_type, pool_id, sender, emitter, fields, event.logical_key, lineage)

    _require_lengths(topics, words, topic_count=3, word_count=4)
    fields = {
        "tick_lower": _signed(words[0], 24, "tick_lower"),
        "tick_upper": _signed(words[1], 24, "tick_upper"),
        "liquidity_delta": _signed(words[2], 256, "liquidity_delta"),
        "salt": _word_bytes32(words[3], "salt"),
    }
    return DecodedV4Event(event_type, pool_id, sender, emitter, fields, event.logical_key, lineage)


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
        if (existing.event_type, existing.pool_id, existing.sender, existing.emitter, dict(existing.fields)) != (
            event.event_type,
            event.pool_id,
            event.sender,
            event.emitter,
            dict(event.fields),
        ):
            raise DecodeError(f"conflicting duplicate event: {event.raw_event_key}")
        if existing.reason_flags != event.reason_flags:
            raise DecodeError(f"conflicting duplicate event flags: {event.raw_event_key}")
        result[event.raw_event_key] = DecodedV4Event(
            existing.event_type,
            existing.pool_id,
            existing.sender,
            existing.emitter,
            existing.fields,
            existing.raw_event_key,
            tuple(dict.fromkeys(existing.raw_lineage + event.raw_lineage)),
            existing.reason_flags,
        )
    return tuple(result.values())


def deduplicate_trade_evidence(records: Iterable[TradeEvidence]) -> tuple[TradeEvidence, ...]:
    """Deduplicate repeated source observations without multiplying cash flow.

    Economic identity is a transaction, wallet, token and established direction.
    A conflicting duplicate fails closed; an equivalent duplicate contributes its
    raw source references and flags to the one retained record.
    """

    result: dict[tuple[str, str, str, str], TradeEvidence] = {}
    for record in records:
        key = (
            record.transaction_hash.lower(),
            record.wallet.lower(),
            record.token.lower(),
            record.trade_direction,
        )
        existing = result.get(key)
        if existing is None:
            result[key] = record
            continue
        if _trade_shape(existing) != _trade_shape(record):
            raise DecodeError(f"conflicting duplicate trade evidence: {record.transaction_hash}")
        result[key] = replace(
            existing,
            raw_event_refs=tuple(dict.fromkeys((*existing.raw_event_refs, *record.raw_event_refs))),
            reason_flags=tuple(dict.fromkeys((*existing.reason_flags, *record.reason_flags))),
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
    route_status: str = "uncertain",
    trade_direction: str = "unknown",
    refund_legs: Sequence[PaymentLeg] = (),
) -> TradeEvidence:
    """Create one route-aware trade record for a transaction, not route legs.

    ``genuine_swap`` is deliberately a high bar: matching transaction hashes
    and transfers are insufficient until the caller has supplied verified route
    evidence, wallet direction and non-refunded net cash flow.
    """

    if activity_kind not in {"transfer", "gift_or_airdrop"}:
        raise ValueError("activity_kind must be transfer or gift_or_airdrop")
    if estimated_usd_value is not None and valuation_method is None:
        raise ValueError("estimated USD requires valuation_method")
    if route_status not in {"verified", "uncertain", "unsupported"}:
        raise ValueError("unsupported route_status")
    if trade_direction not in {"buy", "sell", "unknown"}:
        raise ValueError("unsupported trade_direction")
    if any(leg.direction != "out" for leg in payment_legs):
        raise ValueError("payment legs must flow out of the wallet")
    if any(leg.direction != "in" for leg in receipt_legs):
        raise ValueError("receipt legs must flow into the wallet")
    if any(leg.direction != "in" for leg in refund_legs):
        raise ValueError("refund legs must flow into the wallet")
    refs = list(dict.fromkeys([*raw_event_refs, *(ref for event in swap_events for ref in event.raw_lineage)]))
    if not refs:
        raise ValueError("raw_event_refs cannot be empty")
    reason_flags = list(vendor_claims)
    if len(swap_events) > 1:
        reason_flags.append("multi_hop_route_collapsed_to_one_wallet_purchase")

    net_payment = _net_outflow(payment_legs, refund_legs)
    if swap_events and payment_legs and receipt_legs and route_status == "verified" and trade_direction != "unknown" and net_payment:
        classification = "genuine_swap"
    elif swap_events and payment_legs and receipt_legs:
        classification = "ambiguous"
        if route_status != "verified":
            reason_flags.append("route_evidence_unverified")
        if trade_direction == "unknown":
            reason_flags.append("wallet_direction_unresolved")
        if not net_payment:
            reason_flags.append("fully_refunded_or_zero_net_input")
    elif swap_events and receipt_legs and not payment_legs:
        classification = "ambiguous"
        reason_flags.extend(["no_readable_cash_leg", "vendor_or_swap_label_is_not_spend"])
    elif swap_events and not payment_legs:
        classification = "ambiguous"
        reason_flags.extend(["no_readable_cash_leg", "vendor_or_swap_label_is_not_spend"])
    elif not swap_events and receipt_legs and not payment_legs:
        classification = activity_kind
        reason_flags.append("no_swap_payment_evidence")
    else:
        classification = "ambiguous"
        reason_flags.append("unsupported_or_unresolved_cash_flow")

    if refund_legs:
        reason_flags.append("refund_observed")
    quote_legs = payment_legs if trade_direction != "sell" else receipt_legs
    quote_asset = quote_legs[0].asset if quote_legs and all(leg.asset == quote_legs[0].asset for leg in quote_legs) else None
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
        method_version="trade-evidence.v0.2",
        as_of_time=as_of_time,
        retrieved_time=retrieved_time,
        raw_event_refs=tuple(refs),
        route_status=route_status,
        trade_direction=trade_direction,
        refund_legs=tuple(refund_legs),
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
    pool_identities: Sequence[PoolIdentity] = (),
    route_actors: Sequence[str] = (),
    native_refund_legs: Sequence[PaymentLeg] = (),
    native_refunds_accounted: bool = False,
) -> TradeEvidence:
    """Join a receipt's exact cash/receipt legs to supported swap evidence.

    The join is intentionally conservative. A missing route context, issuer
    mismatch, unlinked receipt log, indirect payment or unknown native refund
    does not get replaced with a midpoint, vendor label, or displayed estimate;
    the resulting activity stays ambiguous.
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
    route_status, route_flags, pool_by_id = _verify_swap_route(
        swap_events=swap_events,
        receipt_logs=logs,
        token=token,
        pool_identities=pool_identities,
        quote_assets=quote_assets,
    )
    actors = {actor.lower() for actor in route_actors}
    actors.update(identity.manager_or_factory.lower() for identity in pool_by_id.values())
    quote_set = _route_quote_assets(pool_by_id.values(), token=token, quote_assets=quote_assets)
    payment_legs: list[PaymentLeg] = []
    receipt_legs: list[PaymentLeg] = []
    refund_legs: list[PaymentLeg] = list(native_refund_legs)
    token_in: list[PaymentLeg] = []
    token_out: list[PaymentLeg] = []
    quote_in: list[PaymentLeg] = []
    quote_out: list[PaymentLeg] = []
    raw_refs = [f"rpc:receipt:{transaction_hash}"]
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
        leg = PaymentLeg(asset, amount, "in", from_address, to_address, ref)
        asset_key = asset.lower()
        sender_is_route = from_address.lower() in actors
        recipient_is_route = to_address.lower() in actors
        if to_address.lower() == wallet.lower() and asset_key == token.lower():
            if sender_is_route:
                token_in.append(leg)
            else:
                route_flags.append("unrelated_token_transfer_excluded")
        elif from_address.lower() == wallet.lower() and asset_key == token.lower():
            if recipient_is_route:
                token_out.append(PaymentLeg(asset, amount, "out", from_address, to_address, ref))
            else:
                route_flags.append("unrelated_token_transfer_excluded")
        elif to_address.lower() == wallet.lower() and asset_key in quote_set:
            if sender_is_route:
                quote_in.append(leg)
            else:
                route_flags.append("unrelated_quote_transfer_excluded")
        elif from_address.lower() == wallet.lower() and asset_key in quote_set:
            if recipient_is_route:
                quote_out.append(PaymentLeg(asset, amount, "out", from_address, to_address, ref))
            else:
                route_flags.append("unrelated_quote_transfer_excluded")
        elif asset_key == token.lower() and sender_is_route:
            route_flags.append("token_fee_or_route_split_observed")

    if transaction is not None:
        tx_from = transaction.get("from")
        tx_to = transaction.get("to")
        tx_value = transaction.get("value", "0x0")
        if tx_from is not None and not isinstance(tx_from, str):
            raise DecodeError("transaction.from is not an address string")
        if tx_to is not None and not isinstance(tx_to, str):
            raise DecodeError("transaction.to is not an address string")
        if tx_from is not None and tx_from.lower() == wallet.lower() and tx_to is not None and tx_to.lower() in actors:
            value = _hex_int_quantity(tx_value, "transaction.value")
            if value > 0:
                ref = f"rpc:transaction:{transaction_hash}:native_value"
                if "native:eth" in quote_set:
                    quote_out.append(PaymentLeg("native:ETH", str(value), "out", tx_from, tx_to, ref))
                    if not native_refunds_accounted:
                        route_status = "uncertain"
                        route_flags.append("native_refund_coverage_unavailable")
                else:
                    route_flags.append("native_input_outside_verified_pool_currency")
                raw_refs.append(ref)

    _validate_native_refunds(native_refund_legs, wallet=wallet, actors=actors)
    if token_in and quote_out and not token_out:
        trade_direction = "buy"
        payment_legs = quote_out
        receipt_legs = token_in
        refund_legs.extend(quote_in)
    elif token_out and quote_in and not token_in:
        trade_direction = "sell"
        payment_legs = token_out
        receipt_legs = quote_in
        refund_legs.extend(token_in)
    else:
        trade_direction = "unknown"
        payment_legs = [*quote_out, *token_out]
        receipt_legs = [*token_in, *quote_in]
        if token_in and token_out:
            route_flags.append("mixed_wallet_token_direction")

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
        vendor_claims=(*vendor_claims, *route_flags),
        estimated_usd_value=estimated_usd_value,
        valuation_method=valuation_method,
        route_status=route_status,
        trade_direction=trade_direction,
        refund_legs=refund_legs,
    )


def _verify_swap_route(
    *,
    swap_events: Sequence[DecodedV4Event],
    receipt_logs: Sequence[object],
    token: str,
    pool_identities: Sequence[PoolIdentity],
    quote_assets: Sequence[str],
) -> tuple[str, list[str], dict[str, PoolIdentity]]:
    """Verify issuer, pool currency and receipt inclusion for V4 swap logs."""

    flags: list[str] = []
    pools = {identity.pool_id.lower(): identity for identity in pool_identities if identity.pool_id is not None}
    if not swap_events:
        return "uncertain", ["no_supported_swap_route"], pools
    if not pools:
        return "uncertain", ["pool_identity_unavailable"], pools
    if any(identity.protocol != "uniswap_v4" for identity in pools.values()):
        return "unsupported", ["unsupported_pool_protocol"], pools
    log_indices = {
        _log_index(log)
        for log in receipt_logs
        if isinstance(log, Mapping)
        and isinstance(log.get("address"), str)
        and isinstance(log.get("topics"), list)
        and log["topics"]
        and isinstance(log["topics"][0], str)
        and log["topics"][0].lower() == SWAP_TOPIC
    }
    for event in swap_events:
        identity = pools.get(event.pool_id.lower())
        if identity is None:
            return "uncertain", [*flags, "swap_pool_identity_unavailable"], pools
        if event.event_type != "Swap" or event.emitter.lower() != identity.manager_or_factory.lower():
            return "unsupported", [*flags, "swap_issuer_or_event_mismatch"], pools
        if "unsupported_hook_behavior" in event.reason_flags:
            return "unsupported", [*flags, "unsupported_hook_route"], pools
        if event.raw_event_key[3] not in log_indices:
            return "uncertain", [*flags, "swap_log_not_linked_to_receipt"], pools
        currencies = {_currency_asset(identity.currency0), _currency_asset(identity.currency1)}
        if token.lower() not in currencies:
            return "unsupported", [*flags, "token_not_in_verified_pool_currency"], pools
        expected_quotes = currencies - {token.lower()}
        supplied_quotes = {_normalize_asset(asset) for asset in quote_assets}
        if not expected_quotes.intersection(supplied_quotes):
            return "uncertain", [*flags, "quote_asset_not_in_verified_pool_currency"], pools
    return "verified", flags, pools


def _route_quote_assets(
    identities: Iterable[PoolIdentity], *, token: str, quote_assets: Sequence[str]
) -> set[str]:
    supplied = {_normalize_asset(asset) for asset in quote_assets}
    result: set[str] = set()
    for identity in identities:
        for currency in (identity.currency0, identity.currency1):
            asset = _currency_asset(currency)
            if asset != token.lower() and asset in supplied:
                result.add(asset)
    return result


def _validate_native_refunds(refunds: Sequence[PaymentLeg], *, wallet: str, actors: set[str]) -> None:
    for refund in refunds:
        if refund.asset.lower() != "native:eth" or refund.direction != "in":
            raise DecodeError("native refunds must be inbound native ETH legs")
        if refund.to_address.lower() != wallet.lower() or refund.from_address.lower() not in actors:
            raise DecodeError("native refund is not linked to the verified route")


def _net_outflow(payments: Sequence[PaymentLeg], refunds: Sequence[PaymentLeg]) -> bool:
    net: dict[str, int] = {}
    for payment in payments:
        net[payment.asset.lower()] = net.get(payment.asset.lower(), 0) + int(payment.amount_atomic)
    for refund in refunds:
        net[refund.asset.lower()] = net.get(refund.asset.lower(), 0) - int(refund.amount_atomic)
    return any(amount > 0 for amount in net.values())


def _trade_shape(record: TradeEvidence) -> tuple[object, ...]:
    def leg_shape(leg: PaymentLeg) -> tuple[str, str, str, str, str]:
        return (leg.asset.lower(), leg.amount_atomic, leg.direction, leg.from_address.lower(), leg.to_address.lower())

    return (
        record.classification,
        record.route_status,
        record.trade_direction,
        tuple(leg_shape(leg) for leg in record.payment_legs),
        tuple(leg_shape(leg) for leg in record.receipt_legs),
        tuple(leg_shape(leg) for leg in record.refund_legs),
        record.quote_asset.lower() if record.quote_asset else None,
        record.estimated_usd,
        record.estimated_usd_value,
        record.valuation_method,
    )


def _log_index(log: Mapping[str, Any]) -> int | None:
    value = log.get("logIndex")
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _currency_asset(value: str) -> str:
    return "native:eth" if value.lower() == "0x" + "0" * 40 else value.lower()


def _normalize_asset(value: str) -> str:
    return "native:eth" if value.lower() == "native:eth" else value.lower()


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


def _address(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        raise DecodeError(f"{field_name} is not an address")
    if any(character not in "0123456789abcdefABCDEF" for character in value[2:]):
        raise DecodeError(f"{field_name} is not an address")
    return value


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
