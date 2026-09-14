from typing import Any

import pytest

from willfly.adapters.robinhood_rpc import ReadOnlyRpcClient, WrongChainError
from willfly.ingest.capture import capture_once


V4 = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
TX = "0x4444444444444444444444444444444444444444444444444444444444444444"
BLOCK = "0x2222222222222222222222222222222222222222222222222222222222222222"


def test_capture_checks_chain_and_preserves_event_and_arrival_times():
    calls: list[str] = []

    def transport(method: str, params: list[Any]):
        calls.append(method)
        if method == "eth_chainId":
            return {"result": "0x1237"}
        if method == "eth_blockNumber":
            return {"result": "0x65"}
        if method == "eth_getLogs":
            return {
                "result": [
                    {
                        "address": V4,
                        "blockNumber": "0x64",
                        "blockHash": BLOCK,
                        "transactionHash": TX,
                        "transactionIndex": "0x0",
                        "logIndex": "0x2",
                        "topics": ["0x" + "11" * 32],
                        "data": "0x",
                        "blockTimestamp": "0x68c4f120"
                    }
                ]
            }
        raise AssertionError(method)

    result = capture_once(
        ReadOnlyRpcClient("https://fixture.invalid", transport=transport, backoff_seconds=0),
        addresses=[V4],
        from_block=100,
        run_id="capture-test",
        clock=lambda: "2026-09-13T00:00:01+00:00",
    )
    assert result.chain_id == 4663
    assert result.to_block == 101
    assert len(result.events) == 1
    assert result.events[0].event_time != result.events[0].received_time
    assert result.events[0].canonical_status == "provisional"
    assert "eth_sendRawTransaction" not in calls


def test_wrong_chain_is_rejected_before_log_reads():
    calls: list[str] = []

    def transport(method: str, params: list[Any]):
        calls.append(method)
        return {"result": "0x1"}

    client = ReadOnlyRpcClient("https://fixture.invalid", transport=transport, backoff_seconds=0)
    with pytest.raises(WrongChainError):
        capture_once(client, addresses=[V4], from_block=1, run_id="wrong-chain")
    assert calls == ["eth_chainId"]


def test_read_only_surface_rejects_broadcast_methods():
    client = ReadOnlyRpcClient("https://fixture.invalid", transport=lambda method, params: {"result": "0x1"})
    with pytest.raises(PermissionError):
        client.request("eth_sendRawTransaction", ["0xdead"])


def test_retry_backoff_recovers_transient_transport_error():
    attempts = 0

    def transport(method: str, params: list[Any]):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("fixture timeout")
        return {"result": "0x1237"}

    client = ReadOnlyRpcClient("https://fixture.invalid", transport=transport, max_retries=1, backoff_seconds=0)
    assert client.check_chain() == 4663
    assert attempts == 2


def test_zero_block_timestamp_is_treated_as_unavailable():
    def transport(method: str, params: list[Any]):
        if method == "eth_getLogs":
            return {
                "result": [
                    {
                        "address": V4,
                        "blockNumber": "0x64",
                        "blockHash": BLOCK,
                        "transactionHash": TX,
                        "logIndex": "0x0",
                        "topics": [],
                        "data": "0x",
                        "blockTimestamp": "0x0",
                    }
                ]
            }
        raise AssertionError(method)

    log = ReadOnlyRpcClient("https://fixture.invalid", transport=transport, backoff_seconds=0).logs(
        address=V4, from_block=100, to_block=100
    )[0]
    assert log.block_timestamp is None


def test_block_header_cache_is_page_scoped_and_clearable():
    calls: list[str] = []

    def transport(method: str, params: list[Any]):
        calls.append(method)
        if method == "eth_getBlockByNumber":
            return {"result": {"number": params[0], "hash": BLOCK, "parentHash": BLOCK, "timestamp": "0x1"}}
        raise AssertionError(method)

    client = ReadOnlyRpcClient("https://fixture.invalid", transport=transport, backoff_seconds=0)
    client.block(100)
    client.block(100)
    assert calls == ["eth_getBlockByNumber"]
    client.clear_block_cache()
    client.block(100)
    assert calls == ["eth_getBlockByNumber", "eth_getBlockByNumber"]


def test_prefetch_blocks_fetches_each_unique_header_once():
    calls: list[int] = []

    def transport(method: str, params: list[Any]):
        if method != "eth_getBlockByNumber":
            raise AssertionError(method)
        calls.append(int(params[0], 16))
        number = params[0]
        return {"result": {"number": number, "hash": BLOCK, "parentHash": BLOCK, "timestamp": "0x1"}}

    client = ReadOnlyRpcClient("https://fixture.invalid", transport=transport, backoff_seconds=0)
    headers = client.prefetch_blocks([100, 100, 101], max_workers=2)
    assert set(headers) == {100, 101}
    assert sorted(calls) == [100, 101]
