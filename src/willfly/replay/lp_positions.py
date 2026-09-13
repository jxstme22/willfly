"""Small-position LP position and fee-growth replay primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace


Q128 = 1 << 128
Q96 = 1 << 96
UINT256_MODULUS = 1 << 256


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
    owner: str | None = None

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


def amounts_for_sqrt_price(
    position: PositionState,
    *,
    current_sqrt_price_x96: int,
    lower_sqrt_price_x96: int,
    upper_sqrt_price_x96: int,
) -> tuple[int, int]:
    """Calculate Uniswap-style token amounts from exact Q96 sqrt prices.

    The caller supplies the protocol's tick-to-price results so this boundary
    does not silently replace deployed TickMath with a float approximation.
    """

    prices = (current_sqrt_price_x96, lower_sqrt_price_x96, upper_sqrt_price_x96)
    if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in prices):
        raise ValueError("sqrt prices must be positive integers")
    if not lower_sqrt_price_x96 < upper_sqrt_price_x96:
        raise ValueError("sqrt price range must be increasing")
    liquidity = position.liquidity
    if current_sqrt_price_x96 <= lower_sqrt_price_x96:
        return (
            liquidity * (upper_sqrt_price_x96 - lower_sqrt_price_x96) * Q96 // upper_sqrt_price_x96 // lower_sqrt_price_x96,
            0,
        )
    if current_sqrt_price_x96 < upper_sqrt_price_x96:
        return (
            liquidity * (upper_sqrt_price_x96 - current_sqrt_price_x96) * Q96 // upper_sqrt_price_x96 // current_sqrt_price_x96,
            liquidity * (current_sqrt_price_x96 - lower_sqrt_price_x96) // Q96,
        )
    return (
        0,
        liquidity * (upper_sqrt_price_x96 - lower_sqrt_price_x96) // Q96,
    )


def accrue_fee_growth(position: PositionState, *, current_tick: int, fee_growth_inside0: int, fee_growth_inside1: int) -> PositionState:
    if any(
        not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < UINT256_MODULUS
        for value in (fee_growth_inside0, fee_growth_inside1, position.fee_growth_inside0_last, position.fee_growth_inside1_last)
    ):
        raise ValueError("fee growth cannot be negative")
    if not position.tick_lower <= current_tick < position.tick_upper:
        return position
    delta0 = (fee_growth_inside0 - position.fee_growth_inside0_last) % UINT256_MODULUS
    delta1 = (fee_growth_inside1 - position.fee_growth_inside1_last) % UINT256_MODULUS
    return replace(
        position,
        fee_growth_inside0_last=fee_growth_inside0,
        fee_growth_inside1_last=fee_growth_inside1,
        tokens_owed0=position.tokens_owed0 + delta0 * position.liquidity // Q128,
        tokens_owed1=position.tokens_owed1 + delta1 * position.liquidity // Q128,
    )
