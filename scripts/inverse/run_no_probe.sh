#!/bin/bash
# Run the trace-only no-probe benchmark condition across configured models and games.
# Usage:
#   bash scripts/inverse/run_no_probe.sh [--seeds "42 100"] [--dry-run] [--resume] [--parallel N]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$REPO_ROOT/scripts/inverse/run_pool.sh" \
    --config-dir configs/inverse/conditions/no_probe \
    "$@"
