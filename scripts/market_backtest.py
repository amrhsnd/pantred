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
    from .fetch_binance import validate_funding
    from .only3_atr import ATR_PERIODS, backtest_atr
except ImportError:
    from sharp_backtest import MINUTE, NOTIONAL, ROOT, SNAPSHOT, backtest, load_recording
    from trade_preview import preview
    from fetch_binance import validate_funding
    from only3_atr import ATR_PERIODS, backtest_atr

BINANCE_RATE = Decimal("0.001")
FUTURES_MAKER = Decimal("0.0002")
FUTURES_TAKER = Decimal("0.0005")
FEE_URL = "https://www.binance.com/en/fee/trading"
INTERVALS = {"1m": MINUTE, "5m": 5 * MINUTE, "15m": 15 * MINUTE}


class CandleReplay:
    """Conservative OHLC execution; never infer an unknown intrabar trade path."""

    def __init__(self, bars, market="spot", funding=None):
        self.bars = bars
        self.times = [bar[0] for bar in bars]
        if market not in ("spot", "usdm"):
            raise ValueError("Unknown execution market.")
        if market == "usdm" and funding is None:
            raise ValueError("Futures replay requires historical funding records.")
        self.market = market
        self.funding = funding or []

    def __call__(self, entry, stop, target, active, expiry, end, _times, _prices):
        result = dict(entry=float(entry), stop=float(stop), target=float(target),
                      fill=None, exit=None, pnl=None, gross=None, fees=0, reason=None,
                      ambiguous=False, status="Expired" if expiry <= end else "Pending")
        futures = self.market == "usdm"
        if futures:
            result.update(funding=0, funding_events=0, funding_ambiguous=False, entry_liquidity=None)
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
                entry_rate = (FUTURES_TAKER if time == active and opening <= entry else FUTURES_MAKER) if futures else BINANCE_RATE
                entry_fee = NOTIONAL * entry_rate
                result.update(fill=time, status="Open", fees=float(entry_fee))
                if futures:
                    result["entry_liquidity"] = "Taker" if entry_rate == FUTURES_TAKER else "Maker"
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
            gross = before_fee_notional - NOTIONAL
            if futures:
                fees = entry_fee + before_fee_notional * (FUTURES_TAKER if stopped else FUTURES_MAKER)
                net = gross - fees
            else:
                # Spot buy fees reduce received BTC; sell only net BTC.
                sell_notional = before_fee_notional * (1 - BINANCE_RATE)
                fees = before_fee_notional * BINANCE_RATE + sell_notional * BINANCE_RATE
                net = sell_notional * (1 - BINANCE_RATE) - NOTIONAL
            result.update(exit=time, out=float(exit_price), gross=float(gross),
                          fees=float(fees), pnl=float(net), reason="Stop" if stopped else "Target",
                          status="Win" if net > 0 else "Loss" if net < 0 else "Flat")
            break
        if futures and filled:
            cashflow = Decimal(0)
            possible_end = min(result["exit"] + MINUTE, end) if result["exit"] is not None else end
            for event in self.funding:
                timestamp = int(event["fundingTime"])
                if not result["fill"] <= timestamp < possible_end:
                    continue
                rate, mark = Decimal(event["fundingRate"]), Decimal(event["markPrice"])
                uncertain = (timestamp < result["fill"] + MINUTE
                             or (result["exit"] is not None and timestamp >= result["exit"]))
                if uncertain:
                    result["funding_ambiguous"] = True
                    # With unknown intraminute ordering, include possible charges,
                    # and credit receipts only when the position is definitely open.
                    if rate < 0:
                        continue
                cashflow -= NOTIONAL / entry * mark * rate
                result["funding_events"] += 1
            result["funding"] = float(cashflow)
            if result["pnl"] is not None:
                net += cashflow
                result.update(pnl=float(net), status="Win" if net > 0 else "Loss" if net < 0 else "Flat")
        return result


def load_binance(folder, interval, market="spot"):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["market"] != market or manifest["symbol"] != "BTCUSDT":
        raise ValueError(f"Expected Binance {market} BTCUSDT data.")
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


