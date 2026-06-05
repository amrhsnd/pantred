import argparse
import sys
from pathlib import Path

from data_collection import CollectionRequest, MarketDataCollector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect historical market data.")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Ticker symbols to collect, for example AAPL MSFT BTC-USD.",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1d"],
        help="Yahoo Finance intervals, for example 1d 1h 15m.",
    )
    parser.add_argument("--start", help="Start date, for example 2026-01-01.")
    parser.add_argument("--end", help="End date. Yahoo Finance treats it as exclusive.")
    parser.add_argument(
        "--period",
        help="Yahoo Finance period, for example 1mo, 6mo, 1y, 5y, or max.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Directory where CSV files and manifest.json will be written.",
    )
    parser.add_argument(
        "--heikin-ashi",
        action="store_true",
        help="Add Heikin Ashi OHLC columns to the exported data.",
    )
    return parser.parse_args()


def main() -> None:
    if len(sys.argv) == 1:
        print("Pantred data collector")
        print("Run the dashboard with: python3 dashboard.py")
        print("Or use the CLI, for example:")
        print("python3 main.py --symbols AAPL BTC-USD --timeframes 1d --period 6mo --heikin-ashi")
        return

    args = parse_args()
    request = CollectionRequest(
        symbols=args.symbols,
        timeframes=args.timeframes,
        start=args.start,
        end=args.end,
        period=args.period,
        output_dir=Path(args.output_dir),
        include_heikin_ashi=args.heikin_ashi,
    )

    results = MarketDataCollector().collect(request)
    for result in results:
        destination = result.output_path if result.output_path else "no file written"
        print(f"{result.symbol} {result.timeframe}: {result.rows} rows -> {destination}")


if __name__ == "__main__":
    main()
