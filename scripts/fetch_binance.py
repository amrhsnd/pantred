"""Download Binance spot or USD-M perpetual candles; no recorder or API key."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = "https://data.binance.vision/data/spot/daily/klines"
FUTURES_ARCHIVES = "https://data.binance.vision/data/futures/um/daily/klines"
FUNDING_API = "https://fapi.binance.com/fapi/v1/fundingRate"
INTERVALS = {"1m": 60_000, "5m": 300_000, "15m": 900_000}
FIELDS = [
    "symbol", "timeframe", "datetime", "open_time_ms", "open", "high", "low",
    "close", "volume", "close_time_ms", "quote_volume", "trade_count",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]


def get_bytes(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Pantred/1.0"}), timeout=30) as response:
                return response.read()
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(min(float(error.headers.get("Retry-After", 2 ** attempt)), 60))
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def milliseconds(value):
    """Spot archive timestamps changed from milliseconds to microseconds in 2025."""
    timestamp = int(value)
    return timestamp // 1000 if timestamp >= 100_000_000_000_000 else timestamp


def parse_archive(payload, checksum, filename, symbol, interval, day):
    actual_hash = hashlib.sha256(payload).hexdigest()
    if checksum.decode("ascii").split() != [actual_hash, filename]:
        raise ValueError(f"Checksum mismatch: {filename}")
    step = INTERVALS[interval]
    day_ms = int(day.timestamp()) * 1000
    records = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        expected_member = filename.removesuffix(".zip") + ".csv"
        if archive.namelist() != [expected_member]:
            raise ValueError(f"Unexpected archive contents: {filename}")
        with archive.open(expected_member) as member:
            for number, row in enumerate(csv.reader(io.TextIOWrapper(member, encoding="utf-8"))):
                if number == 0 and row == ["open_time", "open", "high", "low", "close", "volume",
                                           "close_time", "quote_volume", "count", "taker_buy_volume",
                                           "taker_buy_quote_volume", "ignore"]:
                    continue
                if len(row) != 12:
                    raise ValueError(f"Unexpected candle schema: {filename}")
                opened, closed = milliseconds(row[0]), milliseconds(row[6])
                if opened != day_ms + len(records) * step or closed != opened + step - 1:
                    raise ValueError(f"Missing, duplicate or misaligned candle: {filename}")
                opening, high, low, close = map(Decimal, row[1:5])
                volumes = [Decimal(row[index]) for index in (5, 7, 9, 10)]
                if not all(value.is_finite() for value in [opening, high, low, close, *volumes]):
                    raise ValueError(f"Non-finite candle value: {filename}")
                if not (0 < low <= min(opening, close) <= max(opening, close) <= high):
                    raise ValueError(f"Invalid OHLC prices: {filename}")
                if min(volumes) < 0 or int(row[8]) < 0 or volumes[2] > volumes[0] or volumes[3] > volumes[1]:
                    raise ValueError(f"Invalid volumes or trade count: {filename}")
                records.append([
                    symbol, interval,
                    datetime.fromtimestamp(opened / 1000, timezone.utc).isoformat(),
                    opened, *row[1:6], closed, row[7], int(row[8]), row[9], row[10],
                ])
    expected = 86_400_000 // step
    if len(records) != expected:
        raise ValueError(f"Incomplete day {filename}: {len(records)}/{expected} candles")
    return records, actual_hash


def fetch_interval(symbol, interval, start, end, market="spot"):
    records, sources = [], []
    day = start
    while day < end:
        filename = f"{symbol}-{interval}-{day:%Y-%m-%d}.zip"
        base = FUTURES_ARCHIVES if market == "usdm" else ARCHIVES
        url = f"{base}/{symbol}/{interval}/{filename}"
        try:
            payload = get_bytes(url)
            checksum = get_bytes(url + ".CHECKSUM")
        except HTTPError as error:
            raise RuntimeError(
                f"Archive unavailable ({error.code}): {url}. "
                "Daily archives are published the following day; retry later if recent."
            ) from error
        daily, sha256 = parse_archive(payload, checksum, filename, symbol, interval, day)
        records.extend(daily)
        sources.append({"url": url, "sha256": sha256, "rows": len(daily)})
        day += timedelta(days=1)
    print(f"{symbol} {interval}: verified {len(records):,} candles", flush=True)
    return interval, records, sources


def utc_date(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def validate_funding(rows, symbol, start_ms, end_ms):
    times = [int(row["fundingTime"]) for row in rows]
    if not rows or times != sorted(set(times)):
        raise ValueError("Missing, duplicate or unordered funding history.")
    for row, timestamp in zip(rows, times):
        rate, mark = Decimal(row["fundingRate"]), Decimal(row["markPrice"])
        if (row["symbol"] != symbol or not start_ms <= timestamp < end_ms
                or not rate.is_finite() or not mark.is_finite() or mark <= 0):
            raise ValueError("Invalid funding record or missing settlement mark price.")
    # BTCUSDT's observed eight-hour schedule: reject missing settlements explicitly.
    if symbol == "BTCUSDT":
        period = 8 * 3_600_000
        expected = list(range(start_ms // period, end_ms // period))
        if [timestamp // period for timestamp in times] != expected:
            raise ValueError("BTCUSDT funding does not cover every eight-hour settlement; review interval changes.")
        if any(timestamp % period >= MINUTE_MS for timestamp in times):
            raise ValueError("Unexpected BTCUSDT funding settlement timing.")


MINUTE_MS = 60_000


def fetch_funding(symbol, start, end):
    start_ms, end_ms = int(start.timestamp()) * 1000, int(end.timestamp()) * 1000
    cursor, records, sources = start_ms, [], []
    while cursor < end_ms:
        url = FUNDING_API + "?" + urlencode(dict(symbol=symbol, startTime=cursor, endTime=end_ms - 1, limit=1000))
        payload = get_bytes(url)
        batch = json.loads(payload)
        if not isinstance(batch, list):
            raise ValueError("Funding API returned an error rather than settlement records.")
        sources.append({"url": url, "response_sha256": hashlib.sha256(payload).hexdigest()})
        if not batch:
            break
        records.extend(batch)
        next_cursor = int(batch[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise ValueError("Funding API pagination did not advance.")
        cursor = next_cursor
        if len(batch) < 1000:
            break
    validate_funding(records, symbol, start_ms, end_ms)
    print(f"{symbol}: verified {len(records)} historical funding settlements", flush=True)
    return records, sources


def main(argv=None):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--market", choices=["spot", "usdm"], default="spot",
                        help="Spot or USDT-margined perpetual futures (includes funding history).")
    parser.add_argument("--timeframes", nargs="+", choices=INTERVALS, default=list(INTERVALS))
    parser.add_argument("--start", type=utc_date, default=today - timedelta(days=30))
    parser.add_argument("--end", type=utc_date, default=today, help="Exclusive UTC date (YYYY-MM-DD).")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    symbol = args.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,30}", symbol):
        parser.error("Symbol must contain 2–30 ASCII letters or digits, for example BTCUSDT.")
    if not args.start < args.end <= today:
        parser.error("Use start < end <= today's UTC date; only complete days can be downloaded.")
    intervals = list(dict.fromkeys(args.timeframes))
    output_dir = args.output_dir or ROOT / ("data/raw/binance-futures" if args.market == "usdm" else "data/raw/binance")
    destination = output_dir / symbol / f"{args.start:%Y-%m-%d}_{args.end:%Y-%m-%d}"
    if destination.exists():
        parser.error(f"Output already exists: {destination}. Choose another --output-dir.")
    print(f"Binance {args.market.upper()} {symbol}: {args.start.isoformat()} to {args.end.isoformat()} (exclusive)", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(
                lambda interval: fetch_interval(symbol, interval, args.start, args.end, args.market), intervals
            ))
        funding, funding_sources = fetch_funding(symbol, args.start, args.end) if args.market == "usdm" else (None, None)
        manifest = {
            "source": "Binance public data", "market": args.market, "symbol": symbol,
            "start_inclusive": args.start.isoformat(), "end_exclusive": args.end.isoformat(),
            "timezone": "UTC", "generated_at": datetime.now(timezone.utc).isoformat(),
            "documentation": "https://github.com/binance/binance-public-data",
            "timestamp_unit": "milliseconds", "price_unit": "quote asset (USDT for BTCUSDT)",
            "volume_unit": "base asset (BTC for BTCUSDT)",
            "validation": "SHA-256 archive checksums; complete contiguous candles; OHLCV constraints",
            "results": [],
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Stage the entire download before exposing the final directory.
        with tempfile.TemporaryDirectory(prefix=".binance-", dir=destination.parent) as temporary:
            staging = Path(temporary) / destination.name
            staging.mkdir()
            for interval, rows, sources in results:
                path = staging / f"{interval}.csv"
                with path.open("w", newline="", encoding="utf-8") as output:
                    writer = csv.writer(output)
                    writer.writerow(FIELDS)
                    writer.writerows(rows)
                manifest["results"].append({
                    "timeframe": interval, "rows": len(rows), "file": path.name,
                    "first_open_ms": rows[0][3], "last_open_ms": rows[-1][3],
                    "missing_candles": 0, "duplicate_candles": 0,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "archives": sources,
                })
            if funding is not None:
                path = staging / "funding.json"
                path.write_text(json.dumps(funding, indent=2) + "\n", encoding="utf-8")
                manifest["funding"] = {"file": path.name, "rows": len(funding),
                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                       "sources": funding_sources, "includes_settlement_mark_prices": True}
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            staging.rename(destination)
        print(f"Saved: {destination.resolve()}", flush=True)
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Download failed: {error}\n")


if __name__ == "__main__":
    main()
