"""Shared JS-evaluation helper for RobotRumble traces.

Runs the learner's robot.js inside a Node.js sandbox container, feeding
JSON state lines via stdin and reading actions back from stdout. Picks
the container runtime (docker | singularity/apptainer) based on
``CODECLASH_RUNTIME``.
"""
from __future__ import annotations

import os
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path

NODE_DOCKER_IMAGE = "node:18-alpine"

# SIF lives next to the harness JS assets so it ships with the parsers/
# directory and isn't recomputed per-tournament.
NODE_SIF_PATH = (
    Path(__file__).resolve().parent.parent
    / "traces" / "parsers" / "node-18-alpine.sif"
)


@dataclass
class JsEvalResult:
    """Result of a single JS-eval invocation."""
    stdout: str = ""
    returncode: int = 0
    error: str | None = None


def _runtime() -> str:
    return os.environ.get("CODECLASH_RUNTIME", "docker").lower()


def _ensure_node_sif() -> None:
    """Build node:18-alpine.sif on first use; idempotent."""
    if NODE_SIF_PATH.exists():
        return
    NODE_SIF_PATH.parent.mkdir(parents=True, exist_ok=True)
    builder = shutil.which("singularity") or shutil.which("apptainer")
    if builder is None:
        raise RuntimeError(
            "Neither singularity nor apptainer found on PATH; cannot build "
            f"{NODE_SIF_PATH} for RobotRumble JS evaluation."
        )
    # Build into a per-process temp file then atomically rename, so
    # concurrent callers neither corrupt each other's tmp file nor see a
    # half-built final SIF. Worst case is duplicated work; correctness is
    # preserved because os.replace is atomic on POSIX.
    tmp = NODE_SIF_PATH.with_suffix(f".sif.tmp.{os.getpid()}")
    cmd = [builder, "build", "--fakeroot", str(tmp), f"docker://{NODE_DOCKER_IMAGE}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to build {NODE_SIF_PATH}:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    os.replace(tmp, NODE_SIF_PATH)


def run_js_eval(
    harness_js: Path,
    stdlib_js: Path,
    lodash_js: Path,
    robot_js: Path,
    *,
    payload: str,
    timeout: int = 120,
) -> JsEvalResult:
    """Run the RobotRumble JS harness on stdin payload, return JsEvalResult.

    All four JS file paths are bind-mounted read-only into the container at
    /eval/{harness,stdlib,robot,lodash}.js, then ``node /eval/harness.js
    /eval/stdlib.js /eval/robot.js /eval/lodash.js`` is invoked with the
    payload piped to stdin.
    """
    runtime = _runtime()

    if runtime in ("singularity", "apptainer"):
        _ensure_node_sif()
        executable = shutil.which("singularity") or shutil.which("apptainer")
        cmd: list[str] = [
            executable, "exec",
            "--contain", "--cleanenv",
            "--bind", f"{harness_js}:/eval/harness.js:ro",
            "--bind", f"{stdlib_js}:/eval/stdlib.js:ro",
            "--bind", f"{lodash_js}:/eval/lodash.js:ro",
            "--bind", f"{robot_js}:/eval/robot.js:ro",
            str(NODE_SIF_PATH),
            "node",
            "/eval/harness.js", "/eval/stdlib.js",
            "/eval/robot.js", "/eval/lodash.js",
        ]
    else:
        cmd = [
            "docker", "run", "--rm", "-i",
            "-v", f"{harness_js}:/eval/harness.js:ro",
            "-v", f"{stdlib_js}:/eval/stdlib.js:ro",
            "-v", f"{lodash_js}:/eval/lodash.js:ro",
            "-v", f"{robot_js}:/eval/robot.js:ro",
            NODE_DOCKER_IMAGE, "node",
            "/eval/harness.js", "/eval/stdlib.js",
            "/eval/robot.js", "/eval/lodash.js",
        ]

    try:
        proc = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return JsEvalResult(returncode=124, error=f"JS evaluation timed out after {timeout}s")

    return JsEvalResult(
        stdout=proc.stdout,
        returncode=proc.returncode,
        error=proc.stderr if proc.returncode != 0 else None,
    )
