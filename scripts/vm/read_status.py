"""Read recording health without creating schemas or contending for a write lock."""

import argparse
import json
from pathlib import Path
import sqlite3
import time


def status(database: Path, counts=False) -> dict:
    db = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
    try:
        result = {'now_ms': int(time.time() * 1000), 'feeds': []}
        for symbol in ('BTC', 'ETH', 'SOL'):
            queries = [('l2Book', 'SELECT received_ms FROM observations WHERE channel=? AND symbol=? ORDER BY received_ms DESC LIMIT 1', ('l2Book', symbol)),
                       ('activeAssetCtx', 'SELECT received_ms FROM observations WHERE channel=? AND symbol=? ORDER BY received_ms DESC LIMIT 1', ('activeAssetCtx', symbol)),
                       ('trades', 'SELECT received_ms FROM trades WHERE symbol=? ORDER BY event_ms DESC LIMIT 1', (symbol,)),
                       ('candle:1m', "SELECT received_ms FROM candles WHERE symbol=? AND interval='1m' ORDER BY open_ms DESC LIMIT 1", (symbol,))]
            for channel, query, params in queries:
                row = db.execute(query, params).fetchone()
                result['feeds'].append({'channel': channel, 'symbol': symbol,
                                        'last_received_ms': row[0] if row else None})
        result['recent_events'] = db.execute(
            'SELECT time_ms,kind,details FROM recorder_events ORDER BY id DESC LIMIT 10').fetchall()
        if counts:
            result['counts'] = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                                for table in ('candles', 'trades', 'observations', 'recorder_events')}
        return result
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--counts', action='store_true', help='Also count all stored rows')
    args = parser.parse_args()
    print(json.dumps(status(args.database, args.counts), indent=2))
