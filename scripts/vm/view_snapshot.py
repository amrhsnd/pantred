"""Serve a downloaded recording snapshot locally without recorder controls."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dashboard import DashboardHandler, ThreadingHTTPServer
from monitor import Monitor


class SnapshotMonitor(Monitor):
    def __init__(self, database):
        super().__init__(database)
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            self.captured_ms = max(row[0] or 0 for row in db.execute('''
                SELECT MAX(received_ms) FROM observations
                UNION ALL SELECT MAX(received_ms) FROM trades
                UNION ALL SELECT MAX(received_ms) FROM candles
            '''))
        self.captured_utc = datetime.fromtimestamp(self.captured_ms / 1000, timezone.utc).strftime('%d %b %Y, %H:%M:%S UTC')

    def snapshot(self, symbol='BTC', interval='1m', limit=180):
        data = super().snapshot(symbol, interval, limit)
        data['now_ms'] = self.captured_ms
        return data

    def control(self, action):
        raise ValueError('This is a fixed snapshot.')


class SnapshotHandler(DashboardHandler):
    def do_POST(self):
        self.send_json({'error': 'This dashboard displays a fixed snapshot.'}, 405)

    def do_GET(self):
        if self.path == '/':
            page = (ROOT / 'web/monitor.html').read_text()
            page = page.replace('</head>', '<style>#record,#stop{display:none!important}</style></head>')
            page = page.replace('Market data only <span class="sep">/</span> BTC, ETH, SOL',
                                f'Fixed AWS snapshot / Latest receipt: {self.server.monitor.captured_utc}')
            page = page.replace('>Recorder stopped<', '>Downloaded snapshot<')
            page = page.replace('<a href="/yahoo">Yahoo collector</a>', '')
            for value, label in [('5m', '5 minutes'), ('15m', '15 minutes'), ('1h', '1 hour')]:
                page = page.replace(f'<option value="{value}">{label}</option>', '')
            self.send_bytes(page.encode(), 'text/html; charset=utf-8')
        elif self.path == '/static/monitor.js':
            script = (ROOT / 'web/monitor.js').read_text()
            script = script.replace("$('recorder-state').textContent = running ? 'Recorder running' : data.process.exit_code ? 'Recorder error' : 'Recorder stopped';",
                                    "$('recorder-state').textContent = 'Downloaded snapshot';")
            script = script.replace('Context: ${age}s ago', 'Context at capture: ${age}s old')
            script = script.replace("'Last candle forming'", "'Final candle was forming at capture'")
            script = script.replace("`${Math.max(0,Math.round((data.now_ms-data.book.received_ms)/1000))}s ago`",
                                    "`${Math.max(0,Math.round((data.now_ms-data.book.received_ms)/1000))}s old at capture`")
            script = script.replace('refresh(); setInterval(refresh, 2000);', 'refresh();')
            self.send_bytes(script.encode(), 'text/javascript')
        else:
            super().do_GET()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8501)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), SnapshotHandler)
    server.monitor = SnapshotMonitor(args.database.resolve())
    print(f'Fixed snapshot dashboard: http://127.0.0.1:{args.port}', flush=True)
    print(f'Latest receipt: {server.monitor.captured_utc}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
