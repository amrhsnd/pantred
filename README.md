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

## Binance historical candles

Download BTC/USDT USDT-margined perpetual futures candles and historical
funding settlements for October 24–November 22, 2026:

```bash
python3 scripts/fetch_binance.py --market usdm --start 2026-10-24 --end 2026-11-23
```

Futures CSVs and the funding file/manifest are saved separately under
`data/raw/binance-futures/BTCUSDT/2026-10-24_2026-11-23/`. The funding API supplies
each settlement's actual rate, timestamp and mark price. For this BTCUSDT
window, all 90 eight-hour settlements are required. Archive checksums, native
timestamps and funding coverage are validated before saving.

### Spot candles

Download BTC/USDT candles for the last 30 complete UTC days at native 1m, 5m
and 15m intervals without running a recorder or using an API key:

```bash
python3 scripts/fetch_binance.py
```

For the fixed October 24–November 22, 2026 window:

```bash
python3 scripts/fetch_binance.py --start 2026-10-24 --end 2026-11-23
```

The end date is exclusive. Outputs are separate CSVs and a source/checksum
manifest under `data/raw/binance/BTCUSDT/2026-10-24_2026-11-23/`. Existing
download directories are never overwritten; use `--output-dir` for a new copy.
Prices are USDT, volumes are BTC and timestamps are UTC milliseconds, with an
additional readable UTC datetime. These are **spot** candles, separate from
Hyperliquid perpetuals. The script checks archive SHA-256 checksums, OHLCV values
and every expected timestamp before saving. Incomplete downloads fail explicitly.
Binance publishes daily archives the following day, so the latest complete day
may need a later retry. See [Binance public data](https://github.com/binance/binance-public-data).

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

## Bitcoin one-minute sharp candle backtest

The [GitHub Pages backtest](https://amrhsnd.github.io/pantred/) starts with a
**Market data** selector: Binance BTC/USDT perpetual futures (default), Binance
spot, or the original Hyperliquid BTC perpetual recording. Both Binance markets
offer 1m, 5m and 15m signal intervals. Each dataset
has the existing twelve sharp-degree/history settings, its own coverage dates,
fees, order ledger and interactive candlestick charts.

Build the combined report after downloading both Binance futures and spot data:

```bash
python3 scripts/market_backtest.py
```

This writes `data/processed/market-backtest.html` and a numerical
`market-backtest.summary.json`. Use `--futures-dir`, `--binance-dir` and
`--database` for other complete futures/spot exports or Hyperliquid recordings.
The generated HTML is
self-contained and is published as `index.html` on the `gh-pages` branch.

Binance futures use **0.02% maker / 0.05% taker** fee assumptions without BNB
discounts. Resting entries and targets use maker fees; an immediately marketable
entry at activation and stop exits use taker fees. Fees apply to executed
notional, with constant BTC position size. The model retains independent
1,000-USDT notional orders, with no leverage, capital or margin/liquidation model.
Stops use contract prices, rather than mark-price triggers.

Historical futures funding is included separately from trading fees, using
`−BTC size × settlement mark price × funding rate` for a long position. Positive
cash flows are receipts; negative cash flows are payments. Minute candles
cannot determine whether a fill or exit preceded a settlement in that same
minute. Such cases are flagged: possible charges are included, while uncertain
credits are withheld. Funding is included through the data end for positions
still open. Win/loss classification and net P&L include modeled funding.

Binance spot uses the standard fee of **0.1% on buys and sells**, without a BNB
discount or VIP tier. The buy fee reduces BTC received; the sell fee applies
to proceeds from the remaining BTC. Closed-order buy fees are valued at the
exit price so gross minus fees reconciles exactly with net proceeds. The
fee schedule was checked on November 23, 2026; account-specific rates and
historical promotions are not reconstructed.

All Binance signal intervals execute against one-minute candles. Stop wins
if both exit levels occur within a minute. On the entry minute, a target is
accepted only when the open/close establishes that it occurred after entry;
otherwise the target touch is deferred. The ledger flags intrabar ambiguity.
Stops that gap through the stop level exit at the minute's opening price.
Unfilled orders expire after **10 minutes**, including on 5m and 15m signals.
Initial history bars provide warmup, and no pre-window data is invented.

Binance candle-based fills and the shorter Hyperliquid tick replay are separate
samples. They do not provide a controlled exchange comparison. Each order
uses independent 1,000-unit quote notional without account capital limits;
extra slippage, liquidity and exchange size rounding are excluded. Funding is
included for Binance futures and remains excluded from the original Hyperliquid
replay. Open P&L is excluded while incurred entry fees and futures funding are
included.

### Original Hyperliquid report

From the repository root, replay the October VM snapshot and open its interactive order ledger and candlestick chart:

```bash
python3 scripts/sharp_backtest.py --open
```

Send `data/processed/BTC-1m-backtest.html` to share the result. The recipient can open it in a browser offline. The exporter uses Python's standard library. Use `--database PATH` for another Pantred SQLite recording with BTC trade prints and one-minute candles. The replay covers whole minutes within the recorded trade window. Use `--help` for the sharpness, lookback, expiration and output options.

The default BTC report compares sharp degrees 68%, 100%, 168% and 250% over histories of 30, 20 and 10 candles. Choose either parameter above the chart. For a custom grid, pass multiple integers to each flag, e.g. `--sharp-degree 68 100 --sharp-history 30 20`.

BTC replay fees use the Hyperliquid base perpetual tier. Resting entries and target exits assume a 0.015% maker fee, and stop exits assume a 0.045% taker fee. Each fee uses its executed notional. Win rate and profit factor use after-fee closed trades. Funding and additional slippage are excluded.

The buy limit uses candle 3’s low and the stop uses candle 1’s low. Matching candle 2 and 3 colors target candle 3’s high. Otherwise the target equals the entry and the setup is skipped.
