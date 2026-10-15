from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BATTLE_SCORE = _load_module(
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "battlesnake-gpt5-9aa3-v0"
    / "tests"
    / "score_task.py",
    "battlesnake_score_task",
)
ROBO_SCORE = _load_module(
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "robocode-gpt5-9aa3-v0"
    / "environment"
    / "score_robocode_submission.py",
    "robocode_score_task",
)
HUSKY_SCORE = _load_module(
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "huskybench-gpt5-9aa3-v0"
    / "environment"
    / "score_huskybench_submission.py",
    "huskybench_score_task",
)
HALITE_SCORE = _load_module(
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "halite-gpt5-9aa3-v0"
    / "environment"
    / "score_halite_submission.py",
    "halite_score_task",
)
ROBOTRUMBLE_SCORE = _load_module(
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "robotrumble-gpt5-9aa3-v0"
    / "environment"
    / "score_robotrumble_submission.py",
    "robotrumble_score_task",
)


ACTION_READERS = [
    BATTLE_SCORE._read_actions,
    ROBO_SCORE._read_actions,
    HUSKY_SCORE._read_actions,
    ROBOTRUMBLE_SCORE._read_actions,
]


PROVIDERS = [
    BATTLE_SCORE.BattleSnakeArtifactMoveProvider,
    ROBO_SCORE.RoboCodeArtifactMoveProvider,
    HUSKY_SCORE.HuskyBenchArtifactActionProvider,
]


def test_artifact_provider_returns_actions_in_order():
    for provider_cls in PROVIDERS:
        provider = provider_cls(["right", None, {"turn_radar": 1.0}])
        assert provider({"turn": 1}) == "right"
        assert provider({"turn": 2}) is None
        assert provider({"turn": 3}) == {"turn_radar": 1.0}
        assert provider({"turn": 4}) is None


def test_artifact_action_reader_good_and_missing_action(tmp_path: Path):
    actions_path = tmp_path / "actions.jsonl"
    actions_path.write_text(
        json.dumps({"id": 0, "action": "right"}) + "\n"
        + json.dumps({"id": 2, "status": "ok"}) + "\n"
    )
    for reader in ACTION_READERS:
        assert reader(actions_path, 3) == ["right", None, None]


def test_artifact_action_reader_malformed_json(tmp_path: Path):
    actions_path = tmp_path / "actions.jsonl"
    actions_path.write_text(
        "not-json\n"
        + json.dumps({"id": 1, "action": "left"}) + "\n"
    )
    for reader in ACTION_READERS:
        assert reader(actions_path, 3) == [None, "left", None]


def test_artifact_action_reader_crashing_learner_missing_file(tmp_path: Path):
    missing = tmp_path / "missing-actions.jsonl"
    for reader in ACTION_READERS:
        assert reader(missing, 2) == [None, None]


def test_halite_artifact_action_reader_and_provider(tmp_path: Path):
    actions_path = tmp_path / "halite-actions.jsonl"
    batch = [[[0, 1, 2]]]
    actions_path.write_text(json.dumps({"id": 0, "actions": batch}) + "\n")
    assert HALITE_SCORE._read_action_batches(actions_path, 2) == [batch, []]

    provider = HALITE_SCORE.HaliteArtifactActionProvider([batch])
    assert provider({}, 1) == batch
    assert provider({}, 1) == []


def test_robocode_runner_writes_artifact_and_suppresses_noisy_stdout(tmp_path: Path):
    runner = (
        REPO_ROOT
        / "harbor"
        / "tasks"
        / "robocode-gpt5-9aa3-v0"
        / "environment"
        / "robocode_learner_runner.py"
    )
    submission = tmp_path / "main.py"
    submission.write_text(
        "print('import noise')\n"
        "def move(state):\n"
        "    print('move noise')\n"
        "    return {'turn_radar': 1.0}\n"
    )
    queries = tmp_path / "queries.jsonl"
    actions = tmp_path / "actions.jsonl"
    queries.write_text(json.dumps({"id": 0, "state": {"turn": 1}}) + "\n")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [
            sys.executable,
            str(runner),
            "--submission",
            str(submission),
            "--queries",
            str(queries),
            "--actions",
            str(actions),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert "import noise" in proc.stderr
    assert "move noise" in proc.stderr
    assert [json.loads(line) for line in actions.read_text().splitlines()] == [
        {"id": 0, "action": {"turn_radar": 1.0}}
    ]
