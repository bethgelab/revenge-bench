"""Parity guard for RobotRumble probe trace parsing."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_PROBE_IMPL = (
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "robotrumble-gpt5-9aa3-v0"
    / "environment"
    / "run_probe_impl.py"
)


def _load_run_probe_impl():
    spec = importlib.util.spec_from_file_location("robotrumble_run_probe_impl", RUN_PROBE_IMPL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _robotrumble_probe_replay() -> dict:
    return {
        "winner": None,
        "errors": {},
        "turns": [
            {
                "turn": 1,
                "state": {
                    "turn": 1,
                    "objs": {
                        "b1": {
                            "obj_type": "Unit",
                            "type": "Soldier",
                            "team": "Blue",
                            "coords": [1, 1],
                            "health": 5,
                        },
                        "r1": {
                            "obj_type": "Unit",
                            "type": "Soldier",
                            "team": "Red",
                            "coords": [2, 1],
                            "health": 5,
                        },
                    },
                },
                "robot_actions": {
                    "b1": {"Ok": {"type": "Move", "direction": "East"}},
                    "r1": {"Ok": {"type": "Attack", "direction": "West"}},
                },
            }
        ],
    }


def test_robotrumble_probe_payload_matches_normal_path_parser_byte_identically():
    from revenge_bench.tournaments.inverse_strategy_interventionist import (
        InverseStrategyInterventionistTournament,
    )
    from revenge_bench.harbor.traces.parsers.robotrumble import build_probe_trace_payload

    probe_id = 11
    replay_name = "sim_0.json"
    replay = _robotrumble_probe_replay()
    arena = MagicMock()

    def execute(cmd: str):
        if cmd == "ls /logs/sim_*.json 2>/dev/null || echo 'NONE'":
            return {"output": f"/logs/{replay_name}\n", "returncode": 0}
        if cmd == f"cat /logs/{replay_name}":
            return {"output": json.dumps(replay), "returncode": 0}
        raise AssertionError(f"unexpected command: {cmd}")

    arena.environment.execute.side_effect = execute

    tournament = MagicMock(spec=InverseStrategyInterventionistTournament)
    tournament._parse_robotrumble_probe_traces = (
        InverseStrategyInterventionistTournament._parse_robotrumble_probe_traces.__get__(
            tournament
        )
    )

    normal_payload = tournament._parse_robotrumble_probe_traces(arena, probe_id)
    shared_payload = build_probe_trace_payload([(replay_name, replay)], probe_id)

    assert json.dumps(normal_payload, sort_keys=True) == json.dumps(
        shared_payload, sort_keys=True
    )


def test_robotrumble_probe_engine_failure_is_not_silent(tmp_path, monkeypatch):
    module = _load_run_probe_impl()

    class FailedProc:
        returncode = 17
        stderr = "engine exploded"

    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: FailedProc())

    with pytest.raises(RuntimeError, match="probe sim 2 failed with exit code 17"):
        module._run_simulation(["./rumblebot"], tmp_path / "sim.json", 2)


def test_robotrumble_probe_timeout_is_not_silent(tmp_path, monkeypatch):
    module = _load_run_probe_impl()

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=120)

    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="probe sim 0 timed out after 120s"):
        module._run_simulation(["./rumblebot"], tmp_path / "sim.json", 0)


def test_robotrumble_probe_invalid_json_is_not_silent(tmp_path, monkeypatch):
    module = _load_run_probe_impl()

    class OkProc:
        returncode = 0
        stderr = ""

    def fake_run(*args, **kwargs):
        kwargs["stdout"].write("not json")
        return OkProc()

    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="probe sim 1 produced invalid JSON"):
        module._run_simulation(["./rumblebot"], tmp_path / "sim.json", 1)


def test_robotrumble_probe_wrapper_returns_normal_style_json_error(monkeypatch, capsys):
    module = _load_run_probe_impl()

    def fail(_argv):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(module, "_run", fail)

    assert module.main(["run_probe_impl.py", "1", "3"]) == 0
    assert json.loads(capsys.readouterr().out) == {"error": "probe failed"}
