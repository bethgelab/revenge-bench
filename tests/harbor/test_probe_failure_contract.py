from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "harbor" / "tasks"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shell_probe_errors_return_json_stdout_without_failure_exit():
    cases = {
        "battlesnake-gpt5-9aa3-v0": [
            '{"error": "Probe budget exhausted',
            '{"error": "No probe bot found at /workspace/probe.py"}',
            '{"error": "Sealed target not found in container"}',
            '{"error": "Probe/target servers did not start in time"}',
        ],
        "halite-gpt5-9aa3-v0": [
            '{"error": "probe budget missing"}',
            '{"error": "probe budget exhausted"}',
        ],
        "robotrumble-gpt5-9aa3-v0": [
            '{"error": "probe budget file missing"}',
            '{"error": "probe budget exhausted"}',
        ],
    }

    for task, snippets in cases.items():
        text = (TASKS / task / "environment" / "run_probe").read_text()
        for snippet in snippets:
            assert snippet in text

    for task in cases:
        text = (TASKS / task / "environment" / "run_probe").read_text()
        assert 'echo "probe budget' not in text
        assert "exit 2" not in text
        assert "exit 3" not in text


def test_python_probe_impl_exceptions_match_normal_json_error_contract(monkeypatch, capsys):
    modules = [
        (
            TASKS / "huskybench-gpt5-9aa3-v0" / "environment" / "run_probe_impl.py",
            "huskybench_probe_contract",
        ),
        (
            TASKS / "robocode-gpt5-9aa3-v0" / "environment" / "run_probe_impl.py",
            "robocode_probe_contract",
        ),
        (
            TASKS / "robotrumble-gpt5-9aa3-v0" / "environment" / "run_probe_impl.py",
            "robotrumble_probe_contract",
        ),
    ]

    for path, name in modules:
        module = _load_module(path, name)

        def fail(_argv):
            raise RuntimeError(f"{name} failed")

        entrypoint = "_run" if hasattr(module, "_run") else "main"
        monkeypatch.setattr(module, entrypoint, fail)

        assert module.main(["run_probe_impl.py", "1", "3"]) == 0
        assert json.loads(capsys.readouterr().out) == {"error": f"{name} failed"}
