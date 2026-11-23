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
