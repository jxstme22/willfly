"""Exact-input constant-product fill assumptions with explicit uncertainty."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PoolQuote:
    pool_id: str
    input_asset: str
    output_asset: str
    reserve_input_atomic: int
    reserve_output_atomic: int
    fee_bps: int
    observed_at: str
    hook_supported: bool = True

    def __post_init__(self) -> None:
        if min(self.reserve_input_atomic, self.reserve_output_atomic) <= 0:
            raise ValueError("pool reserves must be positive")
        if not 0 <= self.fee_bps < 10_000:
            raise ValueError("fee_bps must be between 0 and 9999")
        _parse(self.observed_at)


@dataclass(frozen=True)
class FillResult:
    status: str
    input_atomic: int
    output_atomic: int
    fee_atomic: int
    price_impact_bps: int | None
    available_at: str
    reason: str | None
    source_ref: str
    approximate: bool = True


def simulate_fill(
    quote: PoolQuote | None,
    *,
    input_atomic: int,
    submitted_at: str,
    processing_delay_seconds: int = 0,
    max_price_impact_bps: int | None = None,
    gas_fee_atomic: int = 0,
) -> FillResult:
    """Simulate one exact-input fill; never substitute a leader's observed fill."""

    if input_atomic <= 0 or gas_fee_atomic < 0 or processing_delay_seconds < 0:
        raise ValueError("fill amounts and delay are invalid")
    submitted = _parse(submitted_at)
    available_at = (submitted + timedelta(seconds=processing_delay_seconds)).isoformat()
    if quote is None:
        return FillResult("missing_state", input_atomic, 0, 0, None, available_at, "missing_historical_state", "quote:none")
    source_ref = f"quote:{quote.pool_id}:{quote.observed_at}"
    if _parse(quote.observed_at) > _parse(available_at):
        return FillResult("missing_state", input_atomic, 0, 0, None, available_at, "quote_after_execution_time", source_ref)
    if not quote.hook_supported:
        return FillResult("unsupported", input_atomic, 0, 0, None, available_at, "unsupported_hook_behavior", source_ref)
    fee = input_atomic * quote.fee_bps // 10_000
    net_input = input_atomic - fee
    output = quote.reserve_output_atomic * net_input // (quote.reserve_input_atomic + net_input)
    if output <= 0:
        return FillResult("reverted", input_atomic, 0, fee, None, available_at, "insufficient_depth", source_ref)
    impact_numerator = input_atomic * quote.reserve_output_atomic - output * quote.reserve_input_atomic
    impact_denominator = input_atomic * quote.reserve_output_atomic
    impact_bps = max(0, impact_numerator * 10_000 // impact_denominator)
    if max_price_impact_bps is not None and impact_bps > max_price_impact_bps:
        return FillResult("reverted", input_atomic, 0, fee, impact_bps, available_at, "price_impact_limit", source_ref)
    return FillResult("filled", input_atomic, output, fee + gas_fee_atomic, impact_bps, available_at, None, source_ref)


@dataclass(frozen=True)
class RoundTripResult:
    entry: FillResult
    exit: FillResult
    net_quote_atomic: int | None
    status: str


def simulate_follower_round_trip(
    entry_quote: PoolQuote | None,
    exit_quote: PoolQuote | None,
    *,
    quote_input_atomic: int,
    signal_received_at: str,
    processing_delay_seconds: int = 0,
    exit_delay_seconds: int = 0,
) -> RoundTripResult:
    """Requote entry and exit at follower availability times under one path."""

    if entry_quote is not None and exit_quote is not None and (
        entry_quote.input_asset != exit_quote.output_asset
        or entry_quote.output_asset != exit_quote.input_asset
    ):
        raise ValueError("round-trip quotes must reverse the same asset pair")

    entry = simulate_fill(
        entry_quote,
        input_atomic=quote_input_atomic,
        submitted_at=signal_received_at,
        processing_delay_seconds=processing_delay_seconds,
    )
    if entry.status != "filled":
        return RoundTripResult(entry, _unattempted(entry.available_at, "entry_not_filled"), None, "entry_failed")
    exit = simulate_fill(
        exit_quote,
        input_atomic=entry.output_atomic,
        submitted_at=entry.available_at,
        processing_delay_seconds=exit_delay_seconds,
    )
    if exit.status != "filled":
        return RoundTripResult(entry, exit, None, "exit_failed")
    return RoundTripResult(entry, exit, exit.output_atomic - quote_input_atomic, "completed")


def _unattempted(submitted_at: str, reason: str) -> FillResult:
    return FillResult("not_attempted", 0, 0, 0, None, submitted_at, reason, "quote:none")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed
