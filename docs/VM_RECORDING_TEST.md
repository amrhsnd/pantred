# First VM recording test

The first long recording captured more than 24 hours of Hyperliquid mainnet
data for BTC, ETH and SOL. This report describes an **interim snapshot**, taken
before the planned 25-hour end. It does not claim a final 25-hour pass.

## Measured results

The tested collector commit was `33a17574d2e6e0790a98c177b277010eaadf8e97`.
It ran on Ubuntu 24.04, Python 3.12, on an AWS VM in Stockholm (`eu-north-1`),
with about 2 GiB RAM and a 30 GB root volume. The exact EC2 instance type was
not independently verified. The existing 20 unit tests passed on the VM.

| Measurement | Snapshot result |
| --- | --- |
| Recorder started (UTC) | 20 October 2026, 13:43:20 |
| First live connection (UTC) | 20 October 2026, 13:43:22 |
| Snapshot transaction (UTC) | 21 October 2026, 14:16:52 |
| Latest captured receipt (UTC) | 21 October 2026, 14:16:51.497 |
| Live window | 24.558 hours (about 24 hours 33 minutes) |
| SQLite `quick_check` | `ok` |
| Candles, including preload and boundary minutes | 4,599 |
| Trades | 547,671 |
| Observations, including three metadata records | 307,754 |
| Lifecycle events | 53 |
| Disconnects / recorded failures | 8 / 0 |
| Database size | 440,905,728 bytes |

For each of BTC, ETH and SOL, all **1,472 fully contained one-minute candle
slots** were present between 20 October 13:44 UTC and 21 October 14:16 UTC
(exclusive). There were no missing slots, internal gaps or off-grid timestamps.
The initial hour of backfill and partially covered boundary minutes are excluded
from this coverage count.

| Receipt stream | BTC maximum gap | ETH maximum gap | SOL maximum gap |
| --- | ---: | ---: | ---: |
| Asset context | 3.9 s | 3.9 s | 3.9 s |
| Order-book snapshots | 7.7 s | 7.8 s | 7.8 s |
| Trades | 16.0 s | 15.8 s | 23.8 s |

All eight disconnects reported WebSocket `Expired` closes. Each was followed
by a candle refresh and a new connection. Fresh receipts were present for every
expected stream at capture time. These timings describe recorded receipts;
quiet markets can also produce gaps between trades.

## Limits and operational findings

- No stopped event exists in this snapshot. The final shutdown, exit code and
  end-of-run audit remain unverified here.
- Candle backfill can conceal streaming interruptions. Complete minute slots
  do not prove final OHLCV values or complete trades/books during reconnects.
- Books are snapshots rather than a full order-event feed. Asset context has
  receipt timestamps but no exchange timestamp.
- The original health probe used the ordinary CLI `status`, which initializes
  `MarketStore` and can encounter `database is locked` against a live writer.
  The reusable health probe below opens SQLite in read-only mode instead.
- An unpinned online backup took about 12 minutes while writes continued. A
  pinned read transaction completed the copy in 2.6 seconds. `snapshot.py`
  uses that fixed transaction, a timeout, and a separate destination.

The local database, compressed download, logs and detailed audit remain under
ignored `data/hyperliquid/aws-run/`. Large recording files and credentials are
not part of the repository.

The packaged helpers were checked locally: the existing 20 tests passed, a
snapshot remained consistent while a separate WAL writer continued committing,
an existing output was protected from overwrite, and the fixed viewer loaded
all three markets with recording actions and polling disabled. The packaged
SQL audit reproduced the snapshot's measured window and candle coverage.

## Repeat the bounded VM test

On an Ubuntu VM, install Python with venv support, Git, tmux and SQLite. From
the checked-out repository, create `.venv` and install `requirements.txt`.
The scripts below are the reusable version of the original one-off launchers;
they have not yet been used for a second full VM run.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests
tmux new-session -d -s pantred-soak 'bash scripts/vm/run_soak.sh'
```

This records BTC/ETH/SOL, one-minute candles, a one-hour initial backfill and
a 90,000-second duration. It saves minute health samples, disk/memory readings,
the collector commit, installed packages, exit status and a final SQL audit.
The wrapper refuses to overwrite an existing soak database. Preserve earlier
run files before reusing `data/hyperliquid/aws-run/`.

The recorder survives an SSH disconnect through tmux. The recorder ends after
its duration; the VM stays running. A VM reboot does not restart this recording.
To stop early and let the wrapper finish its audit:

```bash
tmux send-keys -t pantred-soak:0.0 C-c
```

Wait for the session to end, then inspect `recorder.exit`, `audit.exit` and
`audit.txt` in the run directory before stopping the VM.

## Download and view one fixed snapshot

On the VM, choose a new output name and create the consistent snapshot:

```bash
.venv/bin/python scripts/vm/snapshot.py \
  data/hyperliquid/aws-run/soak.sqlite3 \
  data/hyperliquid/aws-run/snapshot.sqlite3 --gzip
```

Download the resulting `.sqlite3.gz` with SCP, then decompress it locally.
The helper opens the source in read-only mode, pins one WAL transaction and
backs up to a new file while recording continues. It refuses to overwrite an
existing output. It adds temporary disk activity and requires room for both
the snapshot and archive.

From the local repository:

```bash
python3 scripts/vm/view_snapshot.py --database data/hyperliquid/aws-run/snapshot.sqlite3
```

Open `http://127.0.0.1:8501`. This view hides recorder controls, rejects POSTs,
shows the latest captured receipt, and removes automatic polling. Selecting a
market or chart style reads the same local copy. It never fetches another VM
snapshot. This viewer is intended for this BTC/ETH/SOL, one-minute test profile.

For a live recording, run `sqlite3 -readonly DATABASE < scripts/vm/audit.sql`.
For a fixed snapshot without a stopped event, bind its evaluation time so the
audit does not count the time after capture as missing data. To reproduce the
interim report above:

```bash
sqlite3 -readonly data/hyperliquid/aws-run/soak-snapshot-2026-10-21-1416utc.sqlite3 \
  -cmd '.parameter init' \
  -cmd '.parameter set @as_of_ms 1792592211497' \
  < scripts/vm/audit.sql
```
