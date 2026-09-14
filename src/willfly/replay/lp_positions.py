"""Exact integer primitives for Robinhood-chain Uniswap V4-style positions.

The module deliberately stops at replay.  It does not quote a transaction or
claim that a deployment has the standard Uniswap hooks.  Callers must provide
the observed protocol state (including Q96 square-root prices and inside fee
growth) when they want an exact checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


Q128 = 1 << 128
Q96 = 1 << 96
UINT256_MODULUS = 1 << 256
MIN_TICK = -887272
MAX_TICK = 887272

# These are the constants from the Uniswap TickMath implementation.  Keeping
# them here avoids a float conversion (which loses atomic amounts at large
# liquidity values).
_TICK_RATIOS = (
    0xfffcb933bd6fad37aa2d162d1a594001,
    0xfff97272373d413259a46990580e213a,
    0xfff2e50f5f656932ef12357cf3c7fdcc,
    0xffe5caca7e10e4e61c3624eaa0941cd0,
    0xffcb9843d60f6159c9db58835c926644,
    0xff973b41fa98c081472e6896dfb254c0,
    0xff2ea16466c96a3843ec78b326b52861,
    0xfe5dee046a99a2a811c461f1969c3053,
    0xfcbe86c7900a88aedcffc83b479aa3a4,
    0xf987a7253ac413176f2b074cf7815e54,
    0xf3392b0822b70005940c7a398e4b70f3,
    0xe7159475a2c29b7443b29c7fa6e889d9,
    0xd097f3bdfd2022b8845ad8f792aa5825,
    0xa9f746462d870fdf8a65dc1f90e061e5,
    0x70d869a156d2a1b890bb3df62baf32f7,
    0x31be135f97d08fd981231505542fcfa6,
    0x9aa508b5b7a84e1c677de54f3e99bc9,
    0x5d6af8dedb81196699c329225ee604,
    0x2216e584f5fa1ea926041bedfe98,
    0x48a170391f7dc42444e8fa2,
)


def _uint(value: Any, field: str, *, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} is out of range")
    return value


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
    tick_spacing: int | None = None
    current_tick: int | None = None
    sqrt_price_x96: int | None = None
    hooks: str | None = None
    # Naming aliases used by some RPC position adapters.
    current_sqrt_price_x96: int | None = None
    hook: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.position_id, str) or not self.position_id:
            raise ValueError("LP position_id is invalid")
        if not isinstance(self.pool_id, str) or not self.pool_id:
            raise ValueError("LP pool_id is invalid")
        if not isinstance(self.token0, str) or not self.token0:
            raise ValueError("LP token0 is invalid")
        if not isinstance(self.token1, str) or not self.token1 or self.token0 == self.token1:
            raise ValueError("LP token1 is invalid")
        _uint(self.liquidity, "liquidity")
        if not isinstance(self.tick_lower, int) or isinstance(self.tick_lower, bool):
            raise ValueError("tick_lower must be an integer")
        if not isinstance(self.tick_upper, int) or isinstance(self.tick_upper, bool):
            raise ValueError("tick_upper must be an integer")
        if self.tick_lower >= self.tick_upper:
            raise ValueError("LP position is invalid")
        for value, field in (
            (self.fee_growth_inside0_last, "fee_growth_inside0_last"),
            (self.fee_growth_inside1_last, "fee_growth_inside1_last"),
        ):
            _uint(value, field, maximum=UINT256_MODULUS - 1)
        _uint(self.tokens_owed0, "tokens_owed0")
        _uint(self.tokens_owed1, "tokens_owed1")
        if self.tick_spacing is not None:
            _uint(self.tick_spacing, "tick_spacing")
            if self.tick_spacing == 0:
                raise ValueError("tick_spacing must be positive")
        if self.current_tick is not None and (
            not isinstance(self.current_tick, int) or isinstance(self.current_tick, bool)
        ):
            raise ValueError("current_tick must be an integer")
        if self.sqrt_price_x96 is not None:
            _uint(self.sqrt_price_x96, "sqrt_price_x96")
            if self.sqrt_price_x96 == 0:
                raise ValueError("sqrt_price_x96 must be positive")
        if self.current_sqrt_price_x96 is not None:
            _uint(self.current_sqrt_price_x96, "current_sqrt_price_x96")
            if self.current_sqrt_price_x96 == 0:
                raise ValueError("current_sqrt_price_x96 must be positive")
        if self.sqrt_price_x96 is not None and self.current_sqrt_price_x96 is not None and self.sqrt_price_x96 != self.current_sqrt_price_x96:
            raise ValueError("sqrt price aliases disagree")
        if self.hook is not None and (not isinstance(self.hook, str) or not self.hook):
            raise ValueError("hook must be non-empty text when supplied")
        if self.hooks is not None and (not isinstance(self.hooks, str) or not self.hooks):
            raise ValueError("hooks must be non-empty text when supplied")
        if self.hook is not None and self.hooks is not None and self.hook.lower() != self.hooks.lower():
            raise ValueError("hook aliases disagree")


def round_tick(tick: int, spacing: int, *, upper: bool = False) -> int:
    if not isinstance(tick, int) or isinstance(tick, bool):
        raise ValueError("tick must be an integer")
    if spacing <= 0:
        raise ValueError("tick spacing must be positive")
    quotient, remainder = divmod(tick, spacing)
    if upper and remainder:
        quotient += 1
    return quotient * spacing


def sqrt_price_at_tick(tick: int) -> int:
    """Return Uniswap's exact Q96 square-root price for ``tick``.

    This is the integer TickMath algorithm, including its upward final
    rounding.  It is useful for fixture mechanics and independently supplied
    deployment state; it is not proof that an observed pool uses this math.
    """

    if not isinstance(tick, int) or isinstance(tick, bool) or not MIN_TICK <= tick <= MAX_TICK:
        raise ValueError("tick is outside the supported TickMath range")
    absolute = -tick if tick < 0 else tick
    ratio = _TICK_RATIOS[0] if absolute & 1 else (1 << 128)
    for bit, constant in enumerate(_TICK_RATIOS[1:], start=1):
        if absolute & (1 << bit):
            ratio = (ratio * constant) >> 128
    if tick > 0:
        ratio = ((1 << 256) - 1) // ratio
    result = ratio >> 32
    if ratio & ((1 << 32) - 1):
        result += 1
    return result


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
        return (liquidity * (upper_sqrt_price_x96 - lower_sqrt_price_x96) * Q96 // upper_sqrt_price_x96 // lower_sqrt_price_x96, 0)
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
    if not isinstance(current_tick, int) or isinstance(current_tick, bool):
        raise ValueError("current_tick must be an integer")
    for value, field in (
        (fee_growth_inside0, "fee_growth_inside0"),
        (fee_growth_inside1, "fee_growth_inside1"),
    ):
        _uint(value, field, maximum=UINT256_MODULUS - 1)
    # The pool's *inside* growth already incorporates range crossings.  A
    # position must settle the delta even when the current tick is now below
    # or above its range; conditioning accrual on current in-range status
    # loses fees earned before an exit.
    delta0 = (fee_growth_inside0 - position.fee_growth_inside0_last) % UINT256_MODULUS
    delta1 = (fee_growth_inside1 - position.fee_growth_inside1_last) % UINT256_MODULUS
    return replace(
        position,
        fee_growth_inside0_last=fee_growth_inside0,
        fee_growth_inside1_last=fee_growth_inside1,
        tokens_owed0=position.tokens_owed0 + delta0 * position.liquidity // Q128,
        tokens_owed1=position.tokens_owed1 + delta1 * position.liquidity // Q128,
        current_tick=current_tick,
    )


def fee_growth_inside_from_outside(
    position: PositionState,
    *,
    current_tick: int,
    fee_growth_global0: int,
    fee_growth_global1: int,
    fee_growth_outside_lower0: int,
    fee_growth_outside_lower1: int,
    fee_growth_outside_upper0: int,
    fee_growth_outside_upper1: int,
) -> tuple[int, int]:
    """Derive V3/V4-style inside growth from global and boundary snapshots.

    All subtraction is uint256 modular arithmetic, matching the protocol's
    fee-growth counters.  The caller still has to establish that the supplied
    snapshots belong to the same canonical pool checkpoint.
    """

    values = (
        fee_growth_global0,
        fee_growth_global1,
        fee_growth_outside_lower0,
        fee_growth_outside_lower1,
        fee_growth_outside_upper0,
        fee_growth_outside_upper1,
    )
    for value in values:
        _uint(value, "fee growth", maximum=UINT256_MODULUS - 1)
    if current_tick < position.tick_lower:
        return (
            (fee_growth_outside_lower0 - fee_growth_outside_upper0) % UINT256_MODULUS,
            (fee_growth_outside_lower1 - fee_growth_outside_upper1) % UINT256_MODULUS,
        )
    if current_tick < position.tick_upper:
        return (
            (fee_growth_global0 - fee_growth_outside_lower0 - fee_growth_outside_upper0) % UINT256_MODULUS,
            (fee_growth_global1 - fee_growth_outside_lower1 - fee_growth_outside_upper1) % UINT256_MODULUS,
        )
    return (
        (fee_growth_outside_upper0 - fee_growth_outside_lower0) % UINT256_MODULUS,
        (fee_growth_outside_upper1 - fee_growth_outside_lower1) % UINT256_MODULUS,
    )


__all__ = [
    "MAX_TICK",
    "MIN_TICK",
    "PositionState",
    "Q96",
    "Q128",
    "UINT256_MODULUS",
    "amounts_for_liquidity",
    "amounts_for_sqrt_price",
    "accrue_fee_growth",
    "fee_growth_inside_from_outside",
    "round_tick",
    "sqrt_price_at_tick",
]
