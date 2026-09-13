"""Bounded, schema-checked enrichment with a numerical no-LLM fallback."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
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
) -> LLMResult:
    if not source_text or not model_version or not prompt_version:
        raise ValueError("LLM enrichment metadata is required")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")
    cache_key = hashlib.sha256(f"{model_version}|{prompt_version}|{source_text}".encode()).hexdigest()
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    if call is None:
        result = LLMResult("fallback", model_version, prompt_version, 0, 0, (dict(fallback or {"status": "unavailable"}),), True, "llm_not_configured")
        if cache is not None:
            cache[cache_key] = result
        return result
    if budget.max_requests < 1:
        return LLMResult("fallback", model_version, prompt_version, 0, 0, (dict(fallback or {"status": "budget_exhausted"}),), True, "budget_exhausted")
    last_error = "invalid_output"
    request_count = min(budget.max_requests, max_retries + 1)
    for attempt in range(1, request_count + 1):
        try:
            raw = call(source_text)
            token_count = len(raw.split())
            if token_count > budget.max_tokens:
                raise ValueError("token budget exceeded")
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
