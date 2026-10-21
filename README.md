# pantred: The Trading Helping Panel

Pantred is a market-data research project being developed toward paper trading
of perpetual futures. Chart-image experiments and Heikin Ashi charts remain
part of the research direction. There is no order execution or wallet access.

## Start Here

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

Open the printed URL (normally http://127.0.0.1:8501), then click **Start recording**.
The default watchlist is BTC, ETH and SOL perpetuals. Select a market/timeframe
to see candles, market context, the order book and recent trades. Use **Stop
recording** when finished; the saved history remains visible.

- [User guide](docs/USER_GUIDE.md): startup, controls, files and troubleshooting.
- [Project history](docs/PROJECT_HISTORY.md): milestones, decisions and shipped/planned scope.
- [VM recording test](docs/VM_RECORDING_TEST.md): 24-hour snapshot results, repeatable VM recording, and fixed local viewing.

The app currently collects and monitors data. The paper-trading engine is not
implemented yet. Yahoo collection remains available at `/yahoo`.

## Hyperliquid Perpetual Collector

Python 3.11+ is required. Install `requirements.txt` first. Public mainnet data
is the default and requires no API key or funded account.

List active instruments directly from Hyperliquid:

```bash
python3 main.py hyperliquid markets
```

Record BTC, ETH and SOL continuously (Ctrl+C flushes and stops):

```bash
python3 main.py hyperliquid record --symbols BTC ETH SOL --timeframes 1m
```

This first loads the last 24 hours of candles, then subscribes to public trades,
order-book snapshots, candle updates, and asset context (mark/oracle prices,
funding rate, open interest and daily notional volume). `--lookback-hours` changes
the initial history window. `--duration 60` provides a bounded recording run;
setup/backfill counts toward the duration, but an in-flight REST request may
finish after it. A recording process must remain running to collect data.

Fetch history without starting a stream:

```bash
python3 main.py hyperliquid backfill --symbols BTC ETH --timeframes 1m 5m --lookback-hours 48
python3 main.py hyperliquid backfill --symbols BTC --timeframes 1h --start 2026-09-01 --end 2026-09-10
```

Dates without an offset are UTC, and the end is exclusive. Native intervals are
`1m 3m 5m 15m 30m 1h 2h 4h 8h 12h 1d 3d 1w 1M`; `1M` means a calendar month.
Only the latest 5,000 candles per interval are available from the snapshot API.
Requests outside retention may return partial or empty results; inspect the
coverage warnings. Raw trades are retained for future sub-minute aggregation;
5-second/15-second candle generation is not implemented yet.

Inspect recording counts, feed timestamps and recent lifecycle/coverage events:

```bash
python3 main.py hyperliquid status
```

Export stored candles, optionally including derived Heikin Ashi columns:

```bash
python3 main.py hyperliquid export --symbol BTC --timeframe 1m --output data/processed/BTC-1m.csv --heikin-ashi
```

Exports exclude candles whose close time has not passed. `received_ms` records
when each candle was last observed: a candle whose close time passed while the
recorder was offline may still need a fresh backfill to obtain its final values.
Heikin Ashi values are synthetic and must not be used as execution prices.

### Storage and Recovery

SQLite is a local first implementation, with WAL enabled for concurrent readers.
The default path is `data/hyperliquid/mainnet.sqlite3`; `--database PATH` overrides
it. Run only one recorder per database. The stored tables are:

- `candles`: latest OHLCV per symbol/interval/open timestamp, plus original payload.
- `trades`: original decimal price/size strings, exchange/receipt times and trade ID.
- `observations`: order books, asset contexts and discovered market metadata as JSON.
- `recorder_events`: connections, disconnections, backfills, warnings and stops.

All timestamps are UTC Unix milliseconds. Asset-context messages do not include
an exchange timestamp, so their `event_ms` stays NULL; `received_ms` is local time.
Prices are stored as text to avoid losing decimal precision. Trade identity uses
symbol, exchange timestamp and trade ID. Candles update in place; historical
candle revisions are not an append-only replay of what was known in the past.

Writes commit at least once per second while streaming and on graceful shutdown.
A hard process termination may lose the latest uncommitted batch. The recorder
reconnects with backoff, subscribes again, and refreshes candles from the last
stored candle. It logs possible gaps in trades/books; those missing events are
not reconstructed. A book snapshot is the published depth, not a complete order
event feed. Internal and leading gaps are checked for fixed-duration candles;
calendar-month coverage is not audited. Empty candles are never fabricated.

Books can consume substantial disk space. This version has no automatic archive
or pruning; use a small watchlist and monitor disk usage. `status` reports receipt
timestamps, not a guarantee that an old recording is currently live.

`--testnet` uses a separate default database and testnet feeds, whose prices and
liquidity must not be used to judge mainnet performance. Mixing networks in one
database is rejected. Optional HIP-3 markets can be discovered using
`markets --dex NAME`, then collected with `--dex NAME`; canonical names and their
case-sensitive dex prefixes are preserved.

The collector is available through the CLI and the default local monitor. The
browser-managed recorder uses BTC/ETH/SOL and 1m/5m/15m/1h candles. The separate
Yahoo dashboard remains at `/yahoo`.

### Planned Context Data

Economic context will cover international economies, not just the US. Candidate
adapters include ECB/Eurostat, national central banks/statistical agencies,
IMF/OECD and FRED. Geography, source, observation period, publication/receipt time
and revisions must remain separate. These adapters, X mention counts and the
paper-trading engine are not implemented in this step.

### Verification and API References

```bash
python3 -B -m unittest discover -s tests
```

- [Public info and candle API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- [Perpetual market metadata](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
- [Heartbeats](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/timeouts-and-heartbeats)

## Existing Yahoo Finance Collector

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
