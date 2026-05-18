#!/bin/bash
# ==========================================================================
# OOM Watchdog — kills NL observation processes if RSS exceeds threshold
#
# Checks every 30s:
#   - Per-process: kills any single main.py process exceeding PER_PROC_MAX_GB
#   - Global: kills ALL main.py processes if combined RSS exceeds TOTAL_MAX_GB
#
# Usage:
#   nohup bash watchdog_oom.sh &>> logs/watchdog_oom.log &
#   bash watchdog_oom.sh --per-proc 15 --total 180
# ==========================================================================

set -uo pipefail

PER_PROC_MAX_GB=15    # Kill individual process if it exceeds this
TOTAL_MAX_GB=180      # Kill everything if combined RSS exceeds this
INTERVAL=30           # Check interval in seconds
PATTERN="main.py"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "usage: watchdog_oom.sh [--per-proc GB] [--total GB] [--interval SEC] [--pattern REGEX]"
            echo "  --per-proc GB   kill any single matching process exceeding this RSS (default: ${PER_PROC_MAX_GB})"
            echo "  --total GB      kill all matching processes if combined RSS exceeds this (default: ${TOTAL_MAX_GB})"
            echo "  --interval SEC  poll interval in seconds (default: ${INTERVAL})"
            echo "  --pattern REGEX ps-aux grep pattern to match workers (default: ${PATTERN})"
            exit 0 ;;
        --per-proc)  PER_PROC_MAX_GB="$2"; shift 2 ;;
        --total)     TOTAL_MAX_GB="$2"; shift 2 ;;
        --interval)  INTERVAL="$2"; shift 2 ;;
        --pattern)   PATTERN="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

PER_PROC_MAX_KB=$(( PER_PROC_MAX_GB * 1024 * 1024 ))
TOTAL_MAX_KB=$(( TOTAL_MAX_GB * 1024 * 1024 ))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Watchdog started"
echo "  Per-process limit: ${PER_PROC_MAX_GB} GB"
echo "  Total limit:       ${TOTAL_MAX_GB} GB"
echo "  Interval:          ${INTERVAL}s"
echo "  Pattern:           ${PATTERN}"
echo ""

while true; do
    # Get PIDs and RSS (in KB) of matching processes
    mapfile -t PROCS < <(ps aux | grep "$PATTERN" | grep -v grep | awk '{print $2, $6}')

    if [[ ${#PROCS[@]} -eq 0 ]]; then
        # No processes found — exit watchdog
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] No matching processes found. Exiting watchdog."
        exit 0
    fi

    TOTAL_KB=0
    for entry in "${PROCS[@]}"; do
        PID=$(echo "$entry" | awk '{print $1}')
        RSS_KB=$(echo "$entry" | awk '{print $2}')
        TOTAL_KB=$(( TOTAL_KB + RSS_KB ))

        # Per-process check
        if [[ $RSS_KB -gt $PER_PROC_MAX_KB ]]; then
            RSS_GB=$(awk "BEGIN {printf \"%.1f\", $RSS_KB / 1024 / 1024}")
            CMD=$(ps -p "$PID" -o args= 2>/dev/null | head -c 200)
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] KILL PID=$PID RSS=${RSS_GB}GB > ${PER_PROC_MAX_GB}GB limit"
            echo "  CMD: $CMD"
            kill "$PID" 2>/dev/null
        fi
    done

    # Global check
    if [[ $TOTAL_KB -gt $TOTAL_MAX_KB ]]; then
        TOTAL_GB=$(awk "BEGIN {printf \"%.1f\", $TOTAL_KB / 1024 / 1024}")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] KILL ALL — total RSS=${TOTAL_GB}GB > ${TOTAL_MAX_GB}GB limit (${#PROCS[@]} procs)"
        for entry in "${PROCS[@]}"; do
            PID=$(echo "$entry" | awk '{print $1}')
            kill "$PID" 2>/dev/null
        done
        # Also kill any parent runner
        pkill -f "scripts/forward_pvp/run_forward_pvp.sh" 2>/dev/null
        pkill -f "scripts/inverse/run_" 2>/dev/null
        pkill -f "run_pool.sh" 2>/dev/null
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] All processes killed. Exiting watchdog."
        exit 1
    fi

    # Periodic status (every 5 minutes = every 10 checks)
    TOTAL_GB=$(awk "BEGIN {printf \"%.1f\", $TOTAL_KB / 1024 / 1024}")
    if (( SECONDS % 300 < INTERVAL )); then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK — ${#PROCS[@]} procs, total RSS=${TOTAL_GB}GB"
    fi

    sleep "$INTERVAL"
done
