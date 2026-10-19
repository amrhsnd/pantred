"""Local dashboard access to recorded Hyperliquid data and its owned recorder."""

import json
import signal
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

from data_collection.hyperliquid import now_ms

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data/hyperliquid/mainnet.sqlite3"


class Monitor:
    def __init__(self, database: Path = DATABASE):
        self.database = database
        self.process = None
        self.log = None
        self.lock = threading.Lock()

    def control(self, action: str) -> dict:
        with self.lock:
            if action == "start":
                if self.process is not None and self.process.poll() is None:
                    return self.process_status()
                if self.log:
                    self.log.close()
                self.database.parent.mkdir(parents=True, exist_ok=True)
                self.log = (self.database.parent / "recorder.log").open("a", encoding="utf-8")
                self.process = subprocess.Popen(
                    [sys.executable, "-B", str(ROOT / "main.py"), "hyperliquid", "record",
                     "--symbols", "BTC", "ETH", "SOL", "--timeframes", "1m", "5m", "15m", "1h",
                     "--database", str(self.database)],
                    cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
                )
            elif action == "stop":
                if self.process is not None and self.process.poll() is None:
                    self.process.send_signal(signal.SIGINT)
                    try:
                        self.process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        self.process.terminate()
                        self.process.wait(timeout=5)
                if self.log:
                    self.log.close()
                    self.log = None
            else:
                raise ValueError("Unknown recording action")
            return self.process_status()

    def process_status(self) -> dict:
        code = self.process.poll() if self.process else None
        return {"running": self.process is not None and code is None, "exit_code": code}

    def snapshot(self, symbol="BTC", interval="1m", limit=180) -> dict:
        result = {"now_ms": now_ms(), "process": self.process_status(), "symbol": symbol,
                  "interval": interval, "symbols": [], "intervals": [], "candles": [],
                  "trades": [], "book": None, "context": None, "events": []}
        if not self.database.is_file():
            return result
        db = sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"candles", "trades", "observations", "recorder_events"}.issubset(tables):
                return result
            result["symbols"] = [row[0] for row in db.execute("SELECT DISTINCT symbol FROM candles ORDER BY symbol")]
            result["intervals"] = [row[0] for row in db.execute(
                "SELECT DISTINCT interval FROM candles WHERE symbol=? ORDER BY interval", (symbol,))]
            result["candles"] = [dict(row) for row in db.execute("""SELECT open_ms,close_ms,
                open,high,low,close,volume,received_ms FROM candles WHERE symbol=? AND interval=?
                ORDER BY open_ms DESC LIMIT ?""", (symbol, interval, limit))][::-1]
            result["trades"] = [dict(row) for row in db.execute("""SELECT event_ms,side,price,size
                FROM trades WHERE symbol=? ORDER BY event_ms DESC LIMIT 30""", (symbol,))]
            for channel, key in (("l2Book", "book"), ("activeAssetCtx", "context")):
                row = db.execute("""SELECT payload,received_ms FROM observations
                    WHERE channel=? AND symbol=? ORDER BY received_ms DESC LIMIT 1""", (channel, symbol)).fetchone()
                if row:
                    result[key] = {"data": json.loads(row["payload"]), "received_ms": row["received_ms"]}
            result["events"] = [dict(row) for row in db.execute(
                "SELECT time_ms,kind,details FROM recorder_events ORDER BY id DESC LIMIT 8")]
            return result
        finally:
            db.close()
