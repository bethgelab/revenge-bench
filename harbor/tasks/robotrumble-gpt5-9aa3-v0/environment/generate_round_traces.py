#!/usr/bin/env python3
"""Generate normal-path-style RobotRumble round traces inside Harbor image."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path


TARGET = Path("/target")
OPPONENTS = Path("/opt/revengebench/opponents")
OUT = Path(os.environ.get("ROBOTRUMBLE_TRACE_OUT", "/workspace/rounds/0"))
ARENA = Path(os.environ.get("ROBOTRUMBLE_TRACE_ARENA", "/run/robotrumble_label_arena"))
RESOLVED_TASK = Path(
    os.environ.get("ROBOTRUMBLE_RESOLVED_TASK", "/target/resolved_task.json")
)
TRACE_SOURCE = os.environ.get("ROBOTRUMBLE_TRACE_SOURCE", "harbor-image-build")


def _prepare_bot(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    robot_js = dest / "robot.js"
    if not robot_js.exists():
        raise FileNotFoundError(f"missing robot.js: {src}")
    return robot_js


def _run_one_opponent(opponent: Path, opp_idx: int, sims: int, seed: int) -> None:
    opp_dir = OUT / f"opp_{opp_idx}"
    opp_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"generating RobotRumble traces for opponent {opp_idx}: "
        f"{opponent.name} ({sims} sims)",
        flush=True,
    )

    target_js = _prepare_bot(TARGET, ARENA / f"target_{opp_idx}") 
    opponent_js = _prepare_bot(opponent, ARENA / f"opponent_{opp_idx}")

    players = [("target", target_js), ("opponent", opponent_js)]
    random.Random(seed + opp_idx).shuffle(players)
    target_team = "Blue" if players[0][0] == "target" else "Red"
    cmd_prefix = [
        "./rumblebot",
        "run",
        "term",
        "--raw",
        str(players[0][1]),
        str(players[1][1]),
    ]

    for sim_idx in range(sims):
        dest = opp_dir / f"sim_{sim_idx}.json"
        with dest.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(
                cmd_prefix,
                cwd="/workspace",
                stdout=fh,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=120,
            )
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-4000:]
            raise RuntimeError(
                f"RobotRumble simulation failed for opponent {opponent.name} "
                f"sim {sim_idx} with rc={proc.returncode}:\n{tail}"
            )
        if dest.stat().st_size == 0:
            raise RuntimeError(
                f"RobotRumble simulation produced empty trace: {dest}"
            )
        try:
            data = json.loads(dest.read_text())
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"RobotRumble produced invalid JSON: {dest}") from exc
        if not data.get("turns"):
            raise RuntimeError(f"RobotRumble trace has no turns: {dest}")

    (opp_dir / "_target_team.txt").write_text(f"{target_team}\n")


def main() -> int:
    instance = json.loads(RESOLVED_TASK.read_text())
    opponents = instance["opponents"]
    total_sims = int(instance["sims_per_round"])
    seed = int(instance.get("seed", 0))

    if OUT.exists():
        shutil.rmtree(OUT)
    if ARENA.exists():
        shutil.rmtree(ARENA)
    ARENA.mkdir(parents=True)

    per_opp = total_sims // len(opponents)
    remainder = total_sims % len(opponents)
    for opp_idx, rel in enumerate(opponents):
        sims = per_opp + (1 if opp_idx < remainder else 0)
        if sims <= 0:
            continue
        opponent = OPPONENTS / Path(rel).name
        _run_one_opponent(opponent, opp_idx, sims, seed)

    manifest = {
        "source": TRACE_SOURCE,
        "task": instance,
        "target_identity": "per-opponent _target_team.txt",
        "label_files": [
            p.relative_to(OUT).as_posix() for p in sorted(OUT.rglob("sim_*.json"))
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.rmtree(ARENA, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
