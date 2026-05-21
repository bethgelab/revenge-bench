#!/usr/bin/env bash
#
# revenge-codex-exec — wrapper around `codex exec` for RevengeBench
# tournaments. Baked into the Codex-enabled arena image at
# /usr/local/bin/revenge-codex-exec (see <Game>.codex.Dockerfile).
#
# Responsibilities:
# 1. Launch `codex exec` with all forwarded args (the agent decides the
#    full argv — model, sandbox, output-last-message, etc.).
# 2. Poll for a submission marker written by the MCP `submit` tool. When
#    seen: wait a short grace period, then SIGTERM, then SIGKILL.
#    Lets Codex finish its current tool call cleanly when possible.
# 3. Optional overall wall-clock cap: SIGTERM/SIGKILL after MAX_SECS.
# 4. Always exits with codex's own returncode (or 124 on timeout).
#
# Configuration (env vars, all optional):
#
#   REVENGE_CODEX_MARKER          path to submit marker file
#                                 (default /workspace/.revenge_bench/submitted.json)
#   REVENGE_CODEX_GRACE_SECS      seconds to wait after marker before
#                                 SIGTERM (default 8)
#   REVENGE_CODEX_KILL_GRACE_SECS seconds after SIGTERM before SIGKILL
#                                 (default 5)
#   REVENGE_CODEX_MAX_SECS        hard wall-clock cap; 0 disables
#                                 (default 0)
#
# Codex itself reads its own env vars (CODEX_HOME, OPENAI_API_KEY, MCP
# config, etc.); this wrapper does not touch them.
#
# Exit codes:
#   <codex's exit code>  on natural completion or marker-driven shutdown
#   124                  on wall-clock timeout (matches GNU `timeout`)

set -uo pipefail

readonly MARKER="${REVENGE_CODEX_MARKER:-/workspace/.revenge_bench/submitted.json}"
readonly GRACE_SECS="${REVENGE_CODEX_GRACE_SECS:-8}"
readonly KILL_GRACE_SECS="${REVENGE_CODEX_KILL_GRACE_SECS:-5}"
readonly MAX_SECS="${REVENGE_CODEX_MAX_SECS:-0}"

# Find codex on PATH; allow override for testing via REVENGE_CODEX_BIN.
readonly CODEX_BIN="${REVENGE_CODEX_BIN:-codex}"

# We never want a stale marker from the previous round. Caller (Python
# adapter) also rm's it, but we double-check before launching codex.
rm -f -- "$MARKER" 2>/dev/null || true

# Launch codex in its own process group so we can signal the whole tree.
# Linux containers always have `setsid`; on macOS (test/dev only) we
# fall back to a plain background job and signal the codex pid directly.
#
# `<&0` is required: bash redirects a backgrounded command's stdin to
# /dev/null in non-interactive scripts (job control off). Without it,
# codex reads EOF immediately and reports "No prompt provided via stdin"
# even though the helper itself has the round prompt on its stdin.
if command -v setsid >/dev/null 2>&1; then
  setsid "$CODEX_BIN" "$@" <&0 &
  CODEX_PID=$!
  KILL_TARGET="-$CODEX_PID"  # negative = process-group target
else
  "$CODEX_BIN" "$@" <&0 &
  CODEX_PID=$!
  KILL_TARGET="$CODEX_PID"
fi

# --- Background watcher: marker → graceful shutdown ----------------
# Subshells redirect their own stdio to /dev/null so the parent script's
# pipes can close as soon as the parent exits — otherwise Popen-style
# callers wait on the subshells holding stdout/stderr open.
(
  while kill -0 "$CODEX_PID" 2>/dev/null; do
    if [[ -f "$MARKER" ]]; then
      sleep "$GRACE_SECS"
      kill -TERM -- "$KILL_TARGET" 2>/dev/null || true
      sleep "$KILL_GRACE_SECS"
      kill -KILL -- "$KILL_TARGET" 2>/dev/null || true
      exit 0
    fi
    sleep 1
  done
) </dev/null >/dev/null 2>&1 &
WATCHER_PID=$!

# --- Background timeout: hard cap ----------------------------------
TIMEOUT_PID=""
TIMEOUT_FILE=""
if [[ "$MAX_SECS" -gt 0 ]]; then
  # mktemp creates the file empty, so existence-only checks would
  # always be true; use file *content* as the "timeout fired" sentinel.
  TIMEOUT_FILE="$(mktemp -t revenge-codex-timeout.XXXXXX)"
  (
    sleep "$MAX_SECS"
    if kill -0 "$CODEX_PID" 2>/dev/null; then
      # Non-empty content = timeout fired.
      echo "fired" > "$TIMEOUT_FILE"
      kill -TERM -- "$KILL_TARGET" 2>/dev/null || true
      sleep "$KILL_GRACE_SECS"
      kill -KILL -- "$KILL_TARGET" 2>/dev/null || true
    fi
  ) </dev/null >/dev/null 2>&1 &
  TIMEOUT_PID=$!
fi

# --- Wait for codex; capture its returncode ------------------------
wait "$CODEX_PID"
CODEX_RC=$?

# Tear down background helpers (idempotent; ignore errors).
kill "$WATCHER_PID" 2>/dev/null || true
[[ -n "$TIMEOUT_PID" ]] && kill "$TIMEOUT_PID" 2>/dev/null || true

# Map a fired wall-clock timeout to the conventional 124 so the agent
# can distinguish "codex chose to exit with rc=N" from "we killed it".
# `-s` checks for non-empty content; mktemp pre-created the file empty.
if [[ -n "$TIMEOUT_FILE" && -s "$TIMEOUT_FILE" ]]; then
  rm -f -- "$TIMEOUT_FILE"
  exit 124
fi
[[ -n "$TIMEOUT_FILE" ]] && rm -f -- "$TIMEOUT_FILE"

exit "$CODEX_RC"
