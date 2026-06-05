# pantred: The Trading Helping Panel

Pantred is an early trading research project. The goal is to collect market
data, turn charts into image inputs, and later detect trends from chart images.

## Current Focus

The current codebase contains the first data collection layer:

- fetch historical OHLCV market data from Yahoo Finance
- collect multiple symbols and timeframes in one command
- save local CSV files under `data/raw/`
- write a `manifest.json` for each collection run
- optionally add Heikin Ashi candle columns for later chart generation

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Usage

Open the local dashboard:

```bash
python3 dashboard.py
```

Then visit `http://127.0.0.1:8501`.

Collect daily AAPL and MSFT bars between two dates:

```bash
python3 main.py --symbols AAPL MSFT --timeframes 1d --start 2026-01-01 --end 2026-05-15
```

Collect multiple intervals and include Heikin Ashi columns:

```bash
python3 main.py --symbols AAPL BTC-USD --timeframes 1d 1h --period 6mo --heikin-ashi
```

Outputs are written like this:

```text
data/raw/
  AAPL/
    1d.csv
    1h.csv
  BTC-USD/
    1d.csv
    1h.csv
  manifest.json
```

## Notes

Yahoo Finance has interval limitations. Intraday intervals such as `1m`, `5m`,
`15m`, and `1h` usually only work for recent periods.
