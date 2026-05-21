#!/bin/bash
# Run the Bayesian Program Inference baseline across configured models and games.
# Usage:
#   bash scripts/run_bpi.sh [--seeds "42 100"] [--dry-run] [--resume] [--parallel N]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$REPO_ROOT/scripts/run_pool.sh" \
    --config-dir configs/baselines/bpi \
    "$@"
