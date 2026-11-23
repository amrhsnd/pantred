from decimal import Decimal
import unittest

from scripts.market_backtest import CandleReplay
from scripts.sharp_backtest import MINUTE, backtest, replay_order


def bar(minute, opening, high, low, close):
    return (minute * MINUTE, *map(Decimal, map(str, (opening, high, low, close))))


class MarketBacktestTest(unittest.TestCase):
    def replay(self, bars, expiry=10 * MINUTE, end=20 * MINUTE):
        return CandleReplay(bars)(Decimal(100), Decimal(90), Decimal(110),
                                  MINUTE, expiry, end, [], [])

    def test_binance_fees_reduce_btc_before_sell(self):
        order = self.replay([bar(1, 100, 111, 99, 110)])
        self.assertEqual(order['status'], 'Win')
        self.assertEqual(order['gross'], 100)
        self.assertAlmostEqual(order['fees'], 2.1989)
        self.assertAlmostEqual(order['pnl'], 97.8011)
        self.assertAlmostEqual(order['gross'] - order['fees'], order['pnl'])

    def test_stop_wins_when_both_levels_touch(self):
        order = self.replay([bar(1, 100, 111, 89, 101)])
        self.assertEqual(order['reason'], 'Stop')
        self.assertEqual(order['out'], 90)
        self.assertTrue(order['ambiguous'])

    def test_target_before_possible_entry_is_not_assumed(self):
        order = self.replay([bar(1, 105, 111, 99, 101), bar(2, 100, 105, 89, 95)])
        self.assertEqual(order['exit'], 2 * MINUTE)
        self.assertEqual(order['reason'], 'Stop')
        self.assertTrue(order['ambiguous'])

    def test_entry_bar_close_can_prove_later_target(self):
        order = self.replay([bar(1, 105, 112, 99, 111)])
        self.assertEqual(order['reason'], 'Target')
        self.assertFalse(order['ambiguous'])

    def test_gap_stop_exits_at_open(self):
        order = self.replay([bar(1, 100, 105, 99, 101), bar(2, 85, 94, 80, 92)])
        self.assertEqual(order['reason'], 'Stop')
        self.assertEqual(order['out'], 85)

    def test_entry_at_expiry_is_excluded(self):
        order = self.replay([bar(10, 100, 111, 99, 110)])
        self.assertIsNone(order['fill'])
        self.assertEqual(order['status'], 'Expired')
        self.assertEqual(order['fees'], 0)

    def test_filled_position_can_exit_after_entry_expiration(self):
        order = self.replay([bar(1, 100, 105, 99, 101), bar(15, 105, 111, 100, 110)])
        self.assertEqual(order['exit'], 15 * MINUTE)

    def test_no_fill_before_activation_or_after_end(self):
        for bars in ([bar(0, 100, 111, 99, 110)], [bar(20, 100, 111, 99, 110)]):
            with self.subTest(bars=bars):
                self.assertIsNone(self.replay(bars)['fill'])

    def test_end_of_data_preserves_pending_and_open(self):
        pending = self.replay([bar(1, 102, 105, 101, 103)], end=2 * MINUTE)
        self.assertEqual(pending['status'], 'Pending')
        opened = self.replay([bar(1, 100, 105, 99, 101)], end=2 * MINUTE)
        self.assertEqual(opened['status'], 'Open')
        self.assertEqual(opened['fees'], 1)
        self.assertIsNone(opened['pnl'])

    def test_original_hyperliquid_fee_calculation(self):
        result = replay_order(Decimal(100), Decimal(90), Decimal(110), 0, MINUTE,
                              2 * MINUTE, [0, 1], [Decimal(100), Decimal(110)])
        self.assertAlmostEqual(result['fees'], .315)
        self.assertAlmostEqual(result['pnl'], 99.685)

    def test_signal_activation_scales_with_timeframe_and_expiry_stays_minutes(self):
        bars = [bar(0, 100, 101, 98, 100), bar(5, 99, 110, 99, 110),
                bar(10, 109, 110, 107, 108)]
        calls = []
        def record(entry, stop, target, active, expiry, end, times, prices):
            calls.append((active, expiry))
            return {}
        result = backtest(bars, [], [], 0, 35 * MINUTE, 60, 10,
                          replayer=record, step=5 * MINUTE)
        self.assertEqual(len(result['orders']), 1)
        self.assertEqual(calls, [(15 * MINUTE, 25 * MINUTE)])


