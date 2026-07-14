#!/usr/bin/env python3
"""Score a Halite submission against frozen .hlt traces using normal parser code."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/halite")

from revenge_bench.harbor.traces.offline_eval import (
    evaluate_halite_submission_with_action_provider,
    find_halite_sim_files,
)
from revenge_bench.harbor.traces.parsers.halite import load_hlt_file

MAX_NONZERO_DISTANCES = 200


def _target_hlt_name_for(sim_file: Path) -> str:
    name_file = sim_file.parent / "_target_hlt_name.txt"
    if name_file.exists():
        return name_file.read_text().strip()
    hlt_data = load_hlt_file(sim_file)
    player_names = hlt_data.get("player_names", [])
    if not player_names:
        raise RuntimeError(f"No player names in {sim_file}")
    return player_names[0]


class HaliteArtifactActionProvider:
    def __init__(self, action_batches: list[list]) -> None:
        self.action_batches = action_batches
        self.index = 0

    def __call__(self, _hlt_data: dict, _player_tag: int) -> list:
        if self.index >= len(self.action_batches):
            return []
        actions = self.action_batches[self.index]
        self.index += 1
        return actions


def _write_queries(path: Path, queries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for query in queries:
            handle.write(json.dumps(query, separators=(",", ":")) + "\n")


def _read_action_batches(path: Path, expected: int) -> list[list]:
    batches: list[list] = [[] for _ in range(expected)]
    if not path.exists():
        return batches
    with path.open(encoding="utf-8") as handle:
        for fallback_id, line in enumerate(handle):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            idx = payload.get("id", fallback_id)
            if isinstance(idx, int) and 0 <= idx < expected:
                value = payload.get("actions")
                batches[idx] = value if isinstance(value, list) else []
    return batches


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


def _run_action_artifact(
    *,
    submission: Path,
    runner: Path,
    user: str,
    out_dir: Path,
    queries: list[dict],
) -> list[list]:
    run_root = Path("/run/revengebench_eval")
    artifact_dir = (
        run_root / "halite"
        if Path("/run").is_dir() and os.access("/run", os.W_OK)
        else out_dir / "action_artifacts"
    )
    shutil.rmtree(artifact_dir, ignore_errors=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    queries_path = artifact_dir / "queries.jsonl"
    actions_path = artifact_dir / "actions.jsonl"
    work_dir = artifact_dir / "work"
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
        "--work-dir",
        str(work_dir),
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
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            stderr.write(f"\nHalite learner runner timed out after {exc.timeout}s\n")
            _write_runner_status(
                out_dir,
                status="timeout",
                timeout_sec=int(exc.timeout or 600),
                message="scoring degraded to missing action batches",
            )
            return _read_action_batches(actions_path, len(queries))
    if proc.returncode != 0:
        _write_runner_status(
            out_dir,
            status="nonzero_exit",
            returncode=proc.returncode,
            message="scoring degraded to runner-provided or missing action batches",
        )
    else:
        _write_runner_status(out_dir, status="ok", returncode=0)
    return _read_action_batches(actions_path, len(queries))


def evaluate(
    submission: Path,
    labels: Path,
    out_dir: Path,
    round_num: int,
    *,
    runner: Path = Path("/opt/halite/halite_action_runner.py"),
    runner_user: str = "agent",
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    sim_files = find_halite_sim_files(labels)
    if not sim_files:
        raise RuntimeError(f"No sim_*.hlt files under {labels}")

    target_name = _target_hlt_name_for(sim_files[0])
    queries = []
    for sim_file in sim_files:
        hlt_data = load_hlt_file(sim_file)
        player_tag = hlt_data["player_names"].index(target_name) + 1
        queries.append(
            {
                "id": len(queries),
                "hlt_data": hlt_data,
                "player_tag": player_tag,
            }
        )
    action_batches = _run_action_artifact(
        submission=submission,
        runner=runner,
        user=runner_user,
        out_dir=out_dir,
        queries=queries,
    )
    provider = HaliteArtifactActionProvider(action_batches)

    payload = evaluate_halite_submission_with_action_provider(
        round_dir=labels,
        round_num=round_num,
        target_hlt_name=target_name,
        learner_name="learner",
        action_provider=provider,
        evaluation_type="offline_artifact",
        include_diagnostics=True,
        max_nonzero_distances=MAX_NONZERO_DISTANCES,
    )

    mean_distance = payload.get("mean_distance")
    if not isinstance(mean_distance, (int, float)) or not math.isfinite(mean_distance):
        reward = 0.0
    else:
        reward = 1.0 - float(mean_distance)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reward.txt").write_text(f"{reward}\n")
    total_nonzero = sum(
        int(sim.get("num_nonzero", 0)) for sim in payload.get("per_simulation", [])
    )
    if total_nonzero > len(payload.get("nonzero_distances", [])):
        payload["nonzero_distances_truncated"] = True
        payload["nonzero_distances_total"] = total_nonzero
        payload["nonzero_distances_limit"] = MAX_NONZERO_DISTANCES
    (out_dir / "eval.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--runner", type=Path, default=Path("/opt/halite/halite_action_runner.py"))
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
