from dataclasses import replace
import pytest

from willfly.adapters.launchpad import (
    LAUNCH_SWEPT_TOPIC,
    POOL_GRADUATED_TOPIC,
    PONS_V2_FACTORY,
    TOKEN_LAUNCHED_TOPIC,
    TOKENS_LOCKED_TOPIC,
    LaunchDecodeError,
    UnsupportedLaunchEvent,
    decode_pons_v2_event,
    deduplicate_launch_events,
    launch_from_events,
)
from willfly.domain import RawEvent


TOKEN = "0x1111111111111111111111111111111111111111"
CURVE = "0x2222222222222222222222222222222222222222"
DEPLOYER = "0x3333333333333333333333333333333333333333"
QUOTE = "0x4444444444444444444444444444444444444444"


def _word(value: int) -> str:
    return f"{value:064x}"


def _address_word(address: str) -> str:
    return address[2:].rjust(64, "0")


def _event(
    topic: str,
    topics: list[str],
    words: list[str],
    *,
    block: int = 100,
    index: int = 0,
    received: str = "2026-09-13T00:00:02Z",
    source: str = "fixture.pons",
    transaction_hash: str = "0x" + "55" * 32,
) -> RawEvent:
    return RawEvent.from_dict(
        {
            "chain_id": 4663,
            "source": source,
            "source_schema_version": "rpc-log.v0.1",
            "block_number": block,
            "block_hash": "0x" + f"{block:064x}"[-64:],
            "parent_hash": "0x" + "aa" * 32,
            "transaction_hash": transaction_hash,
            "log_index": index,
            "event_time": "2026-09-13T00:00:01Z",
            "received_time": received,
            "payload": {
                "address": PONS_V2_FACTORY,
                "topics": [topic, *topics],
                "data": "0x" + "".join(words),
            },
            "ingestion_run": "launchpad-test",
            "canonical_status": "canonical",
        }
    )


def _token_launched(
    *, index: int = 0, received: str = "2026-09-13T00:00:02Z", source: str = "fixture.pons"
) -> RawEvent:
    return _event(
        TOKEN_LAUNCHED_TOPIC,
        [_address_word(TOKEN), _address_word(CURVE), _address_word(DEPLOYER)],
        [_address_word(QUOTE), _word(2), _word(4200)],
        index=index,
        received=received,
        source=source,
    )


def test_decode_pons_v2_lifecycle_events_preserves_exact_fields():
    created = decode_pons_v2_event(_token_launched())
    assert created.event_type == "TokenLaunched"
    assert created.token == TOKEN
    assert created.fields == {
        "curve": CURVE,
        "deployer": DEPLOYER,
        "pair_token": QUOTE,
        "launch_config_id": "2",
        "graduation_threshold_atomic": "4200",
    }

    swept = decode_pons_v2_event(
        _event(LAUNCH_SWEPT_TOPIC, [_address_word(TOKEN)], [_word(4100), _word(100)], index=1)
    )
    locked = decode_pons_v2_event(
        _event(TOKENS_LOCKED_TOPIC, [_address_word(TOKEN)], [_word(49)], index=2)
    )
    graduated = decode_pons_v2_event(
        _event(POOL_GRADUATED_TOPIC, [_address_word(TOKEN)], [_word(7), _word(800), _word(3900)], index=3)
    )
    assert swept.fields == {"quote_out_atomic": "4100", "token_out_atomic": "100"}
    assert locked.fields == {"amount_atomic": "49"}
    assert graduated.fields == {
        "position_id": "7",
        "token_amount_atomic": "800",
        "pair_token_amount_atomic": "3900",
    }


def test_launch_projection_marks_graduation_without_inventing_a_pool_id():
    events = [
        decode_pons_v2_event(_token_launched()),
        decode_pons_v2_event(_event(LAUNCH_SWEPT_TOPIC, [_address_word(TOKEN)], [_word(4100), _word(100)], index=1)),
        decode_pons_v2_event(_event(TOKENS_LOCKED_TOPIC, [_address_word(TOKEN)], [_word(49)], index=2)),
        decode_pons_v2_event(
            _event(POOL_GRADUATED_TOPIC, [_address_word(TOKEN)], [_word(7), _word(800), _word(3900)], index=3)
        ),
    ]
    launch = launch_from_events(events)
    assert launch.token == TOKEN
    assert launch.creator == DEPLOYER
    assert launch.lifecycle_state == "graduated"
    assert launch.created_at == "2026-09-13T00:00:01Z"
    assert launch.first_seen_at == "2026-09-13T00:00:02Z"
    assert launch.linked_pool_ids == ()
    assert len(launch.creation_evidence) == 4


def test_curve_sweep_without_pool_stays_unknown_not_non_graduate():
    events = [
        decode_pons_v2_event(_token_launched()),
        decode_pons_v2_event(_event(LAUNCH_SWEPT_TOPIC, [_address_word(TOKEN)], [_word(4100), _word(100)], index=1)),
    ]
    assert launch_from_events(events).lifecycle_state == "unknown"


def test_overlapping_launch_delivery_deduplicates_and_keeps_lineage():
    first = decode_pons_v2_event(_token_launched(source="rpc", received="2026-09-13T00:00:03Z"))
    second = decode_pons_v2_event(_token_launched(source="provider-replay", received="2026-09-13T00:00:04Z"))
    deduped = deduplicate_launch_events([first, second])
    assert len(deduped) == 1
    assert deduped[0].received_time == "2026-09-13T00:00:03Z"
    assert set(deduped[0].raw_lineage) == {first.raw_lineage[0], second.raw_lineage[0]}


def test_malformed_unsupported_and_mixed_launch_events_are_rejected():
    malformed = replace(_token_launched(), payload={"topics": [TOKEN_LAUNCHED_TOPIC, _address_word(TOKEN)], "data": "0x"})
    with pytest.raises(LaunchDecodeError):
        decode_pons_v2_event(malformed)
    unsupported = replace(_token_launched(), payload={"address": PONS_V2_FACTORY, "topics": ["0x" + "ff" * 32], "data": "0x"})
    with pytest.raises(UnsupportedLaunchEvent):
        decode_pons_v2_event(unsupported)
    other_token = replace(_token_launched(), payload={
        "address": PONS_V2_FACTORY,
        "topics": [TOKEN_LAUNCHED_TOPIC, _address_word("0x6666666666666666666666666666666666666666"), _address_word(CURVE), _address_word(DEPLOYER)],
        "data": "0x" + _address_word(QUOTE) + _word(2) + _word(4200),
    })
    with pytest.raises(LaunchDecodeError):
        launch_from_events([decode_pons_v2_event(_token_launched()), decode_pons_v2_event(other_token)])
