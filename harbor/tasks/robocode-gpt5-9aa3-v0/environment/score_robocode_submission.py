#!/usr/bin/env python3
"""Score a RoboCode submission against frozen traces using shared code."""

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
    evaluate_robocode_submission_with_move_provider,
    find_robocode_sim_files,
    robocode_parser_target_name_for_sim,
)
from revenge_bench.traces.parsers.robocode import extract_state_action_pairs


class RoboCodeArtifactMoveProvider:
    def __init__(self, actions: list[Any]) -> None:
        self.actions = actions
        self.index = 0

    def __call__(self, _state: dict) -> Any:
        if self.index >= len(self.actions):
            return None
        action = self.actions[self.index]
        self.index += 1
        return action


def _collect_queries(labels: Path, target_name: str) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for sim_file in find_robocode_sim_files(labels):
        parser_target_name = robocode_parser_target_name_for_sim(sim_file, target_name)
        try:
            for target_state, _target_action in extract_state_action_pairs(
                sim_file, parser_target_name
            ):
                queries.append({"id": len(queries), "state": target_state})
        except Exception:
            continue
    return queries


def _write_queries(path: Path, queries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for query in queries:
            handle.write(json.dumps(query, separators=(",", ":")) + "\n")


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


def _run_action_artifact(
    *,
    submission: Path,
    runner: Path,
    user: str,
    out_dir: Path,
    queries: list[dict[str, Any]],
) -> list[Any]:
    run_root = Path("/run/revengebench_eval")
    artifact_dir = (
        run_root / "robocode"
        if Path("/run").is_dir() and os.access("/run", os.W_OK)
        else out_dir / "action_artifacts"
    )
    shutil.rmtree(artifact_dir, ignore_errors=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    queries_path = artifact_dir / "queries.jsonl"
    actions_path = artifact_dir / "actions.jsonl"
    _write_queries(queries_path, queries)

    prefix: list[str] = []
    if subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip() == "0":
        shutil.chown(artifact_dir, user=user, group=user)
        shutil.chown(queries_path, user=user, group=user)
        prefix = ["runuser", "-u", user, "--"]

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
        str(submission),
        "--queries",
        str(queries_path),
        "--actions",
        str(actions_path),
    ]
    with (out_dir / "learner-runner.stdout").open("w", encoding="utf-8") as stdout, (
        out_dir / "learner-runner.stderr"
    ).open("w", encoding="utf-8") as stderr:
        subprocess.run(cmd, stdout=stdout, stderr=stderr, text=True, timeout=300)
    return _read_actions(actions_path, len(queries))


def evaluate(
    submission: Path,
    labels: Path,
    out_dir: Path,
    round_num: int,
    *,
    target_name: str = "target",
    learner_name: str = "learner",
    runner: Path = Path("/opt/robocode/robocode_learner_runner.py"),
    runner_user: str = "agent",
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not find_robocode_sim_files(labels):
        payload = {"error": f"No frozen record_*.xml traces found in {labels}"}
    else:
        queries = _collect_queries(labels, target_name)
        actions = _run_action_artifact(
            submission=submission,
            runner=runner,
            user=runner_user,
            out_dir=out_dir,
            queries=queries,
        )
        provider = RoboCodeArtifactMoveProvider(actions)
        payload = evaluate_robocode_submission_with_move_provider(
            round_dir=labels,
            round_num=round_num,
            target_name=target_name,
            learner_name=learner_name,
            move_provider=provider,
            evaluation_type="offline_artifact",
            include_diagnostics=True,
        )

    (out_dir / "eval.json").write_text(json.dumps(payload, indent=2) + "\n")
    md = payload.get("mean_distance")
    reward = 1.0 - float(md) if isinstance(md, (int, float)) and math.isfinite(md) else 0.0
    (out_dir / "reward.txt").write_text(f"{reward}\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, default=Path("/workspace/main.py"))
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--target-name", default="target")
    parser.add_argument("--learner-name", default="learner")
    args = parser.parse_args()
    evaluate(
        args.submission,
        args.labels,
        args.out_dir,
        args.round,
        target_name=args.target_name,
        learner_name=args.learner_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
