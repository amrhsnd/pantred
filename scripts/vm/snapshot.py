"""Take a bounded SQLite online backup while a WAL recorder keeps writing."""

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import sqlite3
import time


def capture(source_path: Path, output: Path, timeout: float = 60) -> dict:
    source_path, output = source_path.resolve(), output.resolve()
    if timeout <= 0:
        raise ValueError('Timeout must be positive')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination exclusively; never overwrite an earlier snapshot.
    output.open('xb').close()
    started = time.monotonic()

    def progress(_status, _remaining, _total):
        if time.monotonic() - started > timeout:
            raise TimeoutError('Online backup exceeded its timeout')

    try:
        source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True, timeout=5)
        try:
            source.execute('BEGIN')
            # Pin one WAL read snapshot so new commits cannot restart each step.
            source.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
            captured = datetime.now(timezone.utc)
            target = sqlite3.connect(output)
            try:
                source.backup(target, pages=256, progress=progress, sleep=0.05)
            finally:
                target.close()
        finally:
            source.close()
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {'database': str(output), 'captured_utc': captured.isoformat(),
            'captured_ms': int(captured.timestamp() * 1000),
            'bytes': output.stat().st_size,
            'backup_seconds': round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--timeout', type=float, default=60, help='Backup timeout in seconds')
    parser.add_argument('--gzip', action='store_true', help='Also create OUTPUT.gz for download')
    args = parser.parse_args()
    archive = Path(str(args.output) + '.gz')
    if args.gzip and archive.exists():
        parser.error(f'Archive already exists: {archive}')
    result = capture(args.source, args.output, args.timeout)
    print(json.dumps(result), flush=True)
    if args.gzip:
        with args.output.open('rb') as source, archive.open('xb') as destination:
            with gzip.GzipFile(fileobj=destination, mode='wb', compresslevel=1) as compressed:
                shutil.copyfileobj(source, compressed, 1024 * 1024)
        print(json.dumps({'archive': str(archive.resolve()), 'bytes': archive.stat().st_size}), flush=True)


if __name__ == '__main__':
    main()
