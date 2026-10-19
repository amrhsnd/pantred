import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from data_collection.market_store import MarketStore
from monitor import Monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "market.sqlite3"
        self.monitor = Monitor(self.path)

    def test_empty_state_does_not_create_database(self):
        self.assertEqual(self.monitor.snapshot()["candles"], [])
        self.assertFalse(self.path.exists())

    def test_snapshot_filters_and_orders_saved_data(self):
        with MarketStore(self.path) as store:
            for symbol in ("BTC", "ETH"):
                for stamp in (0, 60_000, 120_000):
                    store.save_candles([{"s":symbol,"i":"1m","t":stamp,"T":stamp+59999,
                                         "o":"10","h":"12","l":"9","c":"11","v":"5","n":2}])
            store.save_message({"channel":"activeAssetCtx","data":{"coin":"BTC","ctx":{"markPx":"11"}}}, 123)
        result = self.monitor.snapshot("BTC", "1m", 2)
        self.assertEqual([row["open_ms"] for row in result["candles"]], [60000,120000])
        self.assertEqual(result["context"]["received_ms"],123)
        self.assertEqual(result["symbols"],["BTC","ETH"])
        self.assertEqual(self.monitor.snapshot("BTC' OR 1=1 --")["candles"], [])

    def test_recording_start_is_idempotent_and_stop_only_signals_owned_process(self):
        process = Mock()
        process.poll.return_value = None
        with patch("monitor.subprocess.Popen", return_value=process) as launch:
            self.monitor.control("start")
            self.monitor.control("start")
            launch.assert_called_once()
            process.poll.side_effect = [None, 0]
            self.assertFalse(self.monitor.control("stop")["running"])
            process.send_signal.assert_called_once()
        other = Monitor(self.path)
        self.assertFalse(other.control("stop")["running"])


if __name__ == "__main__":
    unittest.main()
