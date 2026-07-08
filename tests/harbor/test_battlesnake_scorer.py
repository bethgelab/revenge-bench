"""End-to-end test for the BattleSnake Harbor scorer.

Runs the scorer as a subprocess against synthetic frozen target traces, so it
exercises the real BattleSnake parser + the shared ``offline_eval`` scorer
exactly as the in-container verifier would. Requires ``zstandard`` (the only
import-time dep of the BattleSnake parser) to be installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCORER = (
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "battlesnake-gpt5-9aa3-v0"
    / "tests"
    / "score_task.py"
)
RUNNER = (
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "battlesnake-gpt5-9aa3-v0"
    / "tests"
    / "battlesnake_learner_runner.py"
)
SRC = REPO_ROOT / "src"

# Skip cleanly if the parser's import-time dep is missing in this environment.
zstandard = pytest.importorskip("zstandard")


def _turn(turn_num: int, head_x: int, head_y: int, name: str = "target") -> dict:
    """Minimal BattleSnake turn record the parser recognises (has 'board')."""
    snake = {
        "id": "s1",
        "name": name,
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


def _write_sim_moving_right(path: Path, name: str = "target") -> None:
    """Target moves right on every turn -> every inferred action is 'right'."""
    lines = [
        {"id": "game-1", "ruleset": {"name": "standard"}},  # metadata (no board)
        _turn(0, 0, 5, name),
        _turn(1, 1, 5, name),
        _turn(2, 2, 5, name),
        {"winnerName": name, "isDraw": False},  # results (no board)
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _run_scorer(tmp_path: Path, submission_src: str) -> dict:
    labels = tmp_path / "labels"
    labels.mkdir()
    _write_sim_moving_right(labels / "sim_0.jsonl")

    submission = tmp_path / "main.py"
    submission.write_text(submission_src)

    out_dir = tmp_path / "verifier"

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
            "--runner-user",
            "root" if getattr(os, "geteuid", lambda: -1)() == 0 else "agent",
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"scorer failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"

    eval_json = json.loads((out_dir / "eval.json").read_text())
    reward = (out_dir / "reward.txt").read_text().strip()
    eval_json["_reward_file"] = float(reward)
    return eval_json


def test_perfect_policy_scores_distance_zero(tmp_path: Path):
    payload = _run_scorer(tmp_path, "def move(state):\n    return 'right'\n")
    assert payload["mean_distance"] == 0.0
    assert payload["_reward_file"] == 1.0
    # Two consecutive-turn pairs -> two scored actions.
    assert payload["total_actions"] == 2
    assert payload["num_simulations"] == 1
    assert payload["game"] == "BattleSnake"
    assert payload["target"] == "target"
    assert payload["learner"] == "learner"
    assert payload["evaluation_type"] == "offline_artifact"


def test_wrong_policy_scores_distance_one(tmp_path: Path):
    payload = _run_scorer(tmp_path, "def move(state):\n    return 'up'\n")
    assert payload["mean_distance"] == 1.0
    assert payload["_reward_file"] == 0.0
    assert payload["total_actions"] == 2


def test_move_dict_return_is_unwrapped(tmp_path: Path):
    payload = _run_scorer(tmp_path, "def move(state):\n    return {'move': 'right'}\n")
    assert payload["mean_distance"] == 0.0
    assert payload["_reward_file"] == 1.0


def test_choose_move_entrypoint_supported(tmp_path: Path):
    payload = _run_scorer(tmp_path, "def choose_move(state):\n    return 'right'\n")
    assert payload["mean_distance"] == 0.0
    assert payload["_reward_file"] == 1.0


def test_unloadable_policy_yields_error_zero_reward(tmp_path: Path):
    payload = _run_scorer(tmp_path, "this is not valid python !!!\n")
    assert payload["_reward_file"] == 0.0
    assert payload["mean_distance"] == float("inf")
    assert payload["skipped_none_actions"] == payload["expected_actions"]


def test_missing_entrypoint_yields_error(tmp_path: Path):
    payload = _run_scorer(tmp_path, "def not_a_move(state):\n    return 'right'\n")
    assert payload["_reward_file"] == 0.0
    assert payload["mean_distance"] == float("inf")
    assert payload["skipped_none_actions"] == payload["expected_actions"]


def _load_score_task_module():
    """Import score_task.py by path (it lives outside the installed package)."""
    import importlib.util

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location("_score_task_under_test", SCORER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_action_artifact_logs_are_separate_from_score(tmp_path: Path):
    payload = _run_scorer(tmp_path, "def move(state):\n    print('noise')\n    return 'right'\n")
    assert payload["mean_distance"] == 0.0
    out_dir = tmp_path / "verifier"
    assert (out_dir / "learner-runner.stdout").read_text() == ""
    assert "noise" in (out_dir / "learner-runner.stderr").read_text()
