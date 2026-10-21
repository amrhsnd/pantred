.bail on
.headers on
.mode column
.nullvalue -
.print 'PANTRED SOAK AUDIT'
.print 'Latest started event; live coverage begins at its first connected event. All times UTC.'
.print 'For a fixed snapshot, bind @as_of_ms to its capture/receipt time before running this audit.'
.print 'DATABASE INTEGRITY (expected: ok)'
PRAGMA quick_check;
CREATE TEMP TABLE pantred_soak_run AS
WITH latest AS (
  SELECT MAX(id) AS started_id FROM recorder_events WHERE kind='started'
), bounds AS (
  SELECT latest.started_id,
         MAX(CASE WHEN e.id=latest.started_id THEN e.time_ms END) AS started_ms,
         MIN(CASE WHEN e.kind='connected' THEN e.time_ms END) AS live_start_ms,
         MAX(CASE WHEN e.kind='stopped' THEN e.time_ms END) AS stopped_ms,
         SUM(CASE WHEN e.kind='disconnected' THEN 1 ELSE 0 END) AS disconnects,
         SUM(CASE WHEN e.kind='failed' THEN 1 ELSE 0 END) AS failures
  FROM latest LEFT JOIN recorder_events AS e ON e.id>=latest.started_id
)
SELECT *,
       COALESCE(stopped_ms, @as_of_ms,
                CAST((julianday('now')-2440587.5)*86400000 AS INTEGER)) AS end_ms,
       CASE WHEN started_id IS NULL THEN 'PRELIMINARY: no started event'
            WHEN live_start_ms IS NULL THEN 'PRELIMINARY: no connection observed'
            WHEN stopped_ms IS NULL THEN 'PRELIMINARY: no stopped event'
            ELSE 'FINAL: stopped observed; inspect all checks' END AS report_state
FROM bounds;
.print 'RUN WINDOW'
SELECT report_state,
       datetime(started_ms/1000.0,'unixepoch') AS started_utc,
       datetime(live_start_ms/1000.0,'unixepoch') AS connected_utc,
       datetime(stopped_ms/1000.0,'unixepoch') AS stopped_utc,
       datetime(end_ms/1000.0,'unixepoch') AS evaluated_through_utc,
       ROUND((end_ms-live_start_ms)/3600000.0,3) AS live_window_h,
       disconnects,failures
FROM pantred_soak_run;
.print 'Elapsed live-window time includes interruptions; a 24h span alone is not a pass.'
.print 'ALL LIFECYCLE / COVERAGE EVENTS'
SELECT id,datetime(time_ms/1000.0,'unixepoch') AS utc,kind,details
FROM recorder_events ORDER BY id;
.print 'EXPECTED FEEDS (9 rows; MISSING means no receipts in this live window)'
WITH symbols(symbol) AS (VALUES ('BTC'),('ETH'),('SOL')),
channels(channel) AS (VALUES ('trades'),('l2Book'),('activeAssetCtx')),
expected AS (
  SELECT channel,symbol FROM channels CROSS JOIN symbols
), feed AS (
  SELECT o.channel,o.symbol,o.received_ms
  FROM observations AS o CROSS JOIN pantred_soak_run AS r
  WHERE o.channel IN ('l2Book','activeAssetCtx')
    AND o.symbol IN ('BTC','ETH','SOL')
    AND o.received_ms BETWEEN r.live_start_ms AND r.end_ms
  UNION ALL
  SELECT 'trades',t.symbol,t.received_ms
  FROM trades AS t CROSS JOIN pantred_soak_run AS r
  WHERE t.symbol IN ('BTC','ETH','SOL')
    AND t.received_ms BETWEEN r.live_start_ms AND r.end_ms
), ordered AS (
  SELECT *,received_ms-LAG(received_ms) OVER (
    PARTITION BY channel,symbol ORDER BY received_ms
  ) AS gap_ms FROM feed
)
SELECT x.channel,x.symbol,
       CASE WHEN COUNT(o.received_ms)=0 THEN 'MISSING' ELSE 'PRESENT' END AS coverage,
       COUNT(o.received_ms) AS rows,
       datetime(MIN(o.received_ms)/1000.0,'unixepoch') AS first_utc,
       datetime(MAX(o.received_ms)/1000.0,'unixepoch') AS last_utc,
       ROUND((MAX(o.received_ms)-MIN(o.received_ms))/1000.0,1) AS span_s,
       ROUND(MAX(o.gap_ms)/1000.0,1) AS max_gap_s,
       ROUND((MIN(o.received_ms)-r.live_start_ms)/1000.0,1) AS start_lag_s,
       ROUND((r.end_ms-MAX(o.received_ms))/1000.0,1) AS end_lag_s
FROM expected AS x CROSS JOIN pantred_soak_run AS r
LEFT JOIN ordered AS o ON o.channel=x.channel AND o.symbol=x.symbol
GROUP BY x.channel,x.symbol ORDER BY x.channel,x.symbol;
.print 'Investigate gaps/edge lags >=60s.'
.print 'FULLY CONTAINED 1m CANDLES (excludes preload and partial boundary minutes)'
WITH bounds AS (
  SELECT ((live_start_ms+59999)/60000)*60000 AS first_ms,
         (end_ms/60000)*60000 AS end_ms
  FROM pantred_soak_run
), symbols(symbol) AS (VALUES ('BTC'),('ETH'),('SOL')),
bars AS (
  SELECT c.symbol,c.open_ms,
         LAG(c.open_ms) OVER (PARTITION BY c.symbol ORDER BY c.open_ms) AS previous_ms
  FROM candles AS c CROSS JOIN bounds AS b
  WHERE c.interval='1m' AND c.open_ms>=b.first_ms AND c.open_ms<b.end_ms
    AND c.symbol IN ('BTC','ETH','SOL')
), counts AS (
  SELECT s.symbol,b.first_ms,b.end_ms,
         CASE WHEN b.first_ms IS NOT NULL
              THEN MAX(0,(b.end_ms-b.first_ms)/60000) END AS expected,
         COUNT(c.open_ms) AS actual,
         SUM(CASE WHEN c.open_ms%60000=0 THEN 1 ELSE 0 END) AS aligned,
         SUM(CASE WHEN c.previous_ms IS NOT NULL
                       AND c.open_ms-c.previous_ms<>60000 THEN 1 ELSE 0 END) AS internal_gaps,
         SUM(CASE WHEN c.open_ms%60000<>0 THEN 1 ELSE 0 END) AS off_grid
  FROM symbols AS s CROSS JOIN bounds AS b
  LEFT JOIN bars AS c ON c.symbol=s.symbol
  GROUP BY s.symbol
)
SELECT symbol,
       datetime(first_ms/1000.0,'unixepoch') AS first_expected_utc,
       datetime(end_ms/1000.0,'unixepoch') AS exclusive_end_utc,
       expected,actual,expected-aligned AS missing,internal_gaps,off_grid,
       CASE WHEN first_ms IS NULL THEN 'NO LIVE WINDOW'
            WHEN expected=0 THEN 'NO COMPLETE MINUTES'
            WHEN off_grid>0 THEN 'INVALID TIMESTAMPS'
            WHEN expected<>aligned OR internal_gaps<>0 THEN 'GAPS'
            ELSE 'OK' END AS coverage
FROM counts ORDER BY symbol;
.print 'LIMITATIONS'
.print 'Backfill can conceal stream outages. Receipt continuity does not prove exchange completeness.'
.print 'Context has no exchange timestamp. Books are snapshots, not a complete order-event stream.'
.print 'Without a stopped event this report is preliminary. Check feed gaps, lifecycle and disk growth.'