def load_funding(folder, manifest, start, end):
    metadata = manifest["funding"]
    path = folder / metadata["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("Funding file checksum mismatch.")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) != metadata["rows"]:
        raise ValueError("Funding record count does not match the manifest.")
    validate_funding(rows, "BTCUSDT", start, end)
    return rows


def dataset(market, interval, bars, start, end, runs, **metadata):
    dates = [datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
             for t in (start, end)]
    return dict(market=market, interval=interval, step=INTERVALS[interval],
                start=start, end=end, window=" – ".join(dates) + " UTC (end exclusive)",
                bars=[[t, *map(float, values)] for t, *values in bars], runs=runs, **metadata)


def main(argv=None, algorithm="no_history"):
    atr = algorithm == "only3_withATR"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binance-dir", type=Path,
                        default=ROOT / "data/raw/binance/BTCUSDT/2026-10-24_2026-11-23")
    parser.add_argument("--futures-dir", type=Path,
                        default=ROOT / "data/raw/binance-futures/BTCUSDT/2026-10-24_2026-11-23")
    parser.add_argument("--database", type=Path, default=SNAPSHOT)
    filename = "only3-withATR-backtest.html" if atr else "no-history-backtest.html"
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed" / filename)
    if atr:
        parser.add_argument("--atr-period", type=int, nargs="+", choices=ATR_PERIODS,
                            default=list(ATR_PERIODS), help="Wilder ATR periods; measured at candle 2.")
    else:
        parser.add_argument("--sharp-threshold", type=int, nargs="+", default=[50, 60, 70],
                            help="Middle range must strictly exceed this percent of the three ranges.")
    parser.add_argument("--order-expiration", type=int, default=10, help="Minutes, for every interval.")
    args = parser.parse_args(argv)
    settings = list(dict.fromkeys(args.atr_period if atr else args.sharp_threshold))
    if min(settings) < 0 or max(settings) > 100 or args.order_expiration < 1:
        parser.error("Threshold must be 0–100 and expiration must be positive.")
    if args.output.suffix.lower() != ".html":
        parser.error("Choose an .html output file.")
    runner = backtest_atr if atr else backtest
    catalog = []
    execution_bars, futures_start, futures_end, futures_manifest = load_binance(args.futures_dir, "1m", "usdm")
    funding = load_funding(args.futures_dir, futures_manifest, futures_start, futures_end)
    for interval, step in INTERVALS.items():
        bars, start, end, manifest = load_binance(args.futures_dir, interval, "usdm")
        if len(bars) < 3:
            parser.error(f"Not enough {interval} futures candles for a three-candle setup.")
        if (start, end) != (futures_start, futures_end):
            parser.error("Futures signal and execution windows differ.")
        replay = CandleReplay(execution_bars, market="usdm", funding=funding)
        runs = [runner(bars, [], [], start, end, setting, args.order_expiration,
                       replayer=replay, step=step) for setting in settings]
        catalog.append(dataset(
            "binance-futures", interval, bars, start, end, runs,
            label="Binance · BTC/USDT perpetual futures", symbol="BTC/USDT PERP", currency="USDT",
            execution="1m futures candles · conservative fills · historical funding",
            fee_label="0.02% maker / 0.05% taker · standard USD-M tier · no BNB discount",
            fee_url="https://www.binance.com/en/fee/futureFee", maker_rate=float(FUTURES_MAKER),
            taker_rate=float(FUTURES_TAKER), fee_checked="2026-11-23",
            source_url="https://github.com/binance/binance-public-data",
            funding_records=len(funding), funding_sha256=manifest["funding"]["sha256"],
            csv_sha256={r["timeframe"]: r["sha256"] for r in manifest["results"]},
        ))
        print(f"Binance futures {interval}: {len(bars):,} candles; {sum(len(r['orders']) for r in runs):,} orders across {len(runs)} settings", flush=True)
    for interval, step in INTERVALS.items():
        bars, start, end, manifest = load_binance(args.binance_dir, interval)
        if len(bars) < 3:
            parser.error(f"Not enough {interval} candles for a three-candle setup.")
        # The 1m execution feed preserves minute expiry for every signal interval.
        execution_bars, _, _, _ = load_binance(args.binance_dir, "1m") if interval != "1m" else (bars, start, end, manifest)
        replay = CandleReplay(execution_bars)
        runs = [runner(bars, [], [], start, end, setting, args.order_expiration,
                       replayer=replay, step=step) for setting in settings]
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
        bars, times, prices, start, end = load_recording(db)
    runs = [runner(bars, times, prices, start, end, setting, args.order_expiration)
            for setting in settings]
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
    title = "Three-candle FVG + ATR backtest" if atr else "No-history sharp candle backtest"
    signal_summary = ("Body 2 / range 2 ≥ 80% · Upper wick 2 / range 2 ≤ 10% · "
                      "Lower wick 2 / range 2 ≤ 10% · FVG / body 2 ≥ 50% · "
                      "Range 2 ≥ 1.5 × selected ATR." if atr else
                      "Range 2 / (range 1 + range 2 + range 3) &gt; selected threshold · "
                      "Body 2 / range 2 &gt; 80%.")
    signal_details = (
        'The pattern uses the last three completed candles. Candle 2 must have body/range ≥ 80%, '
        'upper wick/range ≤ 10%, lower wick/range ≤ 10%, FVG/body ≥ 50%, and range ≥ 1.5 × '
        'ATR(<span id="settingText"></span>) at candle 2. Range = high − low; body = |close − open|; '
        'upper wick = high − max(open, close); lower wick = min(open, close) − low. '
        'FVG is the positive gap between candle 1 and candle 3’s wicks: low 3 − high 1 (bullish) '
        'or low 1 − high 3 (bearish). Overlapping or touching wicks have zero FVG. '
        'All limits are inclusive. There is no range-share or candle-color requirement. '
        'ATR uses earlier candles from the same market/timeframe: true range = max(high − low, '
        '|high − previous close|, |low − previous close|). Wilder’s smoothing starts with the mean '
        'of x true ranges, then ATR = (previous ATR × (x − 1) + TR) / x. The first true range is '
        'high − low. ATR includes candle 2 and excludes candle 3 and later data. Signals wait '
        'for x candles through candle 2; missing candles restart ATR warmup. Zero ranges, '
        'bodies and ATR values are excluded. The existing buy-only execution is retained; '
        'bearish FVGs cannot satisfy its long stop/entry levels and are counted as invalid.' if atr else
        'Only the last three completed candles are used. Length means high minus low, including wicks. '
        'Candle 2 is sharp when its range is strictly greater than <span id="settingText"></span>% '
        'of the sum of all three ranges, and its body |close − open| is strictly greater than 80% '
        'of its own range. No earlier history or color filter is used; zero-range candles cannot be sharp.'
    )
    for key, value in dict(METRICS_JS=(ROOT / "web/backtest_metrics.js").read_text(encoding="utf-8"),
                           DATA=json.dumps(catalog, separators=(",", ":")),
                           REPORT_CONFIG=json.dumps(dict(atr=atr)), TITLE=title, BRANCH=algorithm,
                           PARAMETER_LABEL="ATR period" if atr else "Range threshold",
                           SIGNAL_SUMMARY=signal_summary, SIGNAL_DETAILS=signal_details,
                           EXPIRY=args.order_expiration, PREVIEW=preview(fallback, args.order_expiration)).items():
        template = template.replace("{{" + key + "}}", str(value))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template, encoding="utf-8")
    summary = [{"market": item["market"], "interval": item["interval"], "window": item["window"],
                "algorithm": algorithm,
                "runs": [{("atr_period" if atr else "threshold"): setting,
                          **({"atr_multiplier": run["atr_multiplier"], "warmup": run["warmup"]} if atr else {}),
                          "invalid": run["invalid"],
                          "orders": len(run["orders"]),
                          "wins": sum(o["status"] == "Win" for o in run["orders"]),
                          "losses": sum(o["status"] == "Loss" for o in run["orders"]),
                          "ambiguous": sum(o.get("ambiguous", False) for o in run["orders"]),
                          "gross": sum(o["gross"] or 0 for o in run["orders"]),
                          "fees": sum(o["fees"] for o in run["orders"]),
                          "funding": sum(o.get("funding", 0) for o in run["orders"]),
                          "funding_ambiguous": sum(o.get("funding_ambiguous", False) for o in run["orders"]),
                          "net": sum((o["gross"] or 0) - o["fees"] + o.get("funding", 0) for o in run["orders"])}
                         for setting, run in zip(settings, item["runs"])]} for item in catalog]
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
