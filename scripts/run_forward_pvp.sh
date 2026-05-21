#!/bin/bash
# Run the forward-PvP tournament across configured (challenger, game) pairs.
# Iterates over configs/forward_pvp/{challenger}/{game}/*.yaml, dispatching each
# YAML as one main.py invocation. Forward-PvP configs do not contain a
# strategy_pool section, so they cannot be routed through scripts/run_pool.sh; this
# wrapper invokes main.py directly with bounded parallelism.
#
# Usage:
#   bash scripts/run_forward_pvp.sh [--tag-suffix seed42]
#                                                [--challengers "gpt5 gpt5-mini"]
#                                                [--games "battlesnake halite"]
#                                                [--condition blind|recovered|oracle]
#                                                [--parallel N]
#                                                [--dry-run] [--resume]
#
# Seeds for forward-PvP runs are baked into the YAML configs (or game RNG
# defaults). The optional --tag-suffix is appended to the run timestamp to
# label the output directory (matches legacy run_forward_pvp_seed*.sh
# convention).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${PYTHON:-}" ]]; then
    if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
        PYTHON="$REPO_ROOT/.venv/bin/python"
    else
        PYTHON="python3"
    fi
fi
MAIN="$REPO_ROOT/main.py"

# ---- Defaults ----
TAG_SUFFIX=""         # appended to RUN_TIMESTAMP when set
CHALLENGERS=""        # empty = all
GAMES=""              # empty = all
CONDITION_FILTER=""   # empty = all; "blind", "recovered", or "oracle"
PARALLEL=6
PAUSE_BETWEEN=2
DRY_RUN=false
RESUME=false

# ---- Parse arguments ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag-suffix) TAG_SUFFIX="$2"; shift 2 ;;
    --challengers|-c) CHALLENGERS="$2"; shift 2 ;;
    --games|-g) GAMES="$2"; shift 2 ;;
    --condition) CONDITION_FILTER="$2"; shift 2 ;;
    --parallel|-p) PARALLEL="$2"; shift 2 ;;
    --pause) PAUSE_BETWEEN="$2"; shift 2 ;;
    --dry-run|-n) DRY_RUN=true; shift ;;
    --resume|-r) RESUME=true; shift ;;
    --help|-h)
      sed -n '2,20p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

RUN_TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
if [[ -n "$TAG_SUFFIX" ]]; then
  RUN_TIMESTAMP="${RUN_TIMESTAMP}_${TAG_SUFFIX}"
fi
LOG_DIR="logs/forward_pvp_${RUN_TIMESTAMP}"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/runner.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ---- Collect configs ----
CONFIGS=()
for chal_dir in configs/forward_pvp/*/; do
  chal="$(basename "$chal_dir")"
  if [[ -n "$CHALLENGERS" && ! " $CHALLENGERS " =~ " $chal " ]]; then continue; fi
  for game_dir in "$chal_dir"*/; do
    [ -d "$game_dir" ] || continue
    game="$(basename "$game_dir")"
    if [[ -n "$GAMES" && ! " $GAMES " =~ " $game " ]]; then continue; fi
    while IFS= read -r f; do
      name="$(basename "$f" .yaml)"
      if [[ -n "$CONDITION_FILTER" ]]; then
        [[ "$name" == *"__${CONDITION_FILTER}" ]] || continue
      fi
      CONFIGS+=("$f")
    done < <(find "$game_dir" -maxdepth 1 -name "*.yaml" -print | sort)
  done
done

TOTAL=${#CONFIGS[@]}
log "============================================================"
log "Forward PvP Runner"
log "  Configs:     ${TOTAL}"
log "  Timestamp:   ${RUN_TIMESTAMP}"
log "  Tag suffix:  ${TAG_SUFFIX:-<none>}"
log "  Challengers: ${CHALLENGERS:-<all>}"
log "  Games:       ${GAMES:-<all>}"
log "  Condition:   ${CONDITION_FILTER:-<all>}"
log "  Parallel:    ${PARALLEL}"
log "  Resume:      ${RESUME}"
log "  Dry run:     ${DRY_RUN}"
log "  Log dir:     ${LOG_DIR}"
log "============================================================"

if (( TOTAL == 0 )); then
  log "No configs matched."
  exit 0
fi

STATUS_DIR=$(mktemp -d -t forward_pvp_status_XXXXXX)
trap 'rm -rf "$STATUS_DIR"' EXIT

wait_for_slot() {
  local max_jobs="$1"
  while (( $(jobs -rp | wc -l) >= max_jobs )); do
    sleep 2
  done
}

run_one() {
  local config_file="$1"
  local config_name="$2"
  local idx="$3"
  local run_log="${LOG_DIR}/${config_name}.log"
  local extra_flags=()
  $RESUME && extra_flags+=("--resume")

  local t0
  t0=$(date +%s)

  if "$PYTHON" "$MAIN" "$config_file" \
      -t "forward_pvp_${RUN_TIMESTAMP}" \
      "${extra_flags[@]+"${extra_flags[@]}"}" \
      > "$run_log" 2>&1; then
    local elapsed=$(( ($(date +%s) - t0) / 60 ))
    log "  [${idx}/${TOTAL}] ${config_name} - SUCCESS (${elapsed}min)"
    touch "${STATUS_DIR}/${config_name}.ok"
  else
    local rc=$?
    local elapsed=$(( ($(date +%s) - t0) / 60 ))
    log "  [${idx}/${TOTAL}] ${config_name} - FAILED rc=${rc} (${elapsed}min)"
    touch "${STATUS_DIR}/${config_name}.fail"
  fi
}

for i in "${!CONFIGS[@]}"; do
  config_file="${CONFIGS[$i]}"
  config_name="$(basename "$config_file" .yaml)"
  idx=$((i + 1))

  if $DRY_RUN; then
    log "  [DRY RUN] [${idx}/${TOTAL}] $PYTHON $MAIN $config_file -t forward_pvp_${RUN_TIMESTAMP}"
    touch "${STATUS_DIR}/${config_name}.skip"
    continue
  fi

  log "[${idx}/${TOTAL}] Launching ${config_name}"
  wait_for_slot "$PARALLEL"
  run_one "$config_file" "$config_name" "$idx" &
  sleep "$PAUSE_BETWEEN"
done

if ! $DRY_RUN; then
  log ""
  log "All jobs launched. Waiting for completion..."
  wait || true
fi

SUCCESS=$(find "$STATUS_DIR" -name "*.ok" 2>/dev/null | wc -l | tr -d ' ')
FAILED=$(find "$STATUS_DIR" -name "*.fail" 2>/dev/null | wc -l | tr -d ' ')
SKIPPED=$(find "$STATUS_DIR" -name "*.skip" 2>/dev/null | wc -l | tr -d ' ')

log ""
log "============================================================"
log "Forward PvP - DONE"
log "  Total:   ${TOTAL}"
log "  Success: ${SUCCESS}"
log "  Failed:  ${FAILED}"
log "  Skipped: ${SKIPPED}"
log "============================================================"

if (( FAILED > 0 )); then
  exit 1
fi
