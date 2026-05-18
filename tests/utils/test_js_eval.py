import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from revenge_bench.utils.js_eval import run_js_eval, NODE_SIF_PATH, NODE_DOCKER_IMAGE


def _fake_proc(stdout="", returncode=0):
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


def test_run_js_eval_uses_docker_when_runtime_is_docker(tmp_path, monkeypatch):
    monkeypatch.delenv("CODECLASH_RUNTIME", raising=False)  # default = docker
    harness = tmp_path / "h.js"; harness.write_text("")
    stdlib = tmp_path / "s.js"; stdlib.write_text("")
    lodash = tmp_path / "l.js"; lodash.write_text("")
    robot = tmp_path / "r.js"; robot.write_text("")

    with patch("revenge_bench.utils.js_eval.subprocess.run", return_value=_fake_proc("ok\n")) as m:
        result = run_js_eval(harness, stdlib, lodash, robot, payload="x\n", timeout=5)

    assert result.returncode == 0
    cmd = m.call_args[0][0]
    assert cmd[0] == "docker"
    assert cmd[1] == "run"
    assert NODE_DOCKER_IMAGE in cmd  # "node:18-alpine"
    # Docker bind-mounts use -v src:dst:ro
    assert any("-v" == c for c in cmd)


def test_run_js_eval_uses_singularity_when_runtime_is_singularity(tmp_path, monkeypatch):
    monkeypatch.setenv("CODECLASH_RUNTIME", "singularity")
    harness = tmp_path / "h.js"; harness.write_text("")
    stdlib = tmp_path / "s.js"; stdlib.write_text("")
    lodash = tmp_path / "l.js"; lodash.write_text("")
    robot = tmp_path / "r.js"; robot.write_text("")

    # Pre-create the SIF so the helper doesn't try to build it.
    NODE_SIF_PATH.parent.mkdir(parents=True, exist_ok=True)
    NODE_SIF_PATH.touch()

    # Stub shutil.which so the test runs on hosts (e.g. cluster login nodes)
    # where neither singularity nor apptainer is on PATH.
    def _fake_which(name):
        if name in ("singularity", "apptainer"):
            return f"/usr/bin/{name}"
        return None

    try:
        with patch("revenge_bench.utils.js_eval.shutil.which", side_effect=_fake_which), \
             patch("revenge_bench.utils.js_eval.subprocess.run", return_value=_fake_proc("ok\n")) as m:
            result = run_js_eval(harness, stdlib, lodash, robot, payload="x\n", timeout=5)
    finally:
        NODE_SIF_PATH.unlink(missing_ok=True)

    assert result.returncode == 0
    cmd = m.call_args[0][0]
    # cmd[0] may be a full path (e.g. /usr/bin/singularity) returned by shutil.which
    assert cmd[0].endswith("singularity") or cmd[0].endswith("apptainer")
    assert "exec" in cmd
    # Singularity bind-mounts use --bind src:dst:ro
    assert any("--bind" == c for c in cmd)
    assert str(NODE_SIF_PATH) in cmd


def test_run_js_eval_returns_error_on_timeout(tmp_path, monkeypatch):
    monkeypatch.delenv("CODECLASH_RUNTIME", raising=False)
    harness = tmp_path / "h.js"; harness.write_text("")
    stdlib = tmp_path / "s.js"; stdlib.write_text("")
    lodash = tmp_path / "l.js"; lodash.write_text("")
    robot = tmp_path / "r.js"; robot.write_text("")

    import subprocess as sp
    with patch(
        "revenge_bench.utils.js_eval.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd="x", timeout=1),
    ):
        result = run_js_eval(harness, stdlib, lodash, robot, payload="x\n", timeout=1)
    assert result.returncode != 0
    assert "timed out" in (result.error or "").lower()
