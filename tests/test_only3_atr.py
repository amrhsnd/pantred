from decimal import Decimal
import unittest

from scripts.only3_atr import ATR_PERIODS, backtest_atr, wilder_atr
from scripts.sharp_backtest import MINUTE


def bar(minute, opening, high, low, close):
    return (minute * MINUTE, *map(Decimal, map(str, (opening, high, low, close))))


class Only3AtrTest(unittest.TestCase):
    def sample(self, period=10):
        history = [bar(i, 101, 102, 100, 101) for i in range(period - 1)]
        return history + [bar(period-1, 100, 102, 98, 101),
                          bar(period, 101, 110, 100, 109),
                          bar(period+1, 107, 109, 106, 108)]

    def run_setup(self, bars, period=10, step=MINUTE, **kwargs):
        calls = []
        def record(entry, stop, target, active, expiry, end, times, prices):
            calls.append((entry, stop, target, active, expiry))
            return {}
        result = backtest_atr(bars, [], [], kwargs.get('start', 0),
                              kwargs.get('end', 1000 * MINUTE), period, 10,
                              replayer=record, step=step)
        return result, calls

    def test_inclusive_body_wick_and_fvg_boundaries_for_all_periods(self):
        for period in ATR_PERIODS:
            with self.subTest(period=period):
                result, calls = self.run_setup(self.sample(period), period)
                self.assertEqual(result['atr_period'], period)
                self.assertEqual(result['invalid'], 0)
                self.assertEqual(len(result['orders']), 1)
                self.assertEqual(calls, [(Decimal(108), Decimal(98), Decimal(110),
                                         (period+2)*MINUTE, (period+12)*MINUTE)])
                order = result['orders'][0]
                self.assertEqual(order['body_c2'], 8)
                self.assertEqual(order['upper_wick_c2'], 1)
                self.assertEqual(order['lower_wick_c2'], 1)
                self.assertEqual(order['fvg'], 4)

    def test_each_percentage_filter_rejects_a_violation(self):
        cases = [
            # Body below 80%; upper wick over 10%; lower wick over 10%.
            (bar(10, '101.001', 110, 100, 109), None),
            (bar(10, '100.5', 110, 100, '108.999'), None),
            (bar(10, '101.001', 110, 100, '109.5'), None),
            # Gap just below 50% of the 8-unit body, overlap and touching.
            (None, bar(11, 107, 109, '105.999', 108)),
            (None, bar(11, 101, 109, 101, 108)),
            (None, bar(11, 103, 109, 102, 108)),
        ]
        for middle, third in cases:
            with self.subTest(middle=middle, third=third):
                bars = self.sample()
                if middle is not None:
                    bars[-2] = middle
                if third is not None:
                    bars[-1] = third
                self.assertEqual(self.run_setup(bars)[0]['orders'], [])

    def test_atr_multiplier_boundary_is_inclusive(self):
        bars = [bar(i, 105, 110, 100, 105) for i in range(8)]
        bars += [bar(8, 101, 105, 100, 104),
                 bar(9, '101.5', 115, 100, '113.5'),
                 bar(10, 112, 114, 111, 112)]
        result, _ = self.run_setup(bars)
        self.assertEqual(result['orders'][0]['atr'], 10)
        self.assertEqual(result['orders'][0]['range_c2'], 15)
        bars[0] = bar(0, 105, '110.01', 100, 105)
        self.assertEqual(self.run_setup(bars)[0]['orders'], [])

    def test_true_range_includes_previous_close_and_uses_wilder_smoothing(self):
        bars = [bar(i, 100, 101, 99, 100) for i in range(10)]
        bars += [bar(10, 110, 111, 109, 110), bar(11, 110, 111, 109, 110)]
        values = wilder_atr(bars, 10)
        self.assertEqual(values[:9], [None]*9)
        self.assertEqual(values[9], 2)
        self.assertEqual(values[10], Decimal('2.9'))
        self.assertEqual(values[11], Decimal('2.81'))

    def test_warmup_requires_full_period_through_candle2(self):
        self.assertEqual(self.run_setup(self.sample()[3:])[0]['orders'], [])
        # First possible seed is at C2 when exactly x candles have closed.
        self.assertEqual(len(self.run_setup(self.sample()[1:])[0]['orders']), 1)

    def test_candle3_and_future_ranges_cannot_change_candle2_atr(self):
        bars = self.sample()
        baseline, calls = self.run_setup(bars)
        bars[-1] = bar(11, 107, 10000, 106, 108)
        bars += [bar(12, 108, 100000, 1, 109)]
        changed, new_calls = self.run_setup(bars)
        self.assertEqual(changed['orders'][0]['atr'], baseline['orders'][0]['atr'])
        self.assertEqual(new_calls, calls)
        # C3's enormous range also proves the previous range-share filter is gone.
        self.assertEqual(len(changed['orders']), 1)

    def test_missing_candles_restart_atr_and_cannot_form_a_setup(self):
        bars = self.sample()
        bars[8] = bar(80, 101, 102, 100, 101)
        self.assertEqual(self.run_setup(bars)[0]['orders'], [])
        values = wilder_atr([bar(0, 100, 101, 99, 100),
                             bar(2, 110, 111, 109, 110)], 1)
        self.assertEqual(values, [2, 2])  # No invented previous-close jump across a gap.

    def test_signal_timeframe_and_expiration_units(self):
        bars = [(t*5, *ohlc) for t, *ohlc in self.sample()]
        result, calls = self.run_setup(bars, step=5*MINUTE)
        self.assertEqual(len(result['orders']), 1)
        self.assertEqual(calls[0][-2:], (60*MINUTE, 70*MINUTE))

    def test_completed_in_window_three_candles_required(self):
        bars = self.sample()
        for kwargs in ({'start': 10*MINUTE}, {'end': 12*MINUTE-1}):
            self.assertEqual(self.run_setup(bars, **kwargs)[0]['orders'], [])
        self.assertEqual(len(self.run_setup(bars, start=9*MINUTE)[0]['orders']), 1)

    def test_middle_color_is_not_an_extra_filter(self):
        bars = self.sample()
        bars[-2] = bar(10, 109, 110, 100, 101)
        result, _ = self.run_setup(bars)
        self.assertEqual(result['orders'][0]['side'], 'Red')

    def test_bearish_fvg_preserves_buy_only_invalid_levels(self):
        bars = [bar(i, 109, 110, 108, 109) for i in range(9)]
        bars += [bar(9, 110, 112, 108, 109), bar(10, 109, 110, 100, 101),
                 bar(11, 103, 104, 101, 102)]
        result, calls = self.run_setup(bars)
        self.assertEqual(result['invalid'], 1)
        self.assertEqual(calls, [])

    def test_zero_range_and_doji_do_not_generate_orders(self):
        for middle in (bar(10, 100, 100, 100, 100), bar(10, 105, 110, 100, 105)):
            bars = self.sample()
            bars[-2] = middle
            self.assertEqual(self.run_setup(bars)[0]['orders'], [])

    def test_unsupported_period_rejected(self):
        with self.assertRaises(ValueError):
            self.run_setup(self.sample(), period=14)


if __name__ == '__main__':
    unittest.main()
