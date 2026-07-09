#!/usr/bin/env python3
"""Generate normal-path-style Halite round traces inside the Harbor image."""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/halite")

from halite_common import compile_submission, prepare_submission, run_halite


TARGET = Path("/target")
OPPONENTS = Path("/opt/revengebench/opponents")
OUT = Path(os.environ.get("HALITE_TRACE_OUT", "/workspace/rounds/0"))
ARENA = Path(os.environ.get("HALITE_TRACE_ARENA", "/run/halite_label_arena"))
RESOLVED_TASK = Path(os.environ.get("HALITE_RESOLVED_TASK", "/target/resolved_task.json"))
TRACE_SOURCE = os.environ.get("HALITE_TRACE_SOURCE", "harbor-image-build")


def _run_one_opponent(opponent: Path, opp_idx: int, sims: int) -> None:
    opp_dir = OUT / f"opp_{opp_idx}"
    opp_dir.mkdir(parents=True, exist_ok=True)
    print(f"generating Halite traces for opponent {opp_idx}: {opponent.name} ({sims} sims)", flush=True)

    target_work = ARENA / f"target_{opp_idx}"
    opponent_work = ARENA / f"opponent_{opp_idx}"
    prepare_submission(TARGET, target_work)
    prepare_submission(opponent, opponent_work)
    target_exec = compile_submission(target_work / "submission")
    opponent_exec = compile_submission(opponent_work / "submission")

    players = [("target", target_exec), ("opponent", opponent_exec)]
    random.shuffle(players)
    target_player_index = next(i for i, (role, _) in enumerate(players) if role == "target")
    target_hlt_name = None

    for sim_idx in range(sims):
        produced = run_halite(opp_dir, *(executable for _, executable in players))
        if not produced:
            raise RuntimeError("Halite produced no .hlt replay")
        dest = opp_dir / f"sim_{sim_idx}.hlt"
        shutil.move(str(produced[-1]), dest)
        if target_hlt_name is None:
            from revenge_bench.traces.parsers.halite import load_hlt_file

            hlt_data = load_hlt_file(dest)
            player_names = hlt_data.get("player_names", [])
            if target_player_index >= len(player_names):
                raise RuntimeError(f"Could not map target player in {dest}")
            target_hlt_name = player_names[target_player_index]
        for extra in produced[:-1]:
            extra.unlink(missing_ok=True)

    (opp_dir / "_target_hlt_name.txt").write_text(f"{target_hlt_name}\n")
    (opp_dir / "_target_player_index.txt").write_text(f"{target_player_index}\n")


def main() -> int:
    instance = json.loads(RESOLVED_TASK.read_text())
    opponents = instance["opponents"]
    total_sims = int(instance["sims_per_round"])
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
        if not (opponent / "main.c").exists():
            raise FileNotFoundError(f"missing opponent main.c: {opponent}")
        _run_one_opponent(opponent, opp_idx, sims)

    manifest = {
        "source": TRACE_SOURCE,
        "task": instance,
        "target_identity": "per-opponent _target_hlt_name.txt",
        "label_files": [
            p.relative_to(OUT).as_posix() for p in sorted(OUT.rglob("sim_*.hlt"))
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.rmtree(ARENA, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
