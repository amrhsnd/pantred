"""Command-line entry point for the read-only perpetual collector."""

import argparse
import asyncio
import csv
import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from data_collection.hyperliquid import INTERVALS, HyperliquidClient, now_ms
from data_collection.hyperliquid_recorder import backfill, record
from data_collection.market_store import MarketStore


def timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Must be a finite positive number")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Hyperliquid perpetual data collector (read-only)")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("markets", "backfill", "record", "status", "export"):
        command = commands.add_parser(name)
        command.add_argument("--testnet", action="store_true")
        command.add_argument("--database", type=Path, help="Defaults to data/hyperliquid/<network>.sqlite3")
        if name in {"markets", "backfill", "record"}:
            command.add_argument("--dex", default="", help="Optional HIP-3 dex name")
        if name in {"backfill", "record"}:
            command.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL"])
            command.add_argument("--timeframes", nargs="+", choices=INTERVALS, default=["1m"])
            command.add_argument("--lookback-hours", type=positive, default=24)
        if name == "backfill":
            command.add_argument("--start", help="ISO date/time; naive timestamps are UTC")
            command.add_argument("--end", help="Exclusive ISO end date/time; defaults to now")
        if name == "record":
            command.add_argument("--duration", type=positive, help="Stop after this many seconds, including setup")
        if name == "export":
            command.add_argument("--symbol", required=True, help="Exact symbol from markets")
            command.add_argument("--timeframe", choices=INTERVALS, default="1m")
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--heikin-ashi", action="store_true")
    return root


def export_candles(store: MarketStore, symbol: str, interval: str,
                   output: Path, heikin_ashi: bool = False) -> int:
    import pandas as pd
    from data_collection.heikin_ashi import add_heikin_ashi_columns

    # Exclude the still-forming candle; a past close time alone doesn't prove
    # that a final update was observed, so also expose the observation timestamp.
    df = pd.read_sql_query("""SELECT symbol, interval AS timeframe, open_ms, close_ms,
        open,high,low,close,volume,trade_count,received_ms FROM candles
        WHERE symbol=? AND interval=? AND close_ms < ? ORDER BY open_ms""",
                           store.db, params=(symbol, interval, now_ms()))
    if df.empty:
        raise ValueError("No stored candles match this symbol and interval")
    df.insert(2, "date", pd.to_datetime(df["open_ms"], unit="ms", utc=True))
    if heikin_ashi:
        for column in ("open", "high", "low", "close"):
            df[column] = pd.to_numeric(df[column])
        df = add_heikin_ashi_columns(df)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, quoting=csv.QUOTE_MINIMAL)
    return len(df)


def main(argv: list[str] | None = None) -> None:
    cli = parser()
    args = cli.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = HyperliquidClient(testnet=args.testnet)
    path = args.database or Path(f"data/hyperliquid/{client.network}.sqlite3")
    try:
        if args.command == "markets":
            for market in client.markets(args.dex):
                print(f"{market['name']:20} max leverage={market['maxLeverage']:3} "
                      f"mark={market['context']['markPx']}")
            return
        if args.command in {"status", "export"} and not path.is_file():
            raise ValueError(f"No database at {path}; run backfill or record first")
        with MarketStore(path, client.network) as store:
            if args.command == "status":
                print(json.dumps(store.summary(), indent=2))
            elif args.command == "export":
                rows = export_candles(store, args.symbol, args.timeframe,
                                      args.output, args.heikin_ashi)
                print(f"Exported {rows} candles to {args.output}")
            else:
                intervals = list(dict.fromkeys(args.timeframes))
                symbols = client.resolve_symbols(args.symbols, args.dex)
                for market in client.markets(args.dex):
                    if market["name"] in symbols:
                        store.observation("metadata", market["name"], market, now_ms())
                store.db.commit()
                if args.command == "backfill":
                    end = timestamp(args.end) if args.end else now_ms()
                    start = timestamp(args.start) if args.start else end - int(args.lookback_hours * 3_600_000)
                    if end > now_ms():
                        raise ValueError("End cannot be in the future")
                    backfill(client, store, symbols, intervals, start, end)
                else:
                    asyncio.run(record(client, store, symbols, intervals,
                                       args.lookback_hours, args.duration))
                print(json.dumps(store.summary(), indent=2))
    except KeyboardInterrupt:
        print(f"Recording stopped. Data saved in {path}")
    except (ValueError, OSError, sqlite3.Error) as exc:
        cli.exit(1, f"Collector error: {exc}\n")


if __name__ == "__main__":
    main()
