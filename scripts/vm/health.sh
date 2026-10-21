#!/usr/bin/env bash
set -u
umask 077
pantred_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$pantred_root" || exit 1
pantred_run=data/hyperliquid/aws-run
mkdir -p "$pantred_run"
while tmux has-session -t pantred-soak 2>/dev/null; do
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  .venv/bin/python -B scripts/vm/read_status.py --database "$pantred_run/soak.sqlite3"
  du -h "$pantred_run/soak.sqlite3"* 2>/dev/null
  df -h .
  free -m
  sleep 60
done >> "$pantred_run/health.log" 2>&1
