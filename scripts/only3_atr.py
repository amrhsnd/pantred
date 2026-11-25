"""Three-candle body/wick/FVG signals filtered by candle 2's Wilder ATR."""

from decimal import Decimal

try:
    from .sharp_backtest import MINUTE, replay_order
except ImportError:
    from sharp_backtest import MINUTE, replay_order

ATR_PERIODS = (10, 15, 20, 30, 50)
ATR_MULTIPLIER = Decimal("1.5")


def wilder_atr(bars, period, step=MINUTE):
    """Seed with mean(TR, period), then RMA; restart after missing candles.

    TR = max(high-low, abs(high-previous close), abs(low-previous close)).
    A segment's first TR is high-low. None means the seed is not ready.
    Each value uses only candles through that index, including that candle.
    """
    if period < 1 or step <= 0:
        raise ValueError("ATR period and candle step must be positive.")
    values, seed = [], []
    previous = average = None
    for candle in bars:
        time, _, high, low, close = candle
        if previous is None or time - previous[0] != step:
            seed, average = [], None
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous[4]), abs(low - previous[4]))
        if average is None:
            seed.append(true_range)
            if len(seed) == period:
                average = sum(seed, Decimal(0)) / period
        else:
            average = (average * (period - 1) + true_range) / period
        values.append(average)
        previous = candle
    return values


def backtest_atr(bars, times, prices, start, end, atr_period, expiration,
                 replayer=None, step=MINUTE):
    """Apply inclusive signal limits; preserve no_history's long order levels.

    FVG is the positive wick-to-wick gap between candles 1 and 3 in either
    direction. ATR is measured at candle 2, never candle 3 or a future bar.
    Earlier candles contribute only to ATR, not to the three-candle pattern.
    """
    if atr_period not in ATR_PERIODS or expiration < 1 or step <= 0:
        raise ValueError("ATR period must be 10, 15, 20, 30 or 50; expiration and step must be positive.")
    averages = wilder_atr(bars, atr_period, step)
    orders, invalid, warmup = [], 0, 0
    for index in range(2, len(bars)):
        first, middle, third = bars[index-2:index+1]
        if first[0] < start or third[0] + step > end:
            continue
        if middle[0] - first[0] != step or third[0] - middle[0] != step:
            continue
        average = averages[index-1]
        if average is None:
            warmup += 1
            continue
        _, opening, high, low, close = middle
        candle_range, body = high - low, abs(close - opening)
        upper, lower = high - max(opening, close), min(opening, close) - low
        fvg = max(Decimal(0), third[3] - first[2], first[3] - third[2])
        if (candle_range <= 0 or body <= 0 or average <= 0
                or 100 * body < 80 * candle_range
                or 100 * upper > 10 * candle_range
                or 100 * lower > 10 * candle_range
                or 100 * fvg < 50 * body
                or candle_range < ATR_MULTIPLIER * average):
            continue
        entry, stop, target = third[4], first[3], middle[2]
        if not stop < entry < target:
            invalid += 1
            continue
        active = third[0] + step
        order = (replayer or replay_order)(entry, stop, target, active,
                                          active + expiration * MINUTE, end, times, prices)
        order.update(i=index, side="Green" if close > opening else "Red",
                     atr=float(average), range_c2=float(candle_range),
                     body_c2=float(body), upper_wick_c2=float(upper),
                     lower_wick_c2=float(lower), fvg=float(fvg),
                     fvg_direction="Bullish" if third[3] > first[2] else "Bearish")
        orders.append(order)
    return dict(atr_period=atr_period, atr_multiplier=float(ATR_MULTIPLIER),
                orders=orders, invalid=invalid, warmup=warmup)


if __name__ == "__main__":
    try:
        from .market_backtest import main
    except ImportError:
        from market_backtest import main
    main(algorithm="only3_withATR")
