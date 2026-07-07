#!/usr/bin/env bash
# Stage local assets into Harbor's Docker build context.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
WHEELS="$HERE/environment/wheels"
STAGING="$HERE/environment/staging"

rm -rf "$WHEELS" "$STAGING"
mkdir -p "$WHEELS" "$STAGING"

( cd "$REPO_ROOT" && uv build --wheel -o "$WHEELS" )
( cd "$REPO_ROOT" && uv run python -m revenge_bench.harbor.prompt robocode-gpt5-9aa3-v0 )
( cd "$REPO_ROOT" && uv run python -m revenge_bench.harbor.robocode_task stage "$HERE" )

echo "staged wheel(s) in $WHEELS:"
ls -1 "$WHEELS"
echo "staged task asset(s) in $STAGING:"
ls -1 "$STAGING"
