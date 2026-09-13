"""Bounded retry supervision for recorder operations."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable, TypeVar
from urllib.parse import urlsplit


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts <= 0 or self.backoff_seconds < 0:
            raise ValueError("retry policy is invalid")


@dataclass(frozen=True)
class SupervisionResult:
    state: str
    attempts: int
    value: object | None
    error: str | None


def run_with_retries(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy = RetryPolicy(),
    retryable: Callable[[Exception], bool] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> SupervisionResult:
    """Return recovered or degraded state without leaking credentials in errors."""

    should_retry = retryable or (lambda error: isinstance(error, (TimeoutError, OSError, ConnectionError)))
    last_error: Exception | None = None
    attempts = 0
    for attempt in range(1, policy.max_attempts + 1):
        attempts = attempt
        try:
            return SupervisionResult("healthy", attempt, operation(), None)
        except Exception as error:  # noqa: BLE001 - supervision must record every operation failure
            last_error = error
            if attempt == policy.max_attempts or not should_retry(error):
                break
            sleeper(policy.backoff_seconds * (2 ** (attempt - 1)))
    return SupervisionResult("degraded", attempts, None, redact_error(last_error))


def redact_endpoint(endpoint: str) -> str:
    """Return a stable origin-only endpoint reference safe for persisted output.

    RPC credentials are commonly carried in userinfo, path segments or query
    strings. The configured endpoint is still used unchanged by the transport;
    only exported provenance and error text use this origin reference.
    """

    if not isinstance(endpoint, str) or not endpoint:
        return endpoint if isinstance(endpoint, str) else ""
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            return "[REDACTED_ENDPOINT]"
        host = hostname.lower()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme.lower()}://{host}{port}"
    except ValueError:
        return "[REDACTED_ENDPOINT]"


def redact_error(error: Exception | None) -> str | None:
    if error is None:
        return None
    message = str(error)
    message = re.sub(
        r"(?i)https?://[^\s,;]+",
        lambda match: redact_endpoint(match.group(0)),
        message,
    )
    message = re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+",
        r"\1[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)(api[-_]?key|token|password|secret)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", message)
    message = re.sub(r"0x[0-9a-fA-F]{64}", "0x[REDACTED]", message)
    return f"{type(error).__name__}: {message}"
