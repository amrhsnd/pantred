#!/usr/bin/env bash
set -u
umask 077
pantred_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$pantred_root" || exit 1
pantred_run=data/hyperliquid/aws-run
pantred_db="$pantred_run/soak.sqlite3"
mkdir -p "$pantred_run"
if [ -e "$pantred_db" ]; then
  printf 'A soak database already exists; refusing to start another recorder.\n' >&2
  exit 2
fi
for pantred_command in tmux sqlite3; do
  command -v "$pantred_command" >/dev/null || exit 1
done
if [ ! -x .venv/bin/python ]; then
  printf 'Install the project requirements in .venv first.\n' >&2
  exit 1
fi
if tmux has-session -t pantred-health 2>/dev/null; then
  printf 'A health-monitor session already exists.\n' >&2
  exit 2
fi
git rev-parse HEAD > "$pantred_run/commit.txt"
.venv/bin/python -m pip freeze > "$pantred_run/requirements-installed.txt"
.venv/bin/python -c 'import json; from datetime import datetime,timezone,timedelta; start=datetime.now(timezone.utc); print(json.dumps({"launch_utc":start.isoformat(),"approximate_finish_utc":(start+timedelta(seconds=90000)).isoformat(),"duration_seconds":90000,"symbols":["BTC","ETH","SOL"],"intervals":["1m"]},indent=2))' > "$pantred_run/run.json"
tmux new-session -d -s pantred-health -c "$pantred_root" 'bash scripts/vm/health.sh' || exit 1
trap 'tmux kill-session -t pantred-health 2>/dev/null || true' EXIT
# Keep the wrapper alive after Ctrl+C so it can write the final audit.
trap ':' INT
.venv/bin/python -u -B main.py hyperliquid record --database "$pantred_db" --symbols BTC ETH SOL --timeframes 1m --lookback-hours 1 --duration 90000 > "$pantred_run/recorder.log" 2>&1
pantred_recorder_exit=$?
printf '%s\n' "$pantred_recorder_exit" > "$pantred_run/recorder.exit"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$pantred_run/finished-utc.txt"
.venv/bin/python -B scripts/vm/read_status.py --counts --database "$pantred_db" > "$pantred_run/final-status.json" 2> "$pantred_run/final-status-error.log"
sqlite3 -readonly "$pantred_db" < scripts/vm/audit.sql > "$pantred_run/audit.txt" 2>&1
printf '%s\n' "$?" > "$pantred_run/audit.exit"
exit "$pantred_recorder_exit"