class NoHistorySignalTest(unittest.TestCase):
    def run_setup(self, bars, threshold=50, start=0, end=10 * MINUTE):
        calls = []
        def record(entry, stop, target, active, expiry, end, times, prices):
            calls.append((entry, stop, target, active, expiry))
            return {}
        result = backtest(bars, [], [], start, end, threshold, 10, replayer=record)
        return result, calls

    def setup_bars(self, middle_high=110, middle_open=100, middle_close=110):
        return [bar(0, 101, 103, 100, 102),
                bar(1, middle_open, middle_high, 100, middle_close),
                bar(2, 106, 108, 105, 107)]

    def test_first_three_candles_use_close3_low1_high2_without_warmup(self):
        result, calls = self.run_setup(self.setup_bars())
        self.assertEqual(result['threshold'], 50)
        self.assertEqual(result['invalid'], 0)
        self.assertEqual(len(result['orders']), 1)
        self.assertEqual(calls, [(Decimal(107), Decimal(100), Decimal(110),
                                 3 * MINUTE, 13 * MINUTE)])

    def test_threshold_uses_sum_of_three_full_ranges_and_strict_boundary(self):
        # Outer ranges sum to 6: middle ranges 6, 9, 14 are exactly 50/60/70%.
        for threshold, middle in ((50, 6), (60, 9), (70, 14)):
            for extra, expected in ((0, 0), (Decimal('.01'), 1)):
                with self.subTest(threshold=threshold, extra=extra):
                    top = Decimal(100) + middle + extra
                    bars = [bar(0, 101, 103, 100, 102), bar(1, 100, top, 100, top),
                            bar(2, 102, 105, 102, 103)]
                    result, _ = self.run_setup(bars, threshold)
                    self.assertEqual(len(result['orders']), expected)

    def test_body_must_strictly_exceed_eighty_percent_of_middle_range(self):
        for close, expected in (('108', 0), ('108.001', 1), ('107.99', 0)):
            with self.subTest(close=close):
                result, _ = self.run_setup(self.setup_bars(middle_close=close))
                self.assertEqual(len(result['orders']), expected)

    def test_both_middle_colors_and_any_third_color_are_allowed(self):
        for red_middle in (False, True):
            for third_open in (106, 107, 108):
                with self.subTest(red_middle=red_middle, third_open=third_open):
                    bars = self.setup_bars(middle_open=110 if red_middle else 100,
                                           middle_close=100 if red_middle else 110)
                    bars[2] = bar(2, third_open, 108, 105, 107)
                    result, _ = self.run_setup(bars)
                    self.assertEqual(result['orders'][0]['side'], 'Red' if red_middle else 'Green')

    def test_prior_candle_size_cannot_change_setup(self):
        baseline, calls = self.run_setup(self.setup_bars())
        for prior in (bar(-1, 100, 101, 99, 100), bar(-1, 1, 10000, 1, 10000)):
            result, prefixed_calls = self.run_setup([prior] + self.setup_bars())
            self.assertEqual(prefixed_calls, calls)
            self.assertEqual(len(result['orders']), len(baseline['orders']))

    def test_incomplete_outside_window_and_nonconsecutive_setups_are_excluded(self):
        bars = self.setup_bars()
        cases = ((bars[:2], 0, 10 * MINUTE), (bars, MINUTE, 10 * MINUTE),
                 (bars, 0, 3 * MINUTE - 1),
                 ([bars[0], bars[1], bar(3, 106, 108, 105, 107)], 0, 10 * MINUTE))
        for sample, start, end in cases:
            with self.subTest(sample=sample, start=start, end=end):
                result, calls = self.run_setup(sample, start=start, end=end)
                self.assertEqual(result['orders'], [])
                self.assertEqual(calls, [])

    def test_zero_range_and_doji_middle_are_not_sharp(self):
        for middle in (bar(1, 100, 100, 100, 100), bar(1, 105, 110, 100, 105)):
            bars = self.setup_bars()
            bars[1] = middle
            self.assertEqual(self.run_setup(bars)[0]['orders'], [])

    def test_invalid_levels_are_counted_and_not_replayed(self):
        for third in (bar(2, 100, 101, 98, 100), bar(2, 110, 111, 109, 110)):
            bars = self.setup_bars()
            bars[2] = third
            result, calls = self.run_setup(bars)
            self.assertEqual(result['invalid'], 1)
            self.assertEqual(result['orders'], [])
            self.assertEqual(calls, [])


