"""Evidence-preserving Pons V2 launch lifecycle decoding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from willfly.domain import Launch, RawEvent


PONS_V2_FACTORY = "0x7ed598bcef8bd9edd8c97a195c6d13f40801ec7e"
TOKEN_LAUNCHED_TOPIC = "0x8d4aad4953d0ca700d468f3753aa14432d1b35b43ec6409f051fb6aa43a89607"
LAUNCH_SWEPT_TOPIC = "0xcdb72f157fd3666758a6ce201387ffb52038c7562e4fff352828da1096c4b6b4"
TOKENS_LOCKED_TOPIC = "0xa0a18f5bf205becee8b268d7cf69addab8548ae8ef361791464cf0e0e17c1361"
POOL_GRADUATED_TOPIC = "0x0a44ef75df69c534f43cd6c1aa3ef8983065fe5fe79ef9e79f6494e6f258c259"

EVENT_TOPICS = {
    TOKEN_LAUNCHED_TOPIC: "TokenLaunched",
    LAUNCH_SWEPT_TOPIC: "LaunchSwept",
    TOKENS_LOCKED_TOPIC: "GraduationTokensPermanentlyLocked",
    POOL_GRADUATED_TOPIC: "PoolGraduated",
}


class LaunchDecodeError(ValueError):
    """Raised when a Pons V2 lifecycle event cannot be decoded safely."""


class UnsupportedLaunchEvent(LaunchDecodeError):
    """Raised when a factory log is outside the supported lifecycle subset."""


@dataclass(frozen=True)
class DecodedLaunchEvent:
    event_type: str
    token: str
    fields: Mapping[str, Any]
    event_time: str
    received_time: str
    raw_event_key: tuple[int, str | None, str | None, int | None]
    raw_lineage: tuple[str, ...]


def decode_pons_v2_event(event: RawEvent, *, factory: str = PONS_V2_FACTORY) -> DecodedLaunchEvent:
    """Decode one supported factory event and retain its raw lineage."""

    payload = event.payload
    emitter = payload.get("address")
    if emitter is not None and (not isinstance(emitter, str) or emitter.lower() != factory.lower()):
        raise LaunchDecodeError("event emitter does not match the configured Pons V2 factory")
    topics = payload.get("topics")
    data = payload.get("data")
    if not isinstance(topics, list) or not topics or not all(isinstance(topic, str) for topic in topics):
        raise LaunchDecodeError("Pons V2 event topics are missing or malformed")
    if not isinstance(data, str):
        raise LaunchDecodeError("Pons V2 event data is missing or malformed")
    event_type = EVENT_TOPICS.get(topics[0].lower())
    if event_type is None:
        raise UnsupportedLaunchEvent(f"unsupported Pons V2 topic: {topics[0].lower()}")
    token = _topic_address(topics, 1, "token")
    words = _data_words(data)
    fields: dict[str, Any]

    if event_type == "TokenLaunched":
        _require_lengths(topics, words, topic_count=4, word_count=3)
        fields = {
            "curve": _topic_address(topics, 2, "curve"),
            "deployer": _topic_address(topics, 3, "deployer"),
            "pair_token": _word_address(words[0], "pair_token"),
            "launch_config_id": str(_unsigned(words[1], "launch_config_id")),
            "graduation_threshold_atomic": str(_unsigned(words[2], "graduation_threshold")),
        }
    elif event_type == "LaunchSwept":
        _require_lengths(topics, words, topic_count=2, word_count=2)
        fields = {
            "quote_out_atomic": str(_unsigned(words[0], "quote_out")),
            "token_out_atomic": str(_unsigned(words[1], "token_out")),
        }
    elif event_type == "GraduationTokensPermanentlyLocked":
        _require_lengths(topics, words, topic_count=2, word_count=1)
        fields = {"amount_atomic": str(_unsigned(words[0], "amount"))}
    else:
        _require_lengths(topics, words, topic_count=2, word_count=3)
        fields = {
            "position_id": str(_unsigned(words[0], "position_id")),
            "token_amount_atomic": str(_unsigned(words[1], "token_amount")),
            "pair_token_amount_atomic": str(_unsigned(words[2], "pair_token_amount")),
        }

    return DecodedLaunchEvent(
        event_type=event_type,
        token=token,
        fields=fields,
        event_time=event.event_time,
        received_time=event.received_time,
        raw_event_key=event.logical_key,
        raw_lineage=(_raw_ref(event),),
    )


def deduplicate_launch_events(events: Iterable[DecodedLaunchEvent]) -> tuple[DecodedLaunchEvent, ...]:
    """Merge overlapping factory delivery while retaining every source ref."""

    result: dict[tuple[int, str | None, str | None, int | None], DecodedLaunchEvent] = {}
    for event in events:
        existing = result.get(event.raw_event_key)
        if existing is None:
            result[event.raw_event_key] = event
            continue
        if (existing.event_type, existing.token, dict(existing.fields)) != (
            event.event_type,
            event.token,
            dict(event.fields),
        ):
            raise LaunchDecodeError(f"conflicting duplicate launch event: {event.raw_event_key}")
        result[event.raw_event_key] = DecodedLaunchEvent(
            event_type=existing.event_type,
            token=existing.token,
            fields=existing.fields,
            event_time=_earliest_timestamp(existing.event_time, event.event_time),
            received_time=_earliest_timestamp(existing.received_time, event.received_time),
            raw_event_key=existing.raw_event_key,
            raw_lineage=tuple(dict.fromkeys(existing.raw_lineage + event.raw_lineage)),
        )
    return tuple(result.values())


def launch_from_events(
    events: Sequence[DecodedLaunchEvent],
    *,
    chain_id: int = 4663,
    launch_contract: str = PONS_V2_FACTORY,
    launch_contract_version: str = "pons-v2",
) -> Launch:
    """Build a launch projection without inferring a pool or a non-graduate."""

    if not events:
        raise LaunchDecodeError("launch lifecycle requires at least one event")
    events = deduplicate_launch_events(events)
    tokens = {event.token.lower() for event in events}
    if len(tokens) != 1:
        raise LaunchDecodeError("a launch lifecycle cannot combine multiple token identities")
    creation_events = [event for event in events if event.event_type == "TokenLaunched"]
    if len(creation_events) != 1:
        raise LaunchDecodeError("launch lifecycle requires exactly one TokenLaunched event")
    creation = creation_events[0]
    has_pool = any(event.event_type == "PoolGraduated" for event in events)
    has_sweep_without_pool = any(event.event_type == "LaunchSwept" for event in events) and not has_pool
    lifecycle_state = "graduated" if has_pool else "unknown" if has_sweep_without_pool else "active"
    raw_refs = tuple(dict.fromkeys(ref for event in events for ref in event.raw_lineage))
    return Launch(
        chain_id=chain_id,
        token=creation.token,
        launch_contract=launch_contract,
        launch_contract_version=launch_contract_version,
        creation_evidence=raw_refs,
        creator=creation.fields["deployer"],
        created_at=creation.event_time,
        first_seen_at=min(events, key=lambda event: _parse_timestamp(event.received_time)).received_time,
        origin_confidence="observed",
        linked_pool_ids=(),
        lifecycle_state=lifecycle_state,
    )


def _raw_ref(event: RawEvent) -> str:
    return "raw:" + event.source + ":" + ":".join(str(part) for part in event.logical_key)


def _data_words(data: str) -> list[str]:
    if not data.startswith("0x"):
        raise LaunchDecodeError("event data must start with 0x")
    body = data[2:]
    if len(body) % 64 != 0 or any(character not in "0123456789abcdefABCDEF" for character in body):
        raise LaunchDecodeError("event data is not ABI-word aligned hex")
    return [body[index : index + 64] for index in range(0, len(body), 64)]


def _require_lengths(topics: list[str], words: list[str], *, topic_count: int, word_count: int) -> None:
    if len(topics) != topic_count or len(words) != word_count:
        raise LaunchDecodeError(f"expected {topic_count} topics and {word_count} data words")


def _topic_address(topics: list[str], index: int, field_name: str) -> str:
    if len(topics) <= index:
        raise LaunchDecodeError(f"missing indexed {field_name}")
    return _word_address(topics[index], field_name)


def _word_address(word: str, field_name: str) -> str:
    raw = _word_bytes32(word, field_name)
    if raw[2:26] != "0" * 24:
        raise LaunchDecodeError(f"{field_name} is not canonical ABI address encoding")
    return "0x" + raw[26:]


def _word_bytes32(word: str, field_name: str) -> str:
    if word.startswith("0x"):
        word = word[2:]
    if len(word) != 64 or any(character not in "0123456789abcdefABCDEF" for character in word):
        raise LaunchDecodeError(f"{field_name} is not bytes32")
    return "0x" + word


def _unsigned(word: str, field_name: str) -> int:
    return int(_word_bytes32(word, field_name)[2:], 16)


def _earliest_timestamp(first: str, second: str) -> str:
    return first if _parse_timestamp(first) <= _parse_timestamp(second) else second


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
