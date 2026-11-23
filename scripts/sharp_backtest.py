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

try:
    from .trade_preview import preview
except ImportError:
    from trade_preview import preview

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


def load_recording(connection):
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
           ORDER BY open_ms""", (start, end))]
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


def backtest(bars, times, prices, start, end, threshold, expiration,
             replayer=None, step=MINUTE):
    """Buy after a three-bar setup whose middle range dominates the total.

    Both comparisons are strict: range 2 > threshold% of the sum of ranges,
    and body 2 > 80% of range 2. No candles outside the setup are consulted.
    """
    if not 0 <= threshold <= 100 or expiration < 1 or step <= 0:
        raise ValueError("Threshold must be 0–100; expiration and step must be positive.")
    orders = []
    invalid = 0
    ranges = [high - low for _, _, high, low, _ in bars]
    for index, (time, opening, high, low, close) in enumerate(bars):
        if index < 2 or bars[index-2][0] < start or time + step > end:
            continue
        first, middle = bars[index-2:index]
        if middle[0] - first[0] != step or time - middle[0] != step:
            continue
        middle_change = middle[4] - middle[1]
        middle_range = ranges[index-1]
        if (middle_range <= 0 or 100 * middle_range <= threshold * sum(ranges[index-2:index+1])
                or 100 * abs(middle_change) <= 80 * middle_range):
            continue
        stop, target = first[3], middle[2]
        if not stop < close < target:
            invalid += 1
            continue
        active = time + step
        order = (replayer or replay_order)(close, stop, target, active,
                                          active + expiration * MINUTE, end, times, prices)
        order.update(i=index, side="Green" if middle_change > 0 else "Red")
        orders.append(order)
    return dict(threshold=threshold, orders=orders, invalid=invalid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=SNAPSHOT)
    parser.add_argument("--sharp-threshold", type=int, nargs="+", default=[50, 60, 70],
                        help="Middle range must strictly exceed this percent of the three ranges.")
    parser.add_argument("--order-expiration", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/BTC-1m-no-history.html")
    parser.add_argument("--open", action="store_true", help="Open report in your default browser")
    args = parser.parse_args()
    if min(args.sharp_threshold) < 0 or max(args.sharp_threshold) > 100 or args.order_expiration < 1:
        parser.error("Threshold must be 0–100 and expiration must be positive.")
    if not args.database.is_file():
        parser.error("Snapshot missing. Pass --database with a Pantred SQLite recording.")
    if args.output.suffix.lower() != ".html" or args.output.resolve() == args.database.resolve():
        parser.error("Choose a separate .html file for the report.")
    with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        bars, times, prices, start, end = load_recording(db)
    runs = [backtest(bars, times, prices, start, end, threshold, args.order_expiration)
            for threshold in dict.fromkeys(args.sharp_threshold)]
    data = dict(bars=[[t, *map(float, values)] for t, *values in bars], runs=runs)
    dates = [datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M") for t in (start, end)]
    substitutions = dict(DATA=json.dumps(data, separators=(",", ":")), WINDOW=" – ".join(dates)+" UTC",
                         EXPIRY=args.order_expiration, PREVIEW=preview(data, args.order_expiration))
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
