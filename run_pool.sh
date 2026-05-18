#!/bin/bash
# ==========================================================================
# Full-pool benchmark runner
#
# Runs all full-pool configs across multiple seeds, parallelising over
# targets × seeds.  Each run writes to:
#   logs/{model}_{timestamp}/{arena}/target{hash}/seed{N}/
#
# Usage:
#   bash run_pool.sh
#
#   # Dry run:
#   bash run_pool.sh --dry-run
#
#   # Resume (skip completed runs):
#   bash run_pool.sh --resume
#
#   # Reuse a previous run's timestamp (so --resume hits the right output dir):
#   bash run_pool.sh --timestamp 20260426_030536 --resume
#
#   # Specific seeds:
#   bash run_pool.sh --seeds "42 100"
#
#   # Specific configs only:
#   bash run_pool.sh --configs "gpt52_halite deepseekv32_battlesnake"
#
#   # Run with post-hoc pool evaluation after each target:
#   bash run_pool.sh --pool-eval
#
#   # Pool eval with custom sim count:
#   bash run_pool.sh --pool-eval --pool-eval-sims 10
#
#   # Run a custom config directory:
#   bash run_pool.sh --config-dir configs/inverse/pool
# ==========================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
MAIN="$REPO_ROOT/main.py"

# ---- Defaults ----
SEEDS=(42)
DRY_RUN=false
RESUME=false
CONFIGS_FILTER=""  # empty = run all; space-separated list = only these config names
PARALLEL=15
PAUSE_BETWEEN=5
POOL_EVAL=false
POOL_EVAL_SIMS=20
POOL_EVAL_ROUNDS="all"  # last | all | comma-separated

RUN_TIMESTAMP=""

# ---- Configs ----
CONFIG_DIR="configs/inverse/pool"

# ---- Parse arguments ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --resume|-r)
            RESUME=true
            shift
            ;;
        --seeds|-s)
            IFS=' ' read -ra SEEDS <<< "$2"
            shift 2
            ;;
        --parallel|-p)
            PARALLEL="$2"
            shift 2
            ;;
        --pool-eval)
            POOL_EVAL=true
            shift
            ;;
        --pool-eval-sims)
            POOL_EVAL=true
            POOL_EVAL_SIMS="$2"
            shift 2
            ;;
        --pool-eval-rounds)
            POOL_EVAL_ROUNDS="$2"
            shift 2
            ;;
        --configs|-c)
            CONFIGS_FILTER="$2"
            shift 2
            ;;
        --config-dir|-d)
            CONFIG_DIR="$2"
            shift 2
            ;;
        --timestamp|-T)
            RUN_TIMESTAMP="$2"
            shift 2
            ;;
        --help|-h)
            head -30 "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# Default RUN_TIMESTAMP to "now" if --timestamp wasn't passed.
if [[ -z "$RUN_TIMESTAMP" ]]; then
    RUN_TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
fi
LOG_FILE="logs/pool_${RUN_TIMESTAMP}.log"
mkdir -p "$(dirname "$LOG_FILE")"

# ---- Logging ----
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}


# ---- Create a temp config pinned to a single target ----
make_pool_target_config() {
    local config_file="$1"
    local seed="$2"
    local target_path="$3"
    local tmp_dir="$4"
    local config_name target_name tmp_file
    config_name="$(basename "$config_file" .yaml)"
    target_name="$(basename "$target_path")"
    tmp_file="${tmp_dir}/${config_name}_${target_name}_seed${seed}.yaml"

    "$PYTHON" "$REPO_ROOT/scripts/inverse/make_pool_target_config.py" \
        "$config_file" "$tmp_file" \
        --seed "$seed" \
        --target-source-path "$target_path" >&2
    echo "$tmp_file"
}

# ---- Run a single pool-target experiment ----
run_one_pool() {
    local config_file="$1"
    local seed="$2"
    local target_path="$3"
    local timestamp="$4"
    local tmp_dir="$5"

    local target_name run_log status_dir
    target_name="$(basename "$target_path")"
    run_log="logs/${target_name}_seed${seed}.log"
    status_dir="${tmp_dir}/status"
    mkdir -p "$status_dir"

    log "  RUN: ${target_name} seed=${seed}"

    if $DRY_RUN; then
        log "    [DRY RUN] $PYTHON $MAIN ... -t $timestamp"
        touch "${status_dir}/${target_name}_seed${seed}.ok"
        return 0
    fi

    local seeded_config extra_flags=""
    seeded_config="$(make_pool_target_config "$config_file" "$seed" "$target_path" "$tmp_dir")"
    $RESUME && extra_flags="$extra_flags --resume"
    if $POOL_EVAL; then
        extra_flags="$extra_flags --pool-eval --pool-eval-sims $POOL_EVAL_SIMS --pool-eval-rounds $POOL_EVAL_ROUNDS"
    fi

    mkdir -p logs
    local start_time
    start_time=$(date +%s)

    if "$PYTHON" "$MAIN" "$seeded_config" \
        -t "$timestamp" $extra_flags \
        > "$run_log" 2>&1; then
        local elapsed=$(( ($(date +%s) - start_time) / 60 ))
        log "    DONE: ${target_name} seed=${seed} — SUCCESS (${elapsed}min)"
        touch "${status_dir}/${target_name}_seed${seed}.ok"
        return 0
    else
        local rc=$?
        local elapsed=$(( ($(date +%s) - start_time) / 60 ))
        log "    DONE: ${target_name} seed=${seed} — FAILED rc=${rc} (${elapsed}min)"
        touch "${status_dir}/${target_name}_seed${seed}.fail"
        return 1
    fi
}

