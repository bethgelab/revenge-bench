from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCORER = REPO_ROOT / "harbor" / "tasks" / "battlesnake-gpt5-9aa3-v0" / "tests" / "score_task.py"
RUNNER = REPO_ROOT / "harbor" / "tasks" / "battlesnake-gpt5-9aa3-v0" / "tests" / "battlesnake_learner_runner.py"
SRC = REPO_ROOT / "src"

pytest.importorskip("zstandard")


def _turn(turn_num: int, head_x: int, head_y: int) -> dict:
    snake = {
        "id": "s1",
        "name": "target",
        "health": 100,
        "body": [{"x": head_x, "y": head_y}],
        "head": {"x": head_x, "y": head_y},
        "length": 1,
    }
    return {
        "turn": turn_num,
        "board": {"height": 11, "width": 11, "snakes": [snake], "food": [], "hazards": []},
        "you": snake,
    }


def test_gpt5_harbor_scorer_queries_learner_via_artifact(tmp_path: Path):
    if getattr(os, "geteuid", lambda: -1)() == 0:
        pytest.skip("root test process would not exercise the unprivileged runner boundary")

    labels = tmp_path / "labels"
    labels.mkdir()
    lines = [
        {"id": "game-1", "ruleset": {"name": "standard"}},
        _turn(0, 0, 5),
        _turn(1, 1, 5),
        _turn(2, 2, 5),
        {"winnerName": "target", "isDraw": False},
    ]
    (labels / "sim_0.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")

    submission = tmp_path / "main.py"
    submission.write_text("def move(state):\n    return {'move': 'right'}\n")
    out_dir = tmp_path / "out"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCORER),
            "--submission",
            str(submission),
            "--labels",
            str(labels),
            "--target-name",
            "target",
            "--runner",
            str(RUNNER),
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads((out_dir / "eval.json").read_text())
    assert payload["evaluation_type"] == "offline_artifact"
    assert payload["mean_distance"] == 0.0
    assert float((out_dir / "reward.txt").read_text()) == 1.0
