"""Minimal read-only Robinhood Chain JSON-RPC client.

This module deliberately has no transaction-signing or broadcast surface. A
transport can be injected for deterministic tests and offline fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


READ_METHODS = frozenset(
    {
        "eth_chainId",
        "eth_blockNumber",
        "eth_getBlockByNumber",
        "eth_getCode",
        "eth_getLogs",
        "eth_getTransactionReceipt",
        "eth_getTransactionByHash",
    }
)


class JsonRpcError(RuntimeError):
    """Raised when the endpoint returns a JSON-RPC error."""


class WrongChainError(JsonRpcError):
    """Raised when an endpoint does not identify as the configured chain."""


Transport = Callable[[str, list[Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class RpcLog:
    """The subset of an RPC log required by the raw-event boundary."""

    block_number: int
    block_hash: str
    transaction_hash: str
    log_index: int
    payload: Mapping[str, Any]
    block_timestamp: int | None


class ReadOnlyRpcClient:
    """Read-only JSON-RPC client with bounded retries and chain identity checks."""

    def __init__(
        self,
        endpoint: str,
        *,
        expected_chain_id: int = 4663,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        transport: Transport | None = None,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")) and transport is None:
            raise ValueError("endpoint must be HTTP(S)")
        if expected_chain_id <= 0:
            raise ValueError("expected_chain_id must be positive")
        if max_retries < 0 or backoff_seconds < 0:
            raise ValueError("retry settings cannot be negative")
        self.endpoint = endpoint
        self.expected_chain_id = expected_chain_id
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._transport = transport
        self._request_id = 0

    def request(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in READ_METHODS:
            raise PermissionError(f"read-only client rejected method: {method}")
        request_params = params or []
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._call_transport(method, request_params)
                if "error" in response:
                    error = response["error"]
                    raise JsonRpcError(f"{method}: {error}")
                if "result" not in response:
                    raise JsonRpcError(f"{method}: response has no result")
                return response["result"]
            except (HTTPError, URLError, TimeoutError, OSError, JsonRpcError) as exc:
                last_error = exc
                if isinstance(exc, JsonRpcError) and not self._retryable_rpc_error(exc):
                    raise
                if attempt == self.max_retries:
                    raise JsonRpcError(f"{method}: exhausted retries: {exc}") from exc
                if self.backoff_seconds:
                    time.sleep(self.backoff_seconds * (2**attempt))
        raise JsonRpcError(f"{method}: request failed: {last_error}")

    @staticmethod
    def _retryable_rpc_error(error: JsonRpcError) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in ("rate", "timeout", "tempor", "unavailable"))

    def _call_transport(self, method: str, params: list[Any]) -> Mapping[str, Any]:
        self._request_id += 1
        if self._transport is not None:
            return self._transport(method, params)
        body = json.dumps({"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}).encode()
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "willfly-observatory/0.1 (read-only)",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310 - endpoint is configured explicitly
            return json.loads(response.read().decode("utf-8"))

    def check_chain(self) -> int:
        actual = _hex_int(self.request("eth_chainId"), "chainId")
        if actual != self.expected_chain_id:
            raise WrongChainError(f"expected chain {self.expected_chain_id}, endpoint reported {actual}")
        return actual

    def block_number(self) -> int:
        return _hex_int(self.request("eth_blockNumber"), "blockNumber")

    def block(self, block_number: int) -> Mapping[str, Any]:
        return self.request("eth_getBlockByNumber", [hex(block_number), False])

    def code(self, address: str, block_tag: str = "latest") -> str:
        return self.request("eth_getCode", [address, block_tag])

    def transaction(self, transaction_hash: str) -> Mapping[str, Any] | None:
        return self.request("eth_getTransactionByHash", [transaction_hash])

    def resolve_log_time(self, log: RpcLog, headers: dict[str, Mapping[str, Any]]) -> RpcLog:
        """Resolve missing log time from a hash-matched header; never invent event time."""
        if log.block_timestamp is not None:
            return log
        from dataclasses import replace
        if log.block_hash not in headers:
            header = self.block(log.block_number)
            if not isinstance(header, Mapping) or header.get("hash", "").lower() != log.block_hash.lower():
                raise JsonRpcError("missing or fork-mismatched block header")
            headers[log.block_hash] = header
        timestamp = _optional_block_timestamp(headers[log.block_hash].get("timestamp"))
        if timestamp is None:
            raise JsonRpcError("block header timestamp unavailable")
        return replace(log, block_timestamp=timestamp)

    def logs(self, *, address: str | list[str], from_block: int, to_block: int, max_range: int = 2000) -> list[RpcLog]:
        if from_block < 0 or to_block < from_block or to_block - from_block > max_range:
            raise ValueError("log range is invalid or exceeds the configured bound")
        raw_logs = self.request("eth_getLogs", [{"address": address, "fromBlock": hex(from_block), "toBlock": hex(to_block)}])
        if not isinstance(raw_logs, list):
            raise JsonRpcError("eth_getLogs: result is not a list")
        return [
            RpcLog(
                block_number=_hex_int(log.get("blockNumber"), "blockNumber"),
                block_hash=log["blockHash"],
                transaction_hash=log["transactionHash"],
                log_index=_hex_int(log.get("logIndex"), "logIndex"),
                payload=dict(log),
                block_timestamp=_optional_block_timestamp(log.get("blockTimestamp")),
            )
            for log in raw_logs
        ]


def _hex_int(value: Any, field_name: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise JsonRpcError(f"{field_name} is not a hex quantity")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise JsonRpcError(f"{field_name} is not a hex quantity") from exc


def _optional_block_timestamp(value: Any) -> int | None:
    """Treat a provider's zero sentinel as unavailable block time."""

    if value is None:
        return None
    timestamp = _hex_int(value, "blockTimestamp")
    return timestamp or None
