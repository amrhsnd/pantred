# Pantred Project History

This is the human-readable history of the project. Git is the authority for
committed changes; entries marked "working tree" have not yet been committed.

## 15 May 2026: Initial market-data prototype

Commits: a0be511 (initial), 51d476b (Yahoo collection), 8b8eb53 (README),
ef178e7 (requirements).

The project began as "The Trading Helping Panel": an experiment in finding
market trends with AI. A small Python script fetched daily AAPL data through
yfinance and printed the first rows. There was no dashboard, persistent market
database or trading engine.

## 5 June 2026: Data collection and dashboard basics

Commit: 004e6dc, "dashboard basics", on branch data-collector.

The intended research direction became chart-image trend detection, with
Heikin Ashi candles. The collector gained multiple symbols/timeframes, date or
period selection, CSV exports, a request manifest and optional Heikin Ashi
columns. A local browser dashboard added collection controls, CSV previews and
Yahoo symbol search. Unit tests and generated-file exclusions were added.

The data-collector branch was pushed to GitHub on 6 June. This was a branch push,
not a merge into main. Subsequent Hyperliquid work is described below.

## 23 September 2026: Paper-trading direction and Hyperliquid

Committed in 33a1757, "Add Hyperliquid market recorder and local monitor".

The target became a future perpetual-futures trading bot, beginning with paper
trading and an approximately $300 virtual account. Hyperliquid was selected as
the initial exchange. Paid data subscriptions are outside the initial budget.
The immediate scope is reliable market collection and monitoring; a strategy,
simulated fills and real trading have not been implemented.

The Hyperliquid collector adds active-market discovery, candle backfills,
WebSocket trades, book snapshots and perpetual asset context. SQLite stores
these records locally. It includes reconnects, application heartbeats,
deduplication, coverage warnings, mainnet/testnet separation and CSV export.
A short mainnet verification recorded candles, trades and context/book data;
this verified connectivity, not trading performance.

Economic context must eventually include international economies, not only
the United States. Candidate sources include central banks, national statistics
agencies, ECB/Eurostat, IMF/OECD and FRED. Social research was narrowed toward
mention frequencies and attention bursts. Neither economic adapters nor X
collection are implemented; free X access has not been established.

## 23 September 2026: A visible market monitor and usage guide

Committed in 33a1757, "Add Hyperliquid market recorder and local monitor".

The command-line-only Hyperliquid workflow was difficult to use alongside the
older Yahoo dashboard. Running main.py without arguments now starts the local
Hyperliquid monitor. The browser can start/stop a default BTC/ETH/SOL recording,
show recorded candles and Heikin Ashi views, display market context, order books
and trades, and distinguish a running recorder from stale observations.

The Yahoo collector remains at /yahoo. Documentation is available in docs/ and
from the dashboard navigation. These pages describe current behavior and limits.

## 20–21 October 2026: First long VM recording test

A 25-hour BTC/ETH/SOL recording was launched on an AWS VM in Stockholm, using
one-minute candles and a one-hour initial candle backfill. A consistent local
snapshot taken after 24 hours 33 minutes passed SQLite integrity and complete
minute-slot checks. It contains 547,671 trades and 307,754 observations, with
eight successful reconnects after WebSocket expiry and no recorded failure.

This is an interim result: the snapshot precedes the scheduled end, contains no
stopped event, and cannot establish trade/book completeness across reconnects.
The [VM test report](VM_RECORDING_TEST.md) records the measured coverage and
remaining limits. Reusable scripts support bounded recording, read-only health
checks, SQLite online snapshots, auditing and a fixed local snapshot dashboard.

## 23 November 2026: Binance historical spot candles

Historical candles can be downloaded on demand without continuously recording.
The standalone `scripts/fetch_binance.py` fetches Binance spot archives for
BTC/USDT at native 1m, 5m and 15m intervals, verifies published SHA-256 checksums
and complete UTC-day coverage, and saves decimal strings plus normalized
millisecond timestamps in CSVs with a source manifest. It uses only Python's
standard library and requires no API key. Existing download directories are
not overwritten; unavailable or incomplete archives fail explicitly.

The October 24–November 22 UTC download contains 43,200 one-minute, 8,640
five-minute and 2,880 fifteen-minute candles. All 90 archive checksums passed,
with no missing or duplicate candles. Every native 5m and 15m candle reconciled
against constituent 1m OHLC, volume and trade-count data (quote volumes within
the source decimal precision). All 26 unit tests passed, including six new
archive-integrity, timestamp, coverage and OHLCV tests.

These are Binance spot candles rather than Hyperliquid perpetuals. They do not
contain the intraminute trade sequence required by the existing tick replay
backtest. Daily archives are published the following day; a recent unavailable
archive may require retrying later. No trading or recorder workflow was changed.

## 23 November 2026: Market-selectable sharp-candle research report

`scripts/market_backtest.py` builds a self-contained report with a market-data
selector at the beginning. Binance BTC/USDT spot supports 1m, 5m and 15m signals;
the original Hyperliquid BTC perpetual recording remains available at 1m.
Each dataset retains the twelve degree/history combinations and shows its
own dates, currency, fees, charts and order ledger.

