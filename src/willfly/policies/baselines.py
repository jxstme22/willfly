"""Simple predeclared baselines for the first trading laboratory."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketObservation:
    token: str
    as_of_time: str
    verified_flow_atomic: int
    liquidity_atomic: int
    price_change_bps: int
    candidate_available: bool = True
    cohort_state: str = "unknown"
    consecutive_positive_intervals: int = 0
    position_open: bool = False
    position_age_seconds: int = 0


@dataclass(frozen=True)
class BaselineDecision:
    policy: str
    action: str
    token: str
    allocation_fraction_bps: int
    reason: str
    perspective: str = "follower"


@dataclass(frozen=True)
class BaselineConfig:
    entry_allocation_bps: int = 500
    confirmation_intervals: int = 2
    minimum_flow_atomic: int = 1
    minimum_liquidity_atomic: int = 1
    hold_seconds: int = 300

    def __post_init__(self) -> None:
        if not 0 <= self.entry_allocation_bps <= 10_000:
            raise ValueError("entry allocation must be in basis points")
        if min(self.confirmation_intervals, self.minimum_flow_atomic, self.minimum_liquidity_atomic, self.hold_seconds) < 0:
            raise ValueError("baseline thresholds cannot be negative")


def idle_cash(observation: MarketObservation, config: BaselineConfig = BaselineConfig()) -> BaselineDecision:
    return BaselineDecision("idle_cash", "watch", observation.token, 0, "no_entry_by_definition")


def fixed_horizon_hold(observation: MarketObservation, config: BaselineConfig = BaselineConfig()) -> BaselineDecision:
    if observation.position_open and observation.position_age_seconds >= config.hold_seconds:
        return BaselineDecision("fixed_horizon_hold", "exit", observation.token, 0, "fixed_horizon_reached")
    if not observation.position_open and observation.candidate_available:
        return BaselineDecision("fixed_horizon_hold", "enter", observation.token, config.entry_allocation_bps, "candidate_available")
    return BaselineDecision("fixed_horizon_hold", "hold" if observation.position_open else "watch", observation.token, 0, "waiting_for_candidate")


def confirmation_momentum(observation: MarketObservation, config: BaselineConfig = BaselineConfig()) -> BaselineDecision:
    if observation.position_open and observation.price_change_bps < 0:
        return BaselineDecision("confirmation_momentum", "exit", observation.token, 0, "negative_momentum")
    if not observation.position_open and observation.price_change_bps > 0 and observation.consecutive_positive_intervals >= config.confirmation_intervals:
        return BaselineDecision("confirmation_momentum", "enter", observation.token, config.entry_allocation_bps, "confirmed_positive_momentum")
    return BaselineDecision("confirmation_momentum", "hold" if observation.position_open else "watch", observation.token, 0, "confirmation_not_met")


def verified_flow_filter(observation: MarketObservation, config: BaselineConfig = BaselineConfig()) -> BaselineDecision:
    qualifies = observation.verified_flow_atomic >= config.minimum_flow_atomic and observation.liquidity_atomic >= config.minimum_liquidity_atomic
    if observation.position_open and not qualifies:
        return BaselineDecision("verified_flow_filter", "exit", observation.token, 0, "flow_or_liquidity_below_threshold")
    if not observation.position_open and qualifies and observation.candidate_available:
        return BaselineDecision("verified_flow_filter", "enter", observation.token, config.entry_allocation_bps, "verified_flow_and_liquidity_confirmed")
    return BaselineDecision("verified_flow_filter", "hold" if observation.position_open else "watch", observation.token, 0, "verified_flow_filter_not_met")


def tracked_wallet_follow(observation: MarketObservation, config: BaselineConfig = BaselineConfig()) -> BaselineDecision:
    if observation.cohort_state != "member":
        return BaselineDecision("tracked_wallet_follow", "watch", observation.token, 0, "cohort_unavailable_or_uncertain")
    if not observation.position_open and observation.candidate_available:
        return BaselineDecision("tracked_wallet_follow", "enter", observation.token, config.entry_allocation_bps, "observed_prior_cohort_signal")
    return BaselineDecision("tracked_wallet_follow", "hold" if observation.position_open else "watch", observation.token, 0, "no_new_cohort_signal")
