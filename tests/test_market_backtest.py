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
        # Three non-sharp bars warm up, followed by non-sharp / sharp / non-sharp.
        bars = [bar(i * 5, 100, 101, 99, 100) for i in range(3)]
        bars += [bar(15, 100, 101, 98, 100), bar(20, 99, 110, 99, 110),
                 bar(25, 109, 112, 107, 110)]
        calls = []
        def record(entry, stop, target, active, expiry, end, times, prices):
            calls.append((active, expiry))
            return {}
        result = backtest(bars, [], [], 0, 35 * MINUTE, 1, 68, 10,
                          replayer=record, step=5 * MINUTE)
        self.assertEqual(len(result['orders']), 1)
        self.assertEqual(calls, [(30 * MINUTE, 40 * MINUTE)])


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
