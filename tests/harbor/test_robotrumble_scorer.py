from __future__ import annotations

import importlib.util
import json
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCORER = (
    REPO_ROOT
    / "harbor"
    / "tasks"
    / "robotrumble-gpt5-9aa3-v0"
    / "environment"
    / "score_robotrumble_submission.py"
)


def _load_scorer():
    spec = importlib.util.spec_from_file_location("robotrumble_scorer_under_test", SCORER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_robotrumble_labels(round_dir: Path) -> None:
    round_dir.mkdir(parents=True)
    replay = {
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
    (round_dir / "sim_0.json").write_text(json.dumps(replay) + "\n")
    (round_dir / "_target_team.txt").write_text("Blue\n")


def _write_runner(path: Path, source: str) -> Path:
    path.write_text(textwrap.dedent(source))
    path.chmod(0o755)
    return path


def test_robotrumble_artifact_scorer_scores_valid_runner(tmp_path: Path):
    scorer = _load_scorer()
    labels = tmp_path / "labels"
    _write_robotrumble_labels(labels)
    submission = tmp_path / "robot.js"
    submission.write_text("function robot(state, unit) {}\n")
    out_dir = tmp_path / "out"
    runner = _write_runner(
        tmp_path / "good_runner.py",
        """
        #!/usr/bin/env python3
        import argparse, json
        parser = argparse.ArgumentParser()
        parser.add_argument("--submission")
        parser.add_argument("--queries")
        parser.add_argument("--actions")
        args = parser.parse_args()
        with open(args.queries) as src, open(args.actions, "w") as dst:
            for fallback_id, line in enumerate(src):
                payload = json.loads(line)
                idx = payload.get("id", fallback_id)
                action = [{"unit_id": "b1", "action": {"type": "Move", "direction": "East"}}]
                dst.write(json.dumps({"id": idx, "action": action}) + "\\n")
        """,
    )

    payload = scorer.evaluate(
        submission,
        labels,
        out_dir,
        1,
        runner=runner,
        runner_user="root",
    )

    assert payload["mean_distance"] == 0.0
    assert float((out_dir / "reward.txt").read_text()) == 1.0
    assert json.loads((out_dir / "learner-runner.status.json").read_text())["status"] == "ok"


def test_robotrumble_artifact_scorer_nonzero_runner_is_bad_score(tmp_path: Path):
    scorer = _load_scorer()
    labels = tmp_path / "labels"
    _write_robotrumble_labels(labels)
    submission = tmp_path / "robot.js"
    submission.write_text("function robot(state, unit) {}\n")
    out_dir = tmp_path / "out"
    runner = _write_runner(
        tmp_path / "bad_runner.py",
        """
        #!/usr/bin/env python3
        import sys
        print("runner failed", file=sys.stderr)
        raise SystemExit(42)
        """,
    )

    payload = scorer.evaluate(
        submission,
        labels,
        out_dir,
        1,
        runner=runner,
        runner_user="root",
    )

    assert payload["mean_distance"] == 1.0
    assert float((out_dir / "reward.txt").read_text()) == 0.0
    status = json.loads((out_dir / "learner-runner.status.json").read_text())
    assert status["status"] == "nonzero_exit"
    assert status["returncode"] == 42
    assert "runner failed" in (out_dir / "learner-runner.stderr").read_text()


def test_robotrumble_artifact_scorer_error_action_dict_is_bad_score(tmp_path: Path):
    scorer = _load_scorer()
    labels = tmp_path / "labels"
    _write_robotrumble_labels(labels)
    submission = tmp_path / "robot.js"
    submission.write_text("function robot(state, unit) {}\n")
    out_dir = tmp_path / "out"
    runner = _write_runner(
        tmp_path / "error_action_runner.py",
        """
        #!/usr/bin/env python3
        import argparse, json
        parser = argparse.ArgumentParser()
        parser.add_argument("--submission")
        parser.add_argument("--queries")
        parser.add_argument("--actions")
        args = parser.parse_args()
        with open(args.queries) as src, open(args.actions, "w") as dst:
            for fallback_id, line in enumerate(src):
                payload = json.loads(line)
                idx = payload.get("id", fallback_id)
                dst.write(json.dumps({"id": idx, "action": {"error": "boom"}}) + "\\n")
        """,
    )

    payload = scorer.evaluate(
        submission,
        labels,
        out_dir,
        1,
        runner=runner,
        runner_user="root",
    )

    assert payload["mean_distance"] == 1.0
    assert "component_errors" not in payload
    assert json.loads((out_dir / "learner-runner.status.json").read_text())["status"] == "ok"


def test_robotrumble_artifact_scorer_timeout_is_bad_score(
    tmp_path: Path,
    monkeypatch,
):
    scorer = _load_scorer()
    labels = tmp_path / "labels"
    _write_robotrumble_labels(labels)
    submission = tmp_path / "robot.js"
    submission.write_text("function robot(state, unit) {}\n")
    out_dir = tmp_path / "out"
    runner = tmp_path / "timeout_runner.py"
    runner.write_text("# unused\n")

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["id", "-u"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="1000\n", stderr="")
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 180))

    monkeypatch.setattr(scorer.subprocess, "run", fake_run)

    payload = scorer.evaluate(
        submission,
        labels,
        out_dir,
        1,
        runner=runner,
        runner_user="agent",
    )

    assert payload["mean_distance"] == 1.0
    assert float((out_dir / "reward.txt").read_text()) == 0.0
    status = json.loads((out_dir / "learner-runner.status.json").read_text())
    assert status["status"] == "timeout"
    assert "timed out" in (out_dir / "learner-runner.stderr").read_text()
