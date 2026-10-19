import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError

from data_collection.hyperliquid import HyperliquidClient
from data_collection.hyperliquid_cli import export_candles, timestamp
from data_collection.hyperliquid_recorder import backfill, heartbeat, record, subscriptions
from data_collection.market_store import MarketStore


def candle(start=60_000, close="11"):
    return {"s": "BTC", "i": "1m", "t": start, "T": start + 59_999,
            "o": "10", "h": "12", "l": "9", "c": close, "v": "2", "n": 3}


class HyperliquidClientTests(unittest.TestCase):
    def test_discovery_preserves_case_and_filters_delisted(self):
        client = HyperliquidClient()
        response = [{"universe": [{"name": "xyz:GOLD"}, {"name": "OLD", "isDelisted": True}]}, [{}, {}]]
        with patch.object(client, "info", return_value=response):
            self.assertEqual(client.resolve_symbols(["gold", "XYZ:GOLD"], "xyz"), ["xyz:GOLD"])
            with self.assertRaises(ValueError):
                client.resolve_symbols(["OLD"])

    def test_candles_enforce_exclusive_window_and_order(self):
        client = HyperliquidClient()
        with patch.object(client, "info", return_value=[candle(120_000), candle(0), candle()]) as info:
            result = client.candles("BTC", "1m", 60_000, 120_000)
            self.assertEqual([row["t"] for row in result], [60_000])
            self.assertEqual(info.call_args.args[0]["req"]["endTime"], 119_999)
        with self.assertRaises(ValueError):
            client.candles("BTC", "5s", 0, 1)

    def test_utc_date_parsing(self):
        self.assertEqual(timestamp("1970-01-01"), 0)
        self.assertEqual(timestamp("1970-01-01T01:00:00+01:00"), 0)

    def test_http_transient_errors_retry_but_bad_requests_fail_fast(self):
        client = HyperliquidClient()
        with patch("data_collection.hyperliquid.urlopen", side_effect=HTTPError(
            client.info_url, 429, "Rate limited", {}, None
        )) as fetch, patch("data_collection.hyperliquid.time.sleep"):
            with self.assertRaises(ConnectionError):
                client.info({"type": "meta"})
            self.assertEqual(fetch.call_count, 4)
        with patch("data_collection.hyperliquid.urlopen", side_effect=HTTPError(
            client.info_url, 400, "Bad request", {}, None
        )) as fetch, patch("data_collection.hyperliquid.time.sleep"):
            with self.assertRaises(ValueError):
                client.info({"type": "meta"})
            self.assertEqual(fetch.call_count, 1)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "markets.sqlite3"
        self.store = MarketStore(self.path)

    def tearDown(self):
        self.store.__exit__()
        self.temp.cleanup()

    def test_candles_update_without_duplicate_or_stale_overwrite(self):
        self.store.save_candles([candle()], 100)
        self.store.save_candles([candle(close="12")], 200)
        self.store.save_candles([candle(close="9")], 50)
        self.assertEqual(self.store.db.execute("SELECT close,received_ms FROM candles").fetchall(), [("12", 200)])

    def test_trades_deduplicate_by_coin_time_and_id(self):
        trade = {"coin": "BTC", "time": 100, "tid": 9, "side": "B", "px": "12.01", "sz": "0.001"}
        self.store.save_message({"channel": "trades", "data": [trade, trade]})
        self.store.save_message({"channel": "trades", "data": [{**trade, "time": 200}]})
        self.assertEqual(self.store.summary()["trades"], 2)

    def test_context_does_not_invent_exchange_timestamp(self):
        data = {"coin": "BTC", "ctx": {"funding": "0.00001", "openInterest": "5"}}
        self.store.save_message({"channel": "activeAssetCtx", "data": data}, 456)
        self.assertEqual(self.store.db.execute("SELECT event_ms,received_ms FROM observations").fetchone(), (None, 456))

    def test_network_separation(self):
        with self.assertRaisesRegex(ValueError, "separate databases"):
            MarketStore(self.path, "testnet")

    def test_backfill_reports_missing_history_and_resumes_last_candle(self):
        client = HyperliquidClient()
        with patch.object(client, "candles", return_value=[candle(120_000), candle(240_000)]) as fetch:
            backfill(client, self.store, ["BTC"], ["1m"], 0, 300_000)
            self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM recorder_events WHERE kind='coverage_warning'").fetchone()[0], 2)
            backfill(client, self.store, ["BTC"], ["1m"], 0, 300_000, resume=True)
            self.assertEqual(fetch.call_args.args[2], 240_000)

    def test_export_heikin_ashi_preserves_raw_prices_and_excludes_open_candle(self):
        self.store.save_candles([candle(), candle(120_000)])
        target = Path(self.temp.name) / "out.csv"
        with patch("data_collection.hyperliquid_cli.now_ms", return_value=150_000):
            self.assertEqual(export_candles(self.store, "BTC", "1m", target, True), 1)
        import pandas as pd
        data = pd.read_csv(target)
        self.assertEqual(data["close"].iloc[0], 11)
        self.assertIn("ha_close", data)

    def test_protocol_error_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.store.save_message({"channel": "error", "data": "Invalid subscription"})

    def test_stream_records_and_flushes_on_cancellation(self):
        class Socket:
            send = AsyncMock()

            async def recv(self):
                if not hasattr(self, "sent"):
                    self.sent = True
                    return json.dumps({"channel": "candle", "data": candle()})
                raise asyncio.CancelledError()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

        with patch("data_collection.hyperliquid_recorder.connect", return_value=Socket()), \
             patch("data_collection.hyperliquid_recorder.backfill"):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(record(HyperliquidClient(), self.store, ["BTC"], ["1m"]))
        self.assertEqual(self.store.summary()["candles"], 1)
        with MarketStore(self.path) as reader:
            self.assertEqual(reader.summary()["candles"], 1)
            self.assertEqual(reader.summary()["recent_events"][0][1], "stopped")

    def test_subscriptions_cover_required_public_feeds(self):
        feeds = subscriptions(["BTC"], ["1m", "5m"])
        self.assertEqual(len(feeds), 5)
        self.assertEqual({f["type"] for f in feeds}, {"trades", "l2Book", "activeAssetCtx", "candle"})

    def test_reconnect_logs_gap_and_repeats_backfill(self):
        with patch("data_collection.hyperliquid_recorder.connect",
                   side_effect=[OSError("Disconnected"), asyncio.CancelledError()]), \
             patch("data_collection.hyperliquid_recorder.backfill") as fill, \
             patch("data_collection.hyperliquid_recorder.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(record(HyperliquidClient(), self.store, ["BTC"], ["1m"]))
        self.assertEqual(fill.call_count, 2)
        self.assertTrue(fill.call_args.kwargs["resume"])
        self.assertEqual(self.store.db.execute(
            "SELECT COUNT(*) FROM recorder_events WHERE kind='disconnected'"
        ).fetchone()[0], 1)

    def test_application_heartbeat(self):
        socket = AsyncMock()
        with patch("data_collection.hyperliquid_recorder.asyncio.sleep",
                   side_effect=[None, asyncio.CancelledError()]):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(heartbeat(socket))
        socket.send.assert_awaited_once_with('{"method": "ping"}')


if __name__ == "__main__":
    unittest.main()
