"""Build the Binance/Hyperliquid sharp-candle report for GitHub Pages."""

import argparse
from bisect import bisect_left
from contextlib import closing
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

try:
    from .sharp_backtest import MINUTE, NOTIONAL, ROOT, SNAPSHOT, backtest, load_recording
    from .trade_preview import preview
except ImportError:
    from sharp_backtest import MINUTE, NOTIONAL, ROOT, SNAPSHOT, backtest, load_recording
    from trade_preview import preview

BINANCE_RATE = Decimal("0.001")
FEE_URL = "https://www.binance.com/en/fee/trading"
INTERVALS = {"1m": MINUTE, "5m": 5 * MINUTE, "15m": 15 * MINUTE}


class CandleReplay:
    """Conservative OHLC execution; never infer an unknown intrabar trade path."""

    def __init__(self, bars):
        self.bars = bars
        self.times = [bar[0] for bar in bars]

    def __call__(self, entry, stop, target, active, expiry, end, _times, _prices):
        result = dict(entry=float(entry), stop=float(stop), target=float(target),
                      fill=None, exit=None, pnl=None, gross=None, fees=0, reason=None,
                      ambiguous=False, status="Expired" if expiry <= end else "Pending")
        filled = False
        for index in range(bisect_left(self.times, active), len(self.bars)):
            time, opening, high, low, close = self.bars[index]
            if time >= end:
                break
            just_filled = False
            if not filled:
                if time >= expiry:
                    break
                if low > entry:
                    continue
                filled = just_filled = True
                result.update(fill=time, status="Open", fees=float(NOTIONAL * BINANCE_RATE))
            stopped = low <= stop
            touched_target = high >= target
            # When the bar starts above entry, its high can precede the fill.
            target_known_after_fill = not just_filled or opening <= entry or close >= target
            if touched_target and (stopped or not target_known_after_fill):
                result["ambiguous"] = True
            if not stopped and not (touched_target and target_known_after_fill):
                continue
            exit_price = min(opening, stop) if stopped else target
            before_fee_notional = NOTIONAL * exit_price / entry
            # On spot, the buy fee is deducted from received BTC; sell only net BTC.
            sell_notional = before_fee_notional * (1 - BINANCE_RATE)
            buy_fee_at_exit = before_fee_notional * BINANCE_RATE
            sell_fee = sell_notional * BINANCE_RATE
            fees = buy_fee_at_exit + sell_fee
            gross = before_fee_notional - NOTIONAL
            net = sell_notional - sell_fee - NOTIONAL
            result.update(exit=time, out=float(exit_price), gross=float(gross),
                          fees=float(fees), pnl=float(net), reason="Stop" if stopped else "Target",
                          status="Win" if net > 0 else "Loss" if net < 0 else "Flat")
            break
        return result


