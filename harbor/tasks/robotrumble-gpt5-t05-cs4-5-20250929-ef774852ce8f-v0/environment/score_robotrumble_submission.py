#!/usr/bin/env python3
"""Score a RobotRumble submission against frozen traces using shared code."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from revenge_bench.traces.offline_eval import (
    evaluate_robotrumble_submission_with_action_provider,
)


def _write_queries(path: Path, harness_inputs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for idx, item in enumerate(harness_inputs):
            handle.write(json.dumps({"id": idx, "input": item}, separators=(",", ":")) + "\n")


def _read_actions(path: Path, expected: int) -> list[Any]:
    actions: list[Any] = [None] * expected
    if not path.exists():
        return actions
    with path.open(encoding="utf-8") as handle:
        for fallback_id, line in enumerate(handle):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            idx = payload.get("id", fallback_id)
            if isinstance(idx, int) and 0 <= idx < expected:
                actions[idx] = payload.get("action")
    return actions


def _write_runner_status(
    out_dir: Path,
    *,
    status: str,
    returncode: int | None = None,
    timeout_sec: int | None = None,
    message: str | None = None,
) -> None:
    payload = {
        "status": status,
        "returncode": returncode,
        "timeout_sec": timeout_sec,
        "message": message,
    }
    (out_dir / "learner-runner.status.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )


def _make_artifact_node_provider(
    robot_js: Path,
    *,
    out_dir: Path,
    runner: Path,
    runner_user: str,
):
    def provider(harness_inputs: list[dict]) -> list[Any]:
        run_root = Path("/run/revengebench_eval")
        artifact_dir = (
            run_root / "robotrumble"
            if Path("/run").is_dir() and os.access("/run", os.W_OK)
            else out_dir / "action_artifacts"
        )
        shutil.rmtree(artifact_dir, ignore_errors=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        queries_path = artifact_dir / "queries.jsonl"
        actions_path = artifact_dir / "actions.jsonl"
        _write_queries(queries_path, harness_inputs)

        prefix: list[str] = []
        if subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip() == "0":
            shutil.chown(artifact_dir, user=runner_user, group=runner_user)
            shutil.chown(queries_path, user=runner_user, group=runner_user)
            prefix = ["runuser", "-u", runner_user, "--"]

        cmd = [
            *prefix,
            "env",
            "-i",
            "HOME=/home/agent",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "PYTHONNOUSERSITE=1",
            "python3",
            "-I",
            str(runner),
            "--submission",
            str(robot_js),
            "--queries",
            str(queries_path),
            "--actions",
            str(actions_path),
        ]
        with (out_dir / "learner-runner.stdout").open("w", encoding="utf-8") as stdout, (
            out_dir / "learner-runner.stderr"
        ).open("w", encoding="utf-8") as stderr:
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                stderr.write(f"\nRobotRumble learner runner timed out after {exc.timeout}s\n")
                _write_runner_status(
                    out_dir,
                    status="timeout",
                    timeout_sec=int(exc.timeout or 180),
                    message="scoring degraded to missing actions",
                )
                return _read_actions(actions_path, len(harness_inputs))

        if proc.returncode != 0:
            _write_runner_status(
                out_dir,
                status="nonzero_exit",
                returncode=proc.returncode,
                message="scoring degraded to runner-provided or missing actions",
            )
        else:
            _write_runner_status(out_dir, status="ok", returncode=0)
        return _read_actions(actions_path, len(harness_inputs))

    return provider


def evaluate(
    submission: Path,
    labels: Path,
    out_dir: Path,
    round_num: int,
    *,
    runner: Path = Path("/opt/robotrumble/robotrumble_action_runner.py"),
    runner_user: str = "agent",
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = evaluate_robotrumble_submission_with_action_provider(
        round_dir=labels,
        round_num=round_num,
        learner_name="learner",
        action_provider=_make_artifact_node_provider(
            submission,
            out_dir=out_dir,
            runner=runner,
            runner_user=runner_user,
        ),
        fallback_target_team="Blue",
        evaluation_type="offline_artifact",
        include_diagnostics=True,
    )
    (out_dir / "eval.json").write_text(json.dumps(payload, indent=2) + "\n")

    mean_distance = payload.get("mean_distance")
    if not isinstance(mean_distance, (int, float)) or not math.isfinite(mean_distance):
        reward = 0.0
    else:
        reward = 1.0 - float(mean_distance)
    (out_dir / "reward.txt").write_text(f"{reward}\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--runner", type=Path, default=Path("/opt/robotrumble/robotrumble_action_runner.py"))
    parser.add_argument("--runner-user", default="agent")
    args = parser.parse_args()
    evaluate(
        args.submission,
        args.labels,
        args.out_dir,
        args.round,
        runner=args.runner,
        runner_user=args.runner_user,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
