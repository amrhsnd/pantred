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


if __name__ == '__main__':
    unittest.main()