Binance uses standard 0.1% spot buy/sell fees without BNB discounts. Buy fees
reduce BTC received, and sell fees apply to net BTC proceeds. All Binance
signal intervals execute on the one-minute feed with a ten-minute entry
expiration. Intrabar uncertainty uses stop-first handling and defers an
unproven entry-minute target touch; affected orders are flagged. Results
represent independent 1,000-unit orders, not a funded account simulation.

All 37 unit tests passed. Generated Hyperliquid candles and every order in
all twelve runs matched the previous GitHub Pages payload exactly. Every
generated order was checked for activation/expiration boundaries and
gross-minus-fees reconciliation. Binance's 36 configurations were all net
negative under these assumptions; this differs from a tick-accurate replay.

## 23 November 2026: Binance perpetual futures fees and funding

The market selector now defaults to Binance BTCUSDT USDT-margined perpetual
futures, with 1m, 5m and 15m signal intervals and the existing twelve settings
per interval. Spot and Hyperliquid remain selectable, with their complete data
and replay results unchanged from the previous published report.

Futures data was downloaded for the same October 24–November 22 UTC window:
54,720 candles across 90 verified archives, plus all 90 historical funding
settlements with their associated mark prices. Native 5m and 15m OHLCV and
trade counts reconciled against their constituent one-minute futures candles.

Futures fees use 0.02% maker / 0.05% taker assumptions without BNB discounts.
Immediately marketable entries at activation and stop exits use taker fees;
resting entries and targets use maker fees. Position BTC size stays constant.
Funding is a separate signed cash flow using settlement mark price and the
historical rate. Uncertain entry/exit-minute funding includes possible charges
and withholds uncertain credits, with affected orders flagged. This remains a
conservative candle replay of independent 1,000-USDT orders, without leverage,
capital limits or margin/liquidation simulation.

All 48 unit tests passed, including maker/taker classification, signed funding,
funding boundaries, ambiguity, coverage and fee accounting. Generated order
activation/expiry boundaries and gross-minus-fees-plus-funding reconciliation
were checked throughout. The default 1m/68%/30-bar run returned −723.11 USDT
after fees and funding; no futures configuration had positive net results,
and some sparse 15m settings had no fills.

## 23 November 2026: Strategy comparison across markets

The report adds a top-of-page comparison heatmap for all 84 combinations of
market/timeframe and strategy settings. Nineteen selectable metrics cover
profitability, average closed-trade results, fees, funding and order/outcome
counts. Each column ranks within its own market/timeframe; the underlying
sample dates, currencies and execution methods remain visible. Selecting a
cell opens its strategy and orders. A separate expanded table exposes all
metrics for the selected dataset.

Settings without closed trades are displayed but not ranked; unavailable
funding and undefined profit factors remain distinct from observed zeroes.
Equal values share ranks. Cost and ambiguity metrics rank lower values first;
activity counts are explicitly distinguished from profitability.

Six new JavaScript tests cover economic reconciliation, denominators, missing
values, no-trade settings, ties and profit-factor boundaries. The existing
48 Python tests passed. All 84 comparison summaries were checked against
the source orders, and the complete backtest payload remained unchanged.

## 23 November 2026: No-history three-candle strategy

The `no_history` branch replaces the lookback classifier with a rule based only
on the last three completed candles. Candle length includes wicks (`high − low`).
Candle 2 must account for strictly more than 50%, 60% or 70% of their summed
ranges, and its body must cover strictly more than 80% of its own range.
Equality does not qualify. No historical warmup or candle-color filters apply.

The buy limit is close 3, stop loss is low 1, and take profit is high 2; only
strictly ordered levels qualify. Activation follows candle 3's close. The
existing ten-minute unfilled-order expiry, conservative execution, independent
1,000-unit notional, fee and historical funding models are retained.

Both exporters use `--sharp-threshold` (default `50 60 70`). The combined report
retains all seven datasets, nineteen metrics, charts and ledger, with a single
threshold selector and three comparison rows. The standalone Hyperliquid
export uses the same signal rules. The branch report is prepared for
`/pantred/no_history/` alongside the main report on the existing `gh-pages`
branch, whose root report is preserved.

All 56 Python tests and six JavaScript tests passed. Tests cover strict range
and body boundaries, independence from earlier candles, both sharp colors,
third-candle colors/dojis, window/gap boundaries and exact order levels. All
2,750 generated orders across 21 runs were audited for signal/level validity,
threshold subsets, activation/expiry bounds and P&L reconciliation. Both HTML
exports passed JavaScript syntax checks; browser preview confirmed threshold
and timeframe changes update the metrics and charts.

For the existing October 24–November 22 Binance futures 1m sample, net results
including modeled fees/funding are −464.62, −173.99 and −79.70 USDT for 50%,
60% and 70%, respectively. These are independent-order research results,
not account returns. The 15m/60% result is +1.78 USDT from only two closed
trades; 15m/70% produces no orders.

## Current boundaries

The standalone sharp-candle research reports now include an order/fill replay;
they are separate from the collector and do not implement a paper-trading
account or live execution.

- Available: collection, local persistence, monitoring, history export.
- Not available in the collector: a paper-trading account, live strategy or
  order execution, international economic feeds or social-platform feeds.
- Live views require the recording process and internet access. Saved history
  remains visible when recording stops.
- Heikin Ashi prices are derived values, not prices at which orders can execute.

## Maintaining this history

After each meaningful milestone, add the decision, changed behavior, remaining
limits and verification performed. Replace working-tree labels with actual
commit IDs after commits are made. Do not describe planned features as shipped.
