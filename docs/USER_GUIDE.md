# Using Pantred

## Start the app

From the project folder, run:

    python3 main.py

Open the URL printed in the terminal, normally http://127.0.0.1:8501.
Keep that terminal running. If the port is already occupied, the app picks the
next available port and prints it. You can also use python3 dashboard.py or
python3 main.py dashboard --port 8502.

For first-time installation, use Python 3.11 or newer:

    python3 -m venv .venv
    source .venv/bin/activate
    python3 -m pip install -r requirements.txt
    python3 main.py

Use the same Python environment for installation and starting the app.

## See Hyperliquid data

1. Open the Hyperliquid monitor and click Start recording.
2. Wait for the initial history to load. The recorder collects BTC, ETH and SOL
   perpetuals, with 1-minute, 5-minute, 15-minute and 1-hour candles.
3. Choose a market, timeframe and chart window. Standard and Heikin Ashi modes
   are available. Pan or scroll over the chart to inspect prices.
4. Read the mark/oracle price, funding rate, open interest, daily volume and
   spread above the chart. The book and recent trades appear below it.
5. Use Stop recording to pause collection. Saved data stays available.

The page reads saved data every two seconds. A running process is not proof of
a fresh feed: inspect the context/book age and activity list. Initial history
loads before live observations arrive. The newest candle may still be forming.
Heikin Ashi calculations start at the first candle of the displayed window;
changing the window can affect the initial smoothed values.

Open interest and trade/book size are in units of the selected base asset.
Notional volume is dollar-denominated. Funding is the provider's current rate
shown as a percentage, not an annualized yield or your account's funding payment.
Displayed numbers are rounded; the database retains provider price strings.

## What the app does today

This is a read-only market monitor. It does not connect a wallet, place orders,
run a strategy or calculate paper-trading profits. No deposit is necessary.
"Mainnet" means the source is the real market; it does not mean real trading.

The Start recording button launches a local recorder owned by this dashboard.
Stopping the dashboard with Ctrl+C also stops that recorder. Closing only the
browser tab does not stop the server or recorder. Use Stop recording first
when you are finished. A recorder launched separately in a terminal must be
stopped in that terminal; the dashboard does not own it.

## Where data is saved

Hyperliquid database: data/hyperliquid/mainnet.sqlite3
Dashboard recorder log: data/hyperliquid/recorder.log
Yahoo CSV files: data/raw/

The paths above are inside the project folder for the browser-managed recorder.
CLI commands use the working directory unless --database supplies another path.
Recordings can grow large, especially order-book snapshots. There is no automatic
disk cleanup. SQLite files and downloaded datasets are excluded from Git.

To export Hyperliquid candles from the project directory:

    python3 main.py hyperliquid export --symbol BTC --timeframe 1m --output data/processed/BTC-1m.csv --heikin-ashi

For collector status:

    python3 main.py hyperliquid status

To discover other perpetuals:

    python3 main.py hyperliquid markets

The browser-managed watchlist currently records BTC, ETH and SOL. Custom
recording watchlists are available through the CLI documented in README.md.
Do not run a second recorder against the same database at the same time.

## Yahoo and other markets

Select Yahoo collector in the top navigation. This is the earlier CSV workflow:
choose symbols/timeframe/period and collect a snapshot. It does not feed the
Hyperliquid live monitor. International economic series and social mention
frequencies remain planned work.

## Troubleshooting

- Blank charts: click Start recording and allow the initial backfill to finish.
  Check Collector activity and recorder.log if data never appears.
- Old prices: check timestamps. Restart recording; an offline period can leave
  gaps in trades/books that cannot be recovered by this collector.
- Recorder error: inspect recorder.log for the provider or connection error.
- Page unavailable: restart main.py and use the exact printed URL.
- Missing Python module: install requirements with the same Python interpreter.
- Charts load without live internet once data has been saved; live collection
  still needs network access. The chart library is served locally.

Project decisions and milestones are documented in PROJECT_HISTORY.md.
