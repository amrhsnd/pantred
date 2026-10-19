"""Append-only observations and upserted candles for one Hyperliquid network."""

import json
import sqlite3
from pathlib import Path

from data_collection.hyperliquid import now_ms


class MarketStore:
    def __init__(self, path: Path, network: str = "mainnet") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT, interval TEXT, open_ms INTEGER, close_ms INTEGER,
                open TEXT, high TEXT, low TEXT, close TEXT, volume TEXT,
                trade_count INTEGER, received_ms INTEGER, payload TEXT,
                PRIMARY KEY(symbol, interval, open_ms));
            CREATE TABLE IF NOT EXISTS trades (
                symbol TEXT, event_ms INTEGER, trade_id TEXT, side TEXT,
                price TEXT, size TEXT, received_ms INTEGER, payload TEXT,
                PRIMARY KEY(symbol, event_ms, trade_id));
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY, channel TEXT, symbol TEXT,
                event_ms INTEGER, received_ms INTEGER, payload TEXT);
            CREATE INDEX IF NOT EXISTS observations_lookup
                ON observations(channel, symbol, received_ms);
            CREATE TABLE IF NOT EXISTS recorder_events (
                id INTEGER PRIMARY KEY, time_ms INTEGER, kind TEXT, details TEXT);
        """)
        stored = self.db.execute("SELECT value FROM settings WHERE key='network'").fetchone()
        if stored and stored[0] != network:
            self.db.close()
            raise ValueError("Use separate databases for mainnet and testnet")
        self.db.execute("INSERT OR IGNORE INTO settings VALUES ('network', ?)", (network,))
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.commit()
        self.db.close()

    def event(self, kind: str, details: str) -> None:
        self.db.execute("INSERT INTO recorder_events(time_ms,kind,details) VALUES (?,?,?)",
                        (now_ms(), kind, details))

    def save_candles(self, rows: list[dict], received_ms: int | None = None) -> None:
        received = now_ms() if received_ms is None else received_ms
        for c in rows:
            self.db.execute("""
                INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol,interval,open_ms) DO UPDATE SET
                    close_ms=excluded.close_ms, open=excluded.open, high=excluded.high,
                    low=excluded.low, close=excluded.close, volume=excluded.volume,
                    trade_count=excluded.trade_count, received_ms=excluded.received_ms,
                    payload=excluded.payload
                WHERE excluded.received_ms >= candles.received_ms
            """, (c["s"], c["i"], int(c["t"]), int(c["T"]), str(c["o"]),
                  str(c["h"]), str(c["l"]), str(c["c"]), str(c["v"]), int(c["n"]),
                  received, json.dumps(c)))

    def save_message(self, message: dict, received_ms: int | None = None) -> bool:
        received = now_ms() if received_ms is None else received_ms
        channel, data = message.get("channel"), message.get("data")
        if channel == "candle":
            self.save_candles(data if isinstance(data, list) else [data], received)
        elif channel == "trades":
            for trade in data:
                self.db.execute("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?)",
                                (trade["coin"], int(trade["time"]), str(trade["tid"]),
                                 trade["side"], str(trade["px"]), str(trade["sz"]),
                                 received, json.dumps(trade)))
        elif channel in {"l2Book", "activeAssetCtx"}:
            self.observation(channel, data["coin"], data, received, data.get("time"))
        elif channel == "error":
            raise ValueError(f"Hyperliquid stream error: {data}")
        else:
            return False
        return True

    def observation(self, channel: str, symbol: str, payload: dict, received: int,
                    event_ms: int | None = None) -> None:
        self.db.execute("""INSERT INTO observations
            (channel,symbol,event_ms,received_ms,payload) VALUES (?,?,?,?,?)""",
                        (channel, symbol, event_ms, received, json.dumps(payload)))

    def last_candle(self, symbol: str, interval: str) -> int | None:
        return self.db.execute("SELECT MAX(open_ms) FROM candles WHERE symbol=? AND interval=?",
                               (symbol, interval)).fetchone()[0]

    def summary(self) -> dict:
        counts = {table: self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("candles", "trades", "observations", "recorder_events")}
        counts["feeds"] = [dict(zip(("channel", "symbol", "last_received_ms"), row))
                           for row in self.db.execute("""SELECT channel,symbol,MAX(received_ms)
                               FROM observations GROUP BY channel,symbol
                               UNION ALL SELECT 'trades',symbol,MAX(received_ms)
                               FROM trades GROUP BY symbol
                               UNION ALL SELECT 'candle:' || interval,symbol,MAX(received_ms)
                               FROM candles GROUP BY symbol,interval""")]
        counts["recent_events"] = list(self.db.execute(
            "SELECT time_ms,kind,details FROM recorder_events ORDER BY id DESC LIMIT 10"))
        return counts
