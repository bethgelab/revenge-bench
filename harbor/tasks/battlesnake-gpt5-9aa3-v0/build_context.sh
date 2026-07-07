#!/usr/bin/env bash
# Stage local assets into Harbor's Docker build context.
#
# revenge_bench is NOT published to PyPI, so the task image installs THIS
# working tree's code. Harbor builds with `environment/` as the Docker context,
# so every file referenced by the Dockerfile must be present under that
# directory before Harbor builds the image.
#
# Run this once before `harbor run` (or a direct `docker build`). Harbor may
# rebuild the image, but the staged files persist in the context until you
# rebuild them, so a single run here is enough per code change.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
WHEELS="$HERE/environment/wheels"
STAGING="$HERE/environment/staging"

rm -rf "$WHEELS" "$STAGING"
mkdir -p "$WHEELS" "$STAGING"

( cd "$REPO_ROOT" && uv build --wheel -o "$WHEELS" )
( cd "$REPO_ROOT" && uv run python -m revenge_bench.harbor.battlesnake_task stage "$HERE" )

echo "staged wheel(s) in $WHEELS:"
ls -1 "$WHEELS"
echo "staged task asset(s) in $STAGING:"
ls -1 "$STAGING"
