# pantred: The Trading Helping Panel

## Three-candle FVG + ATR algorithm (`only3_withATR`)

[Open the published ATR report](https://amrhsnd.github.io/pantred/only3_withATR/).
This branch extends `no_history` with the following **inclusive** signal rules:

| Candle 2 / three-candle measurement | Required value |
| --- | --- |
| Body / range | ≥ 80% |
| Upper wick / range | ≤ 10% |
| Lower wick / range | ≤ 10% |
| FVG size / body 2 | ≥ 50% |
| Range 2 / ATR(x) at candle 2 | ≥ 1.5 |

Range is high − low, body is |close − open|, upper wick is
high − max(open, close), and lower wick is min(open, close) − low.
The FVG is the positive gap between candle 1 and candle 3's wicks:
low 3 − high 1 for a bullish gap, or low 1 − high 3 for a bearish gap.
Touching or overlapping wicks give no FVG. The earlier range-share threshold
is replaced by these rules.

The report compares **ATR periods 10, 15, 20, 30 and 50** across the same
Binance spot/futures 1m, 5m and 15m datasets and Hyperliquid 1m recording.
ATR uses Wilder's smoothing on the selected market and timeframe. True range
is max(high − low, |high − previous close|, |low − previous close|).
The first ATR is the mean of x true ranges; later values are
(previous ATR × (x − 1) + current TR) / x. The first TR in a contiguous
segment is high − low. ATR includes candle 2, excludes candle 3 and future
candles, and needs x candles through candle 2 before a signal is eligible.
Missing candles restart the warmup. Only ATR uses candles before the pattern.

Existing long order levels remain **entry = close 3, stop = low 1,
target = high 2**, requiring stop < entry < target. There is no color filter;
bearish FVG candidates have invalid long levels and are counted as invalid.
Execution, independent 1,000-unit notional, 10-minute unfilled-order expiry,
trading fees and funding treatment match the previous report.

Generate the self-contained HTML and summary JSON using the datasets described
below:

```bash
python3 scripts/only3_atr.py
# Optional subset of the supported ATR periods:
python3 scripts/only3_atr.py --atr-period 10 20 50
```

Outputs are `data/processed/only3-withATR-backtest.html` and
`only3-withATR-backtest.summary.json`. The shared `--futures-dir`,
`--binance-dir`, `--database`, `--output` and `--order-expiration` options
are supported. Publish the HTML as `only3_withATR/index.html` and the summary
as `only3_withATR/summary.json` on the existing `gh-pages` branch.
The market, timeframe and ATR selectors, comparison heatmap, order ledger and
charts work offline. Each order shows its body, wick, FVG and ATR ratios.
The prior main report and `/no_history/` report remain available.

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

## No-history sharp candle backtest

This branch implements the three-candle strategy at
[its own GitHub Pages address](https://amrhsnd.github.io/pantred/no_history/).
The [main strategy report](https://amrhsnd.github.io/pantred/) remains separate.

For the last three completed candles, let `R = high − low` and
`B = |close − open|`. Candle 2 is sharp when **both** conditions hold:

- `100 × R2 > x × (R1 + R2 + R3)`, for **x = 50, 60, 70**.
- `100 × B2 > 80 × R2` (body strictly greater than 80% of its range).

Length includes wicks. Both comparisons are strict; equality does not qualify.
Only these three candles determine a signal. No historical warmup, additional
sharpness checks on candles 1/3, or candle-color filters apply. A zero-range
middle candle cannot be sharp.

Buy limit = **close 3**, stop loss = **low 1**, take profit = **high 2**.
Only `stop < entry < target` setups qualify. Orders activate after candle 3
closes; unfilled orders expire after ten minutes, including for 5m/15m signals.
The existing limit-fill, stop-first, trading-fee and funding models are retained.

The report has the same market/timeframe selectors, nineteen comparison metrics,
order ledger and candlestick charts as the main report. The threshold selector
replaces the former degree/history selectors. It compares all three thresholds
across seven datasets: Binance BTC/USDT perpetual futures and spot at 1m, 5m
and 15m, plus the October Hyperliquid BTC perpetual recording at 1m.

Build the report after downloading both Binance futures and spot data:

```bash
python3 scripts/market_backtest.py
# Optional custom thresholds:
python3 scripts/market_backtest.py --sharp-threshold 50 60 70
```

This writes `data/processed/no-history-backtest.html` and
`no-history-backtest.summary.json`. Use `--futures-dir`, `--binance-dir` and
`--database` for other complete exports or recordings. The generated HTML is
self-contained and is published as `no_history/index.html` on the `gh-pages`
branch; its root `index.html` serves the main strategy.

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
The first signal can use the first three complete in-window candles; no pre-window data is needed.

Binance candle-based fills and the shorter Hyperliquid tick replay are separate
samples. They do not provide a controlled exchange comparison. Each order
uses independent 1,000-unit quote notional without account capital limits;
extra slippage, liquidity and exchange size rounding are excluded. Funding is
included for Binance futures and remains excluded from the original Hyperliquid
replay. Open P&L is excluded while incurred entry fees and futures funding are
included.

### Hyperliquid-only no-history report

From the repository root, replay the October VM snapshot and open its interactive order ledger and candlestick chart:

```bash
python3 scripts/sharp_backtest.py --open
```

Send `data/processed/BTC-1m-no-history.html` to share the result. The recipient can open it in a browser offline. The exporter uses Python's standard library. Use `--database PATH` for another Pantred SQLite recording with BTC trade prints and one-minute candles. The replay covers whole minutes within the recorded trade window. Use `--help` for the threshold, expiration and output options.

The default BTC report compares range thresholds 50%, 60% and 70%, with the same strict body > 80% rule. For a custom set, use `--sharp-threshold 50 60 70`.

BTC replay fees use the Hyperliquid base perpetual tier. Resting entries and target exits assume a 0.015% maker fee, and stop exits assume a 0.045% taker fee. Each fee uses its executed notional. Win rate and profit factor use after-fee closed trades. Funding and additional slippage are excluded.

The buy limit uses candle 3’s low and the stop uses candle 1’s low. Matching candle 2 and 3 colors target candle 3’s high. Otherwise the target equals the entry and the setup is skipped.
