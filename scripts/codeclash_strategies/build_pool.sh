#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Build a strategy pool from extracted CodeClash strategies.
#
# Orchestrates the full pipeline:
#   1. validate_strategies.py  — Round 1: structural hard filters
#   2. select_candidates.py    — Round 2: dedup + complexity + sampling
#   3. elo_tournament.py       — Round 3: Swiss-system Elo tournament
#
# Usage:
#   # Full pipeline (default: BattleSnake, 40 strategies, 15 Elo rounds)
#   bash scripts/codeclash_strategies/build_pool.sh
#
#   # Custom game and count
#   bash scripts/codeclash_strategies/build_pool.sh --game BattleSnake --count 40
#
#   # Skip Elo (just validate + select)
#   bash scripts/codeclash_strategies/build_pool.sh --skip-elo
#
#   # Resume Elo from a previous run
#   bash scripts/codeclash_strategies/build_pool.sh --elo-only
#
#   # Dry-run: show what would happen without writing anything
#   bash scripts/codeclash_strategies/build_pool.sh --dry-run
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${PYTHON:-}" ]]; then
    if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
        PYTHON="$REPO_ROOT/.venv/bin/python"
    else
        PYTHON="python3"
    fi
fi

# ── Defaults ─────────────────────────────────────────────────────────
GAME="BattleSnake"
COUNT=40
ELO_ROUNDS=15
ELO_SIMS=10
SEED=42
DEDUP_THRESHOLD=0.997
SOURCE="data/extracted_strategies"
POOL_DIR=""          # auto-derived from game if empty
ELO_DIR=""           # auto-derived from game if empty
SKIP_ELO=false
ELO_ONLY=false
DRY_RUN=false

# ── Parse arguments ──────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --game)         GAME="$2";           shift 2 ;;
        --count)        COUNT="$2";          shift 2 ;;
        --elo-rounds)   ELO_ROUNDS="$2";     shift 2 ;;
        --elo-sims)     ELO_SIMS="$2";       shift 2 ;;
        --seed)         SEED="$2";           shift 2 ;;
        --threshold)    DEDUP_THRESHOLD="$2"; shift 2 ;;
        --source)       SOURCE="$2";         shift 2 ;;
        --pool-dir)     POOL_DIR="$2";       shift 2 ;;
        --elo-dir)      ELO_DIR="$2";        shift 2 ;;
        --skip-elo)     SKIP_ELO=true;       shift   ;;
        --elo-only)     ELO_ONLY=true;       shift   ;;
        --dry-run)      DRY_RUN=true;        shift   ;;
        -h|--help)
            awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 && !/^#/ { exit }' "$0"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Derived paths ────────────────────────────────────────────────────
GAME_LOWER=$(echo "$GAME" | tr '[:upper:]' '[:lower:]')
[[ -z "$POOL_DIR" ]] && POOL_DIR="data/targets/${GAME_LOWER}"
[[ -z "$ELO_DIR" ]]  && ELO_DIR="logs/elo/${GAME}"

echo "════════════════════════════════════════════════════════════════"
echo "  Strategy Pool Builder"
echo "════════════════════════════════════════════════════════════════"
echo "  Game:           $GAME"
echo "  Source:         $SOURCE"
echo "  Pool dir:       $POOL_DIR"
echo "  Target count:   $COUNT"
echo "  Dedup threshold: $DEDUP_THRESHOLD"
echo "  Elo rounds:     $ELO_ROUNDS (sims=$ELO_SIMS)"
echo "  Elo output:     $ELO_DIR"
echo "  Seed:           $SEED"
[[ "$SKIP_ELO" == true ]] && echo "  ⚠ Skipping Elo tournament"
[[ "$ELO_ONLY" == true ]] && echo "  ⚠ Elo-only mode (skipping validate + select)"
[[ "$DRY_RUN" == true ]]  && echo "  ⚠ Dry-run mode"
echo "════════════════════════════════════════════════════════════════"
echo ""

DRY_FLAG=""
[[ "$DRY_RUN" == true ]] && DRY_FLAG="--dry-run"

# ── Step 1: Validate (Round 1 hard filters) ──────────────────────────
if [[ "$ELO_ONLY" != true ]]; then
    echo "━━━ Step 1/3: Validate strategies (Round 1) ━━━"
    "$PYTHON" -m revenge_bench.scripts.codeclash_strategies.validate_strategies \
        --game "$GAME" \
        --source "$SOURCE" \
        ${DRY_RUN:+--quiet}
    echo ""

    # ── Step 2: Select candidates (Round 2 dedup + complexity + sample) ──
    echo "━━━ Step 2/3: Select candidates (Round 2) ━━━"
    SELECT_ARGS=(
        --game "$GAME"
        --source "$SOURCE"
        --count "$COUNT"
        --threshold "$DEDUP_THRESHOLD"
        --seed "$SEED"
    )

    if [[ "$DRY_RUN" == true ]]; then
        SELECT_ARGS+=(--dry-run)
    else
        SELECT_ARGS+=(--populate "$POOL_DIR")
    fi

    "$PYTHON" -m revenge_bench.scripts.codeclash_strategies.select_candidates "${SELECT_ARGS[@]}"
    echo ""
fi

# ── Step 3: Elo tournament (Round 3) ─────────────────────────────────
if [[ "$SKIP_ELO" != true ]]; then
    echo "━━━ Step 3/3: Elo tournament (Round 3) ━━━"

    if [[ "$DRY_RUN" == true ]]; then
        "$PYTHON" -m revenge_bench.scripts.codeclash_strategies.elo_tournament \
            --pool "$POOL_DIR" \
            --game "$GAME" \
            --rounds "$ELO_ROUNDS" \
            --sims "$ELO_SIMS" \
            --output "$ELO_DIR" \
            --dry-run
    else
        "$PYTHON" -m revenge_bench.scripts.codeclash_strategies.elo_tournament \
            --pool "$POOL_DIR" \
            --game "$GAME" \
            --rounds "$ELO_ROUNDS" \
            --sims "$ELO_SIMS" \
            --output "$ELO_DIR"
    fi
    echo ""
fi

# ── Summary ──────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════"
if [[ "$DRY_RUN" == true ]]; then
    echo "  Dry-run complete. No files were written."
else
    ACTUAL_COUNT=$(find "$POOL_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    echo "  Pool: $POOL_DIR ($ACTUAL_COUNT strategies)"
    [[ "$SKIP_ELO" != true ]] && echo "  Elo:  $ELO_DIR"
    [[ -f "$POOL_DIR/selection_report.json" ]] && echo "  Report: $POOL_DIR/selection_report.json"
    [[ -f "$ELO_DIR/elo_rankings.json" ]] && echo "  Rankings: $ELO_DIR/elo_rankings.json"
fi
echo "════════════════════════════════════════════════════════════════"
