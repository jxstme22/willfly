"""Small-position LP position and fee-growth replay primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace


Q128 = 1 << 128


@dataclass(frozen=True)
class PositionState:
    position_id: str
    pool_id: str
    token0: str
    token1: str
    liquidity: int
    tick_lower: int
    tick_upper: int
    fee_growth_inside0_last: int = 0
    fee_growth_inside1_last: int = 0
    tokens_owed0: int = 0
    tokens_owed1: int = 0

    def __post_init__(self) -> None:
        if not self.position_id or not self.pool_id or self.liquidity < 0 or self.tick_lower >= self.tick_upper:
            raise ValueError("LP position is invalid")


def round_tick(tick: int, spacing: int, *, upper: bool = False) -> int:
    if spacing <= 0:
        raise ValueError("tick spacing must be positive")
    quotient, remainder = divmod(tick, spacing)
    if upper and remainder:
        quotient += 1
    return quotient * spacing


def amounts_for_liquidity(position: PositionState, current_tick: int) -> tuple[int, int]:
    """Use an integer linearized tick model and label it as a counterfactual."""

    width = position.tick_upper - position.tick_lower
    if current_tick <= position.tick_lower:
        return position.liquidity * width, 0
    if current_tick >= position.tick_upper:
        return 0, position.liquidity * width
    return position.liquidity * (position.tick_upper - current_tick), position.liquidity * (current_tick - position.tick_lower)


def accrue_fee_growth(position: PositionState, *, current_tick: int, fee_growth_inside0: int, fee_growth_inside1: int) -> PositionState:
    if min(fee_growth_inside0, fee_growth_inside1) < 0:
        raise ValueError("fee growth cannot be negative")
    if not position.tick_lower <= current_tick < position.tick_upper:
        return position
    delta0 = max(0, fee_growth_inside0 - position.fee_growth_inside0_last)
    delta1 = max(0, fee_growth_inside1 - position.fee_growth_inside1_last)
    return replace(
        position,
        fee_growth_inside0_last=fee_growth_inside0,
        fee_growth_inside1_last=fee_growth_inside1,
        tokens_owed0=position.tokens_owed0 + delta0 * position.liquidity // Q128,
        tokens_owed1=position.tokens_owed1 + delta1 * position.liquidity // Q128,
    )
