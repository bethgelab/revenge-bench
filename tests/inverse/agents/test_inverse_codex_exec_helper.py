"""End-to-end shell tests for scripts/codex/inverse-codex-exec.sh.

Exercises the three exit paths:
- natural completion: rc passthrough,
- submit marker: graceful SIGTERM shutdown after grace period,
- wall-clock timeout: returns 124 (GNU `timeout` convention).

Skipped on Windows; relies on a POSIX shell + bash. macOS lacks
`setsid` but the helper has a fallback path for that case.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "scripts" / "codex" / "inverse-codex-exec.sh"


pytestmark = pytest.mark.skipif(
    not shutil.which("bash"),
    reason="inverse-codex-exec.sh needs a POSIX bash shell",
)


def _run_helper(env: dict, *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Invoke the helper with the given env, return CompletedProcess."""
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        ["bash", str(HELPER)],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_fake_codex(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    path.chmod(0o755)
    return path


class TestNaturalCompletion:
    def test_passes_through_codex_returncode_zero(self, tmp_path):
        fake = _write_fake_codex(
            tmp_path / "fake_codex.sh",
            'echo ok; exit 0\n',
        )
        result = _run_helper({
            "INVERSE_CODEX_BIN": str(fake),
            "INVERSE_CODEX_MARKER": str(tmp_path / "never.json"),
        })
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_passes_through_codex_returncode_nonzero(self, tmp_path):
        fake = _write_fake_codex(
            tmp_path / "fake_codex.sh",
            'exit 7\n',
        )
        result = _run_helper({
            "INVERSE_CODEX_BIN": str(fake),
            "INVERSE_CODEX_MARKER": str(tmp_path / "never.json"),
        })
        assert result.returncode == 7

    def test_forwards_argv_to_codex(self, tmp_path):
        fake = _write_fake_codex(
            tmp_path / "fake_codex.sh",
            'printf "ARGS:%s\\n" "$@"; exit 0\n',
        )
        # We can only set env, so use a wrapper to forward args.
        result = subprocess.run(
            ["bash", str(HELPER), "--model", "test-model", "extra-arg"],
            env={**os.environ, "INVERSE_CODEX_BIN": str(fake),
                 "INVERSE_CODEX_MARKER": str(tmp_path / "never.json")},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "ARGS:--model" in result.stdout
        assert "ARGS:test-model" in result.stdout
        assert "ARGS:extra-arg" in result.stdout


class TestMarkerShutdown:
    def test_marker_triggers_graceful_termination(self, tmp_path):
        marker = tmp_path / "marker.json"
        # `exec sleep` so the fake codex *is* the sleep process — without
        # this, killing the bash wrapper would orphan the child sleep,
        # which keeps stdout/stderr pipes open and stalls the parent.
        # Production codex on Linux doesn't have this issue (setsid +
        # pgroup kill); the exec idiom keeps the test portable.
        fake = _write_fake_codex(
            tmp_path / "fake_codex.sh",
            'echo "fake codex pid $$"\nexec sleep 30\n',
        )

        # Background thread to write the marker after a delay.
        def write_marker_later():
            time.sleep(1.0)
            marker.write_text("{}")

        import threading
        t = threading.Thread(target=write_marker_later)
        t.start()

        start = time.monotonic()
        result = _run_helper(
            {
                "INVERSE_CODEX_BIN": str(fake),
                "INVERSE_CODEX_MARKER": str(marker),
                "INVERSE_CODEX_GRACE_SECS": "1",
                "INVERSE_CODEX_KILL_GRACE_SECS": "1",
            },
            timeout=15,
        )
        elapsed = time.monotonic() - start
        t.join()

        # marker at t=1, grace=1, total ~2-3s; well under 30s natural runtime.
        assert elapsed < 8, f"helper took {elapsed:.1f}s; expected ~2-3s"
        # rc=143 (SIGTERM) is the typical outcome; SIGKILL gives 137.
        # Either signals correct shutdown.
        assert result.returncode in (143, 137), (
            f"unexpected rc={result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


class TestWallClockTimeout:
    def test_returns_124_on_timeout(self, tmp_path):
        fake = _write_fake_codex(
            tmp_path / "fake_codex.sh",
            "exec sleep 30\n",  # see comment in TestMarkerShutdown
        )
        start = time.monotonic()
        result = _run_helper(
            {
                "INVERSE_CODEX_BIN": str(fake),
                "INVERSE_CODEX_MARKER": str(tmp_path / "never.json"),
                "INVERSE_CODEX_MAX_SECS": "2",
                "INVERSE_CODEX_KILL_GRACE_SECS": "1",
            },
            timeout=10,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 6, f"helper took {elapsed:.1f}s"
        assert result.returncode == 124

    def test_marker_beats_timeout_when_both_fire(self, tmp_path):
        """If marker is written before MAX_SECS, helper should exit via
        marker path (rc=143) rather than waiting for timeout (rc=124)."""
        marker = tmp_path / "marker.json"
        fake = _write_fake_codex(
            tmp_path / "fake_codex.sh",
            "exec sleep 30\n",  # see comment in TestMarkerShutdown
        )

        def write_marker_later():
            time.sleep(0.5)
            marker.write_text("{}")

        import threading
        t = threading.Thread(target=write_marker_later)
        t.start()

        result = _run_helper(
            {
                "INVERSE_CODEX_BIN": str(fake),
                "INVERSE_CODEX_MARKER": str(marker),
                "INVERSE_CODEX_GRACE_SECS": "1",
                "INVERSE_CODEX_KILL_GRACE_SECS": "1",
                "INVERSE_CODEX_MAX_SECS": "10",
            },
            timeout=15,
        )
        t.join()
        assert result.returncode in (143, 137), (
            f"unexpected rc={result.returncode}"
        )
