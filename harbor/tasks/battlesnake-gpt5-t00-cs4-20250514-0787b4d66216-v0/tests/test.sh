#!/usr/bin/env bash
# RevengeBench BattleSnake (Tier I) Harbor verifier entrypoint.
#
# Harbor mounts this tests/ directory at scoring time. It runs as root and:
#   1. hardens PATH / clears inherited PYTHON* vars (anti import-hijack),
#   2. generates fresh root-only target-vs-opponent traces, matching the normal
#      post-edit round timing,
#   3. leaves eval.json + reward.txt under /logs/verifier for Harbor to read.
#
# The learner can read /workspace/rounds/0 from the start of the task, matching
# the normal BattleSnake path where prior target-vs-opponent traces are evidence.
# Opponent source is sealed under /opt/revengebench/opponents.
set -euo pipefail

# --- Hardening: deterministic PATH, no inherited interpreter hijacking --------
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONDONTWRITEBYTECODE || true
export PYTHONNOUSERSITE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${REWARD_DIR:-/logs/verifier}"
LABEL_DIR="${REVENGE_LABEL_DIR:-/run/verifier_labels/rounds/1}"
mkdir -p "$OUT_DIR"

# Make the verifier's own files read-only so a compromised run can't rewrite
# the scorer or labels mid-flight.
chmod -R a-w "$HERE" 2>/dev/null || true

# Fresh hidden labels: same target and opponent pool as the visible round-0
# evidence, but regenerated after the learner finishes. Keep them root-only.
rm -rf /run/verifier_labels /run/verifier_label_arena
mkdir -p "$(dirname "$LABEL_DIR")"
BATTLESNAKE_TRACE_OUT="$LABEL_DIR" \
BATTLESNAKE_TRACE_ARENA=/run/verifier_label_arena \
BATTLESNAKE_TRACE_SOURCE=harbor-verifier \
python3 -I /opt/battlesnake/generate_round_traces.py
chown -R root:root /run/verifier_labels
chmod -R go-rwx /run/verifier_labels

# The scorer runs as trusted root so it can read hidden labels. It never imports
# learner code directly; score_task.py launches /workspace/main.py as `agent`
# through a JSONL subprocess runner.
python3 -I "$HERE/score_task.py" \
  --submission /workspace/main.py \
  --labels "$LABEL_DIR" \
  --target-name target \
  --round "${REVENGE_ROUND:-1}" \
  --runner "$HERE/battlesnake_learner_runner.py" \
  --runner-user "${REVENGE_LEARNER_USER:-agent}" \
  --out-dir "$OUT_DIR"

# Ensure a reward exists even if the scorer somehow exited without writing one.
if [[ ! -f "$OUT_DIR/reward.txt" ]]; then
  echo "0.0" > "$OUT_DIR/reward.txt"
fi

echo "reward=$(cat "$OUT_DIR/reward.txt")"