class FuturesReplayTest(unittest.TestCase):
    def replay(self, bars, funding=None, end=20 * MINUTE, target="110"):
        return CandleReplay(bars, market="usdm", funding=funding or [])(
            Decimal(100), Decimal(90), Decimal(target), MINUTE, 10 * MINUTE, end, [], [])

    def event(self, minute, rate, mark="120"):
        return {"fundingTime": minute * MINUTE + 3, "fundingRate": str(rate), "markPrice": mark}

    def test_futures_reject_missing_funding_input(self):
        with self.assertRaisesRegex(ValueError, "requires historical funding"):
            CandleReplay([], market="usdm")

    def test_resting_entry_and_target_use_maker_fees_on_constant_size(self):
        order = self.replay([bar(1, 105, 108, 102, 104), bar(2, 104, 108, 99, 101),
                             bar(3, 105, 111, 101, 110)])
        self.assertEqual(order['entry_liquidity'], 'Maker')
        self.assertAlmostEqual(order['fees'], .42)
        self.assertAlmostEqual(order['gross'], 100)
        self.assertAlmostEqual(order['pnl'], 99.58)

    def test_immediately_marketable_entry_uses_taker_fee(self):
        order = self.replay([bar(1, 100, 111, 99, 110)])
        self.assertEqual(order['entry_liquidity'], 'Taker')
        self.assertAlmostEqual(order['fees'], .72)
        self.assertAlmostEqual(order['pnl'], 99.28)

    def test_stop_exit_uses_taker_fee(self):
        order = self.replay([bar(2, 104, 108, 99, 101), bar(3, 100, 105, 89, 95)])
        self.assertAlmostEqual(order['fees'], .65)
        self.assertAlmostEqual(order['pnl'], -100.65)

    def test_funding_uses_historical_mark_and_sign(self):
        bars = [bar(1, 100, 105, 99, 101), bar(5, 105, 111, 100, 110)]
        for rate, cashflow in (("0.001", -1.2), ("-0.001", 1.2)):
            with self.subTest(rate=rate):
                order = self.replay(bars, [self.event(3, rate)])
                self.assertAlmostEqual(order['funding'], cashflow)
                self.assertEqual(order['funding_events'], 1)
                self.assertFalse(order['funding_ambiguous'])
                self.assertAlmostEqual(order['pnl'], 100 - .72 + cashflow)

    def test_entry_and_exit_minute_funding_is_conservative(self):
        bars = [bar(1, 100, 105, 99, 101), bar(5, 105, 111, 100, 110)]
        for minute in (1, 5):
            for rate, cashflow in (("0.001", -1.2), ("-0.001", 0)):
                with self.subTest(minute=minute, rate=rate):
                    order = self.replay(bars, [self.event(minute, rate)])
                    self.assertAlmostEqual(order['funding'], cashflow)
                    self.assertTrue(order['funding_ambiguous'])

    def test_funding_excludes_before_fill_after_exit_and_at_data_end(self):
        bars = [bar(2, 104, 108, 99, 101), bar(5, 105, 111, 100, 110)]
        events = [self.event(i, '.001') for i in (0, 1, 6, 20)]
        self.assertEqual(self.replay(bars, events)['funding'], 0)
        opened = self.replay(bars[:1], [{"fundingTime": 20 * MINUTE,
                                        "fundingRate": ".001", "markPrice": "120"}])
        self.assertEqual(opened['funding'], 0)

    def test_open_position_and_unfilled_order_funding(self):
        event = self.event(3, '.001')
        opened = self.replay([bar(1, 100, 105, 99, 101)], [event])
        self.assertEqual(opened['status'], 'Open')
        self.assertAlmostEqual(opened['fees'], .5)
        self.assertAlmostEqual(opened['funding'], -1.2)
        self.assertIsNone(opened['pnl'])
        unfilled = self.replay([bar(1, 105, 108, 102, 104)], [event])
        self.assertEqual(unfilled['funding'], 0)
        self.assertEqual(unfilled['fees'], 0)

    def test_win_loss_classification_includes_funding(self):
        bars = [bar(1, 100, '100.01', 99, 100), bar(5, 100, '100.02', 99, '100.02')]
        without = self.replay(bars, target='100.02')
        funded = self.replay(bars, [self.event(3, '-.001', mark='100')], target='100.02')
        self.assertEqual(without['status'], 'Loss')
        self.assertEqual(funded['status'], 'Win')
        self.assertAlmostEqual(funded['gross'] - funded['fees'] + funded['funding'], funded['pnl'])


if __name__ == '__main__':
    unittest.main()