def load_binance(folder, interval):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["market"] != "spot" or manifest["symbol"] != "BTCUSDT":
        raise ValueError("Expected Binance spot BTCUSDT data.")
    metadata = next(item for item in manifest["results"] if item["timeframe"] == interval)
    path = folder / metadata["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError(f"CSV checksum mismatch: {path}")
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    bars = [(int(row["open_time_ms"]), *[Decimal(row[key]) for key in ("open", "high", "low", "close")])
            for row in rows]
    start, end = [int(datetime.fromisoformat(manifest[key]).timestamp()) * 1000
                  for key in ("start_inclusive", "end_exclusive")]
    step = INTERVALS[interval]
    if (len(bars) != metadata["rows"] or len(bars) != (end - start) // step
            or any(bar[0] != start + index * step for index, bar in enumerate(bars))):
        raise ValueError(f"Incomplete {interval} Binance candles.")
    if any(row["symbol"] != "BTCUSDT" or row["timeframe"] != interval for row in rows):
        raise ValueError("CSV market/interval does not match its manifest.")
    return bars, start, end, manifest


def dataset(market, interval, bars, start, end, runs, **metadata):
    dates = [datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
             for t in (start, end)]
    return dict(market=market, interval=interval, step=INTERVALS[interval],
                start=start, end=end, window=" – ".join(dates) + " UTC (end exclusive)",
                bars=[[t, *map(float, values)] for t, *values in bars], runs=runs, **metadata)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binance-dir", type=Path,
                        default=ROOT / "data/raw/binance/BTCUSDT/2026-10-24_2026-11-23")
    parser.add_argument("--database", type=Path, default=SNAPSHOT)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/market-backtest.html")
    parser.add_argument("--sharp-history", type=int, nargs="+", default=[30, 20, 10])
    parser.add_argument("--sharp-degree", type=int, nargs="+", default=[68, 100, 168, 250])
    parser.add_argument("--order-expiration", type=int, default=10, help="Minutes, for every interval.")
    args = parser.parse_args(argv)
    if min(args.sharp_history) < 1 or min(args.sharp_degree) < 0 or args.order_expiration < 1:
        parser.error("History and expiration must be positive; degree must be nonnegative.")
    if args.output.suffix.lower() != ".html":
        parser.error("Choose an .html output file.")
    histories, degrees = list(dict.fromkeys(args.sharp_history)), list(dict.fromkeys(args.sharp_degree))
    catalog = []
    for interval, step in INTERVALS.items():
        bars, start, end, manifest = load_binance(args.binance_dir, interval)
        # Keep the first lookback bars as warmup; do not invent pre-window history.
        if len(bars) < max(histories) + 3:
            parser.error(f"Not enough {interval} candles for the requested history.")
        # The 1m execution feed preserves minute expiry for every signal interval.
        execution_bars, _, _, _ = load_binance(args.binance_dir, "1m") if interval != "1m" else (bars, start, end, manifest)
        replay = CandleReplay(execution_bars)
        runs = [backtest(bars, [], [], start, end, history, degree, args.order_expiration,
                         replayer=replay, step=step) for degree in degrees for history in histories]
        catalog.append(dataset(
            "binance", interval, bars, start, end, runs, label="Binance · BTC/USDT spot",
            symbol="BTC/USDT", currency="USDT", execution="1m candles · conservative fills",
            fee_label="0.1% buy / 0.1% sell · standard spot tier · no BNB discount",
            fee_url=FEE_URL, maker_rate=float(BINANCE_RATE), taker_rate=float(BINANCE_RATE),
            source_url="https://github.com/binance/binance-public-data",
            fee_checked="2026-11-23", csv_sha256={r["timeframe"]: r["sha256"] for r in manifest["results"]},
        ))
        print(f"Binance {interval}: {len(bars):,} candles; {sum(len(r['orders']) for r in runs):,} orders across {len(runs)} settings", flush=True)
    with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        bars, times, prices, start, end = load_recording(db, max(histories))
    runs = [backtest(bars, times, prices, start, end, history, degree, args.order_expiration)
            for degree in degrees for history in histories]
    catalog.append(dataset(
        "hyperliquid", "1m", bars, start, end, runs, label="Hyperliquid · BTC perpetual",
        symbol="BTC", currency="USD", execution="Recorded trades · tick replay",
        fee_label="0.015% maker / 0.045% taker · base perpetual tier",
        fee_url="https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees",
        maker_rate=0.00015, taker_rate=0.00045,
        source_url="https://github.com/amrhsnd/pantred/blob/main/docs/VM_RECORDING_TEST.md",
    ))
    # Keep the script-disabled fallback useful without embedding thousands of SVGs.
    fallback = {**catalog[0], "runs": [{**run, "orders": run["orders"][:3]} for run in catalog[0]["runs"]]}
    template = (ROOT / "web/market_backtest.html").read_text(encoding="utf-8")
    for key, value in dict(DATA=json.dumps(catalog, separators=(",", ":")),
                           EXPIRY=args.order_expiration, PREVIEW=preview(fallback, args.order_expiration)).items():
        template = template.replace("{{" + key + "}}", str(value))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template, encoding="utf-8")
    summary = [{"market": item["market"], "interval": item["interval"], "window": item["window"],
                "runs": [{"history": run["history"], "degree": run["degree"],
                          "orders": len(run["orders"]),
                          "wins": sum(o["status"] == "Win" for o in run["orders"]),
                          "losses": sum(o["status"] == "Loss" for o in run["orders"]),
                          "ambiguous": sum(o.get("ambiguous", False) for o in run["orders"]),
                          "gross": sum(o["gross"] or 0 for o in run["orders"]),
                          "fees": sum(o["fees"] for o in run["orders"]),
                          "net": sum((o["gross"] or 0) - o["fees"] for o in run["orders"])}
                         for run in item["runs"]]} for item in catalog]
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
