"""End-to-end test for the BattleSnake probe trace parser used by run_probe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PARSER = (
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "battlesnake-gpt5-9aa3-v0"
    / "environment"
    / "parse_probe_traces.py"
)
SRC = REPO_ROOT / "src"

pytest.importorskip("zstandard")


def _snake(name: str, x: int, y: int) -> dict:
    return {"id": name, "name": name, "health": 100, "body": [{"x": x, "y": y}], "head": {"x": x, "y": y}, "length": 1}


def _turn(turn_num: int, probe_xy: tuple[int, int], target_xy: tuple[int, int]) -> dict:
    snakes = [_snake("probe", *probe_xy), _snake("target", *target_xy)]
    return {"turn": turn_num, "board": {"height": 11, "width": 11, "snakes": snakes, "food": [], "hazards": []}}


def _write_sim(path: Path) -> None:
    # probe moves right each turn; target moves up each turn -> every pair differs.
    lines = [
        {"id": "g", "ruleset": {"name": "standard"}},
        _turn(0, (0, 0), (5, 0)),
        _turn(1, (1, 0), (5, 1)),
        _turn(2, (2, 0), (5, 2)),
        {"winnerName": None, "isDraw": True},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _run_parser(tmp_path: Path, remaining: str = "4") -> dict:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_sim(logs / "sim_0.jsonl")
    out = tmp_path / "probe_trace_1.json"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.run(
        [sys.executable, str(PARSER), str(logs), str(out), "1", remaining],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"parser failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
    return json.loads(out.read_text())


def test_probe_pairs_capture_target_and_probe_actions(tmp_path: Path):
    payload = _run_parser(tmp_path)
    assert payload["probe_id"] == 1
    assert payload["num_simulations"] == 1
    assert payload["total_turns"] == 2  # two consecutive-turn transitions
    assert payload["probes_remaining"] == 4
    pairs = payload["pairs"]
    assert len(pairs) == 2
    for p in pairs:
        assert p["probe_action"] == "right"
        assert p["target_action"] == "up"
        assert p["distance"] == 1.0
        # target_state must be exposed (states/actions), but never target source.
        assert p["target_state"]["you"]["name"] == "target"


def test_probes_remaining_null_passthrough(tmp_path: Path):
    payload = _run_parser(tmp_path, remaining="null")
    assert payload["probes_remaining"] is None


def test_no_sim_files_reports_error(tmp_path: Path):
    logs = tmp_path / "logs"
    logs.mkdir()
    out = tmp_path / "probe_trace_1.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(PARSER), str(logs), str(out), "1", "null"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0
    payload = json.loads(out.read_text())
    assert payload.get("error")
