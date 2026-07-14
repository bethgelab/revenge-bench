#!/usr/bin/env bash
# RevengeBench HuskyBench Harbor verifier entrypoint.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONDONTWRITEBYTECODE || true
export PYTHONNOUSERSITE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${REWARD_DIR:-/logs/verifier}"
LABEL_DIR="${REVENGE_LABEL_DIR:-/run/verifier_labels/rounds/1}"
mkdir -p "$OUT_DIR"

chmod -R a-w "$HERE" 2>/dev/null || true

rm -rf /run/verifier_labels
mkdir -p "$(dirname "$LABEL_DIR")"
HUSKYBENCH_TRACE_OUT="$LABEL_DIR" \
HUSKYBENCH_TRACE_SOURCE=harbor-verifier \
python3 -I /opt/huskybench/generate_round_traces.py
chown -R root:root /run/verifier_labels
chmod -R go-rwx /run/verifier_labels

python3 -I /opt/huskybench/score_huskybench_submission.py \
  --submission /workspace/client/player.py \
  --labels "$LABEL_DIR" \
  --round "${REVENGE_ROUND:-1}" \
  --out-dir "$OUT_DIR" \
  --target-name target \
  --learner-name learner

if [[ ! -f "$OUT_DIR/reward.txt" ]]; then
  echo "0.0" > "$OUT_DIR/reward.txt"
fi

echo "reward=$(cat "$OUT_DIR/reward.txt")"
