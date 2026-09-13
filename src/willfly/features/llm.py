"""Bounded, schema-checked enrichment with a numerical no-LLM fallback."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
from typing import Callable, Mapping, MutableMapping


@dataclass(frozen=True)
class LLMBudget:
    max_requests: int
    max_tokens: int

    def __post_init__(self) -> None:
        if min(self.max_requests, self.max_tokens) <= 0:
            raise ValueError("LLM budget must be positive")


@dataclass(frozen=True)
class LLMResult:
    status: str
    model_version: str
    prompt_version: str
    request_count: int
    token_count: int
    claims: tuple[Mapping[str, object], ...]
    fallback_used: bool
    reason: str | None


class LLMBudgetLedger:
    """Persistent per-run request/token accounting for bounded enrichment."""

    def __init__(self, max_requests: int, max_tokens: int, *, path: str | Path | None = None) -> None:
        if min(max_requests, max_tokens) <= 0:
            raise ValueError("LLM ledger limits must be positive")
        self.max_requests = max_requests
        self.max_tokens = max_tokens
        self.path = None if path is None else Path(path)
        self._lock = threading.RLock()
        self.requests = 0
        self.tokens = 0
        self.cache_hits = 0
        self.retries = 0
        if self.path is not None and self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("max_requests") != max_requests or payload.get("max_tokens") != max_tokens:
                raise ValueError("LLM ledger identity does not match its persisted limits")
            self.requests = int(payload.get("requests", 0))
            self.tokens = int(payload.get("tokens", 0))
            self.cache_hits = int(payload.get("cache_hits", 0))
            self.retries = int(payload.get("retries", 0))
            if min(self.requests, self.tokens, self.cache_hits, self.retries) < 0:
                raise ValueError("LLM ledger contains negative usage")

    def reserve_request(self) -> bool:
        with self._lock:
            if self.requests >= self.max_requests:
                return False
            self.requests += 1
            self._persist()
            return True

    def record_tokens(self, token_count: int) -> None:
        if token_count < 0:
            raise ValueError("token usage cannot be negative")
        with self._lock:
            self.tokens += token_count
            self._persist()

    def record_retry(self) -> None:
        with self._lock:
            self.retries += 1
            self._persist()

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1
            self._persist()

    def to_dict(self) -> dict[str, int]:
        return {
            "max_requests": self.max_requests,
            "max_tokens": self.max_tokens,
            "requests": self.requests,
            "tokens": self.tokens,
            "cache_hits": self.cache_hits,
            "retries": self.retries,
        }

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False, encoding="utf-8") as handle:
            temp_name = handle.name
            handle.write(json.dumps(self.to_dict(), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, self.path)


def bounded_enrich(
    source_text: str,
    *,
    call: Callable[[str], str] | None,
    budget: LLMBudget,
    model_version: str,
    prompt_version: str,
    fallback: Mapping[str, object] | None = None,
    cache: MutableMapping[str, LLMResult] | None = None,
    max_retries: int = 0,
    deadline_seconds: float | None = None,
    ledger: LLMBudgetLedger | None = None,
) -> LLMResult:
    if not source_text or not model_version or not prompt_version:
        raise ValueError("LLM enrichment metadata is required")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")
    if deadline_seconds is not None and deadline_seconds <= 0:
        raise ValueError("LLM deadline must be positive")
    cache_key = hashlib.sha256(f"{model_version}|{prompt_version}|{source_text}".encode()).hexdigest()
    if cache is not None and cache_key in cache:
        if ledger is not None:
            ledger.record_cache_hit()
        return cache[cache_key]
    if call is None:
        result = LLMResult("fallback", model_version, prompt_version, 0, 0, (dict(fallback or {"status": "unavailable"}),), True, "llm_not_configured")
        if cache is not None:
            cache[cache_key] = result
        return result
    if budget.max_requests < 1 or (
        ledger is not None and (ledger.requests >= ledger.max_requests or ledger.tokens >= ledger.max_tokens)
    ):
        return LLMResult("fallback", model_version, prompt_version, 0, 0, (dict(fallback or {"status": "budget_exhausted"}),), True, "budget_exhausted")
    last_error = "invalid_output"
    request_count = min(budget.max_requests, max_retries + 1)
    for attempt in range(1, request_count + 1):
        if ledger is not None and not ledger.reserve_request():
            last_error = "budget_exhausted"
            break
        if ledger is not None and attempt > 1:
            ledger.record_retry()
        try:
            raw = _call_with_deadline(call, source_text, deadline_seconds)
            token_count = len(raw.split())
            if ledger is not None:
                ledger.record_tokens(token_count)
            if token_count > budget.max_tokens:
                raise ValueError("token budget exceeded")
            if ledger is not None and ledger.tokens > ledger.max_tokens:
                raise ValueError("cumulative token budget exceeded")
            parsed = json.loads(raw)
            if not isinstance(parsed, list) or not all(isinstance(item, Mapping) and "claim_type" in item and "evidence" in item for item in parsed):
                raise ValueError("LLM output failed claim schema")
            allowed = {"narrative", "risk", "catalyst", "contradiction", "unknown"}
            if not all(item["claim_type"] in allowed and isinstance(item["evidence"], str)
                       and item["evidence"].strip() and item["evidence"] in source_text
                       for item in parsed):
                raise ValueError("claim type or literal source evidence is invalid")
            result = LLMResult("accepted", model_version, prompt_version, attempt, token_count, tuple(dict(item) for item in parsed), False, None)
            if cache is not None:
                cache[cache_key] = result
            return result
        except Exception as exc:  # noqa: BLE001 - enrichment must never block numeric features
            last_error = type(exc).__name__
    return LLMResult(
        "fallback",
        model_version,
        prompt_version,
        request_count,
        0,
        (dict(fallback or {"status": "invalid_output"}),),
        True,
        last_error,
    )


def _call_with_deadline(call: Callable[[str], str], source_text: str, deadline_seconds: float | None) -> str:
    if deadline_seconds is None:
        return call(source_text)
    result: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            result.put(("ok", call(source_text)))
        except Exception as exc:  # noqa: BLE001 - callback errors become bounded fallback
            result.put(("error", exc))

    worker = threading.Thread(target=invoke, name="willfly-llm-call", daemon=True)
    worker.start()
    worker.join(deadline_seconds)
    if worker.is_alive():
        raise TimeoutError("LLM deadline exceeded")
    kind, value = result.get_nowait()
    if kind == "error":
        raise value  # type: ignore[misc]
    if not isinstance(value, str):
        raise ValueError("LLM callback must return text")
    return value
