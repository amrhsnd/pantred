"""Replay the Bitcoin one-minute strategy and export a portable interactive chart."""

import argparse
from bisect import bisect_left
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
MINUTE = 60_000
NOTIONAL = Decimal("1000")
MAKER_RATE = Decimal("0.00015")
TAKER_RATE = Decimal("0.00045")
SNAPSHOT = ROOT / "data/hyperliquid/aws-run/soak-snapshot-2026-10-21-1416utc.sqlite3"


def replay_order(entry, stop, target, active, expiry, end, times, prices):
    result = dict(entry=float(entry), stop=float(stop), target=float(target),
                  fill=None, exit=None, pnl=None, gross=None, fees=0, reason=None,
                  status="Expired" if expiry <= end else "Pending")
    for index in range(bisect_left(times, active), bisect_left(times, expiry)):
        if prices[index] > entry:
            continue
        entry_fee = NOTIONAL * MAKER_RATE
        result.update(fill=times[index], status="Open", fees=float(entry_fee))
        for tick in range(index, len(times)):
            price = prices[tick]
            if price <= stop or price >= target:
                exit_price = price if price <= stop else target
                stopped = price <= stop
                exit_notional = NOTIONAL * exit_price / entry
                fees = entry_fee + exit_notional * (TAKER_RATE if stopped else MAKER_RATE)
                gross = exit_notional - NOTIONAL
                net = gross - fees
                result.update(exit=times[tick], out=float(exit_price), gross=float(gross),
                              fees=float(fees), pnl=float(net),
                              reason="Stop" if stopped else "Target",
                              status="Win" if net > 0 else "Loss" if net < 0 else "Flat")
                break
        break
    return result


def load_recording(connection, history):
    first, last = connection.execute(
        "SELECT min(event_ms), max(event_ms) FROM trades WHERE symbol='BTC'"
    ).fetchone()
    if first is None:
        raise ValueError("The database contains no BTC trades.")
    start = ((first + MINUTE - 1) // MINUTE) * MINUTE
    end = last // MINUTE * MINUTE
    bars = [(time, *map(Decimal, values)) for time, *values in connection.execute(
        """SELECT open_ms, open, high, low, close FROM candles
           WHERE symbol='BTC' AND interval='1m' AND open_ms>=? AND open_ms<?
           ORDER BY open_ms""", (start - history * MINUTE, end))]
    if not bars or end <= start:
        raise ValueError("The recording contains no complete BTC minutes.")
    if bars[-1][0] != end - MINUTE or bars[0][0] > start or any(
        b[0] - a[0] != MINUTE for a, b in zip(bars, bars[1:])
    ):
        raise ValueError("Missing one-minute candles inside the BTC replay window.")
    times, prices = [], []
    for time, price in connection.execute(
        """SELECT event_ms, price FROM trades WHERE symbol='BTC'
           AND event_ms>=? AND event_ms<? ORDER BY event_ms, CAST(trade_id AS INTEGER)""",
        (start, end)
    ):
        times.append(time)
        prices.append(Decimal(price))

    return bars, times, prices, start, end


def backtest(bars, times, prices, start, end, history, degree, expiration):
    sharp, orders = [], []
    invalid = 0
    ranges = [high - low for _, _, high, low, _ in bars]
    for index, (time, opening, high, low, close) in enumerate(bars):
        body = abs(close - opening)
        sharp.append(index >= history and body > 0 and
                     100 * body >= 68 * (high - low) and
                     100 * history * body > degree * sum(ranges[index-history:index]))
        if index < history + 2 or bars[index-2][0] < start:
            continue
        if sharp[index-2:index+1] != [False, True, False]:
            continue
        middle = bars[index-1]
        middle_change = middle[4] - middle[1]
        stop = bars[index-2][3]
        target = high if (close - opening) * middle_change > 0 else low
        if not stop < low < target:
            invalid += 1
            continue
        active = time + MINUTE
        order = replay_order(low, stop, target, active, active + expiration * MINUTE,
                             end, times, prices)
        order.update(i=index, side="Green" if middle_change > 0 else "Red")
        orders.append(order)
    return dict(history=history, degree=degree, orders=orders, invalid=invalid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=SNAPSHOT)
    parser.add_argument("--sharp-history", type=int, nargs="+", default=[30, 20, 10])
    parser.add_argument("--sharp-degree", type=int, nargs="+", default=[68, 100, 168, 250])
    parser.add_argument("--order-expiration", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/BTC-1m-backtest.html")
    parser.add_argument("--open", action="store_true", help="Open report in your default browser")
    args = parser.parse_args()
    if min(args.sharp_history) < 1 or min(args.sharp_degree) < 0 or args.order_expiration < 1:
        parser.error("History and expiration must be positive and degree must be nonnegative.")
    if not args.database.is_file():
        parser.error("Snapshot missing. Pass --database with a Pantred SQLite recording.")
    if args.output.suffix.lower() != ".html" or args.output.resolve() == args.database.resolve():
        parser.error("Choose a separate .html file for the report.")
    with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        bars, times, prices, start, end = load_recording(db, max(args.sharp_history))
    runs = [backtest(bars, times, prices, start, end, history, degree, args.order_expiration)
            for degree in dict.fromkeys(args.sharp_degree)
            for history in dict.fromkeys(args.sharp_history)]
    data = dict(bars=[[t, *map(float, values)] for t, *values in bars], runs=runs)
    dates = [datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M") for t in (start, end)]
    substitutions = dict(DATA=json.dumps(data, separators=(",", ":")), WINDOW=" – ".join(dates)+" UTC",
                         EXPIRY=args.order_expiration)
    report = (ROOT / "web/sharp_candle.html").read_text(encoding="utf-8")
    for key, value in substitutions.items():
        report = report.replace("{{"+key+"}}", str(value))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output.resolve())
    if args.open:
        webbrowser.open(args.output.resolve().as_uri())


if __name__ == "__main__":
    main()