# ---- Wait until fewer than N jobs are running ----
wait_for_slot() {
    local max_jobs="$1"
    while (( $(jobs -rp | wc -l) >= max_jobs )); do
        sleep 2
    done
}

# ---- Config filter helper ----
should_run_config() {
    local config_name="$1"
    if [[ -z "$CONFIGS_FILTER" ]]; then
        return 0
    fi
    for allowed in $CONFIGS_FILTER; do
        [[ "$config_name" == "$allowed" ]] && return 0
    done
    return 1
}

# ---- Main ----

log "============================================================"
log "Full-Pool Benchmark Runner"
log "  Seeds:    ${SEEDS[*]}"
log "  Parallel: ${PARALLEL}"
log "  Resume:   ${RESUME}"
log "  Dry:      ${DRY_RUN}"
log "  PoolEval: ${POOL_EVAL} (sims=${POOL_EVAL_SIMS}, rounds=${POOL_EVAL_ROUNDS})"
if [[ -n "$CONFIGS_FILTER" ]]; then
    log "  Configs:  ${CONFIGS_FILTER}"
fi
log "============================================================"

# Health checks
if ! $DRY_RUN; then
    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log "WARNING: Local LLM proxy not running at localhost:8000. Continuing; proxy-dependent configs may fail."
    else
        log "Local LLM proxy health check: OK"
    fi

    runtime="${CODECLASH_RUNTIME:-docker}"
    # Portable lowercase (avoid bash 4+ ${var,,} which breaks on macOS /bin/bash 3.2)
    runtime=$(echo "$runtime" | tr '[:upper:]' '[:lower:]')
    if [[ "$runtime" == "singularity" || "$runtime" == "apptainer" ]]; then
        if ! command -v singularity > /dev/null 2>&1 && ! command -v apptainer > /dev/null 2>&1; then
            log "ERROR: CODECLASH_RUNTIME=$runtime but neither singularity nor apptainer is on PATH. Aborting."
            exit 1
        fi
        log "Singularity check: OK (runtime=$runtime)"
    else
        if ! docker info > /dev/null 2>&1; then
            log "ERROR: Docker not accessible. Aborting."
            exit 1
        fi
        log "Docker check: OK"
    fi
fi

TOTAL=0
LAUNCHED=0
TMP_DIR=$(mktemp -d -t revenge_bench_pool_XXXXXX)

while IFS= read -r config_file; do
    config_name="$(basename "$config_file" .yaml)"
    should_run_config "$config_name" || continue

    # Discover targets via Python helper
    targets_file="${TMP_DIR}/targets_${config_name}.txt"
    "$PYTHON" -m revenge_bench.scripts.inverse.list_pool_targets "$config_file" --output "$targets_file"
    TARGETS=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && TARGETS+=("$line")
    done < "$targets_file"

    log ""
    log "=== ${config_name} (${#TARGETS[@]} targets × ${#SEEDS[@]} seeds = $(( ${#TARGETS[@]} * ${#SEEDS[@]} )) jobs, ts=${RUN_TIMESTAMP}) ==="

    for target_path in "${TARGETS[@]}"; do
        for seed in "${SEEDS[@]}"; do
            TOTAL=$((TOTAL + 1))

            if ! $DRY_RUN; then
                wait_for_slot "$PARALLEL"
            fi

            run_one_pool "$config_file" "$seed" "$target_path" "$RUN_TIMESTAMP" "$TMP_DIR" &

            if ! $DRY_RUN; then
                sleep $PAUSE_BETWEEN
            fi
            LAUNCHED=$((LAUNCHED + 1))
        done
    done
done < <(find "$CONFIG_DIR" -mindepth 1 -maxdepth 2 -name "*.yaml" -print | sort)

log ""
log "All ${LAUNCHED} jobs launched. Waiting for completion..."
wait || true

STATUS_DIR="${TMP_DIR}/status"
SUCCESS=$(find "$STATUS_DIR" -name "*.ok" 2>/dev/null | wc -l)
FAILED=$(find "$STATUS_DIR" -name "*.fail" 2>/dev/null | wc -l)
SKIPPED=$(find "$STATUS_DIR" -name "*.skip" 2>/dev/null | wc -l)

log ""
log "============================================================"
log "DONE: ${SUCCESS} succeeded, ${FAILED} failed, ${SKIPPED} skipped out of ${TOTAL} total"
log "============================================================"

rm -rf "$TMP_DIR"
exit $FAILED
