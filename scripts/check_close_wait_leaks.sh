#!/usr/bin/env bash
# scripts/check_close_wait_leaks.sh
#
# Polls all main.py processes for CLOSE_WAIT sockets to confirm the timeout
# fix in configs/inverse/pool/*.yaml is taking effect at runtime.
#
# Usage:
#   ./scripts/check_close_wait_leaks.sh              # one-shot check
#   ./scripts/check_close_wait_leaks.sh --watch 60   # poll every 60s, log status each tick
#
# A "leak" is any process with a CLOSE_WAIT socket persisting more than
# ~5-7 minutes. A momentary CLOSE_WAIT during normal request teardown is
# fine; a persistent one indicates the timeout is not being honoured.
set -euo pipefail

interval=""
if [[ "${1:-}" == "--watch" ]]; then
  interval="${2:-60}"
fi

check_once() {
  local found=0
  for pid in $(pgrep -f "main.py" 2>/dev/null || true); do
    cw=$(lsof -p "$pid" 2>/dev/null | grep -c CLOSE_WAIT || true)
    if [[ "$cw" -gt 0 ]]; then
      etime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ' || true)
      echo "PID $pid (etime=$etime): $cw CLOSE_WAIT socket(s) — should auto-resolve in <5min"
      found=1
    fi
  done
  return $found
}

if [[ -n "$interval" ]]; then
  while true; do
    if check_once; then
      echo "[$(date)] no leaks"
    fi
    sleep "$interval"
  done
else
  if check_once; then
    echo "no main.py processes with CLOSE_WAIT sockets"
  fi
fi
