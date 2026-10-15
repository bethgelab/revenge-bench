#!/usr/bin/env python3
"""Generate normal-path-style HuskyBench round traces inside Harbor image."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from huskybench_common import run_husky_game, shuffled_two_player_match


TARGET = Path("/target")
OPPONENTS = Path("/opt/revengebench/opponents")
OUT = Path(os.environ.get("HUSKYBENCH_TRACE_OUT", "/workspace/rounds/0"))
RESOLVED_TASK = Path(os.environ.get("HUSKYBENCH_RESOLVED_TASK", "/target/resolved_task.json"))
TRACE_SOURCE = os.environ.get("HUSKYBENCH_TRACE_SOURCE", "harbor-image-build")


def _run_one_opponent(opponent: Path, opp_idx: int, sims: int) -> list[Path]:
    opp_dir = OUT / f"opp_{opp_idx}"
    if opp_dir.exists():
        shutil.rmtree(opp_dir)
    opp_dir.mkdir(parents=True)
    print(
        f"generating HuskyBench traces for opponent {opp_idx}: {opponent.name} ({sims} hands)",
        flush=True,
    )
    players = shuffled_two_player_match(("target", TARGET), ("opponent", opponent))
    return run_husky_game(players, sims, opp_dir)


def main() -> int:
    instance = json.loads(RESOLVED_TASK.read_text())
    opponents = instance["opponents"]
    total_sims = int(instance["sims_per_round"])

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    per_opp = total_sims // len(opponents)
    remainder = total_sims % len(opponents)
    label_files: list[str] = []
    for opp_idx, rel in enumerate(opponents):
        sims = per_opp + (1 if opp_idx < remainder else 0)
        if sims <= 0:
            continue
        opponent = OPPONENTS / Path(rel).name
        game_logs = _run_one_opponent(opponent, opp_idx, sims)
        label_files.extend(p.relative_to(OUT).as_posix() for p in game_logs)

    if not label_files:
        raise RuntimeError("no HuskyBench labels generated")

    manifest = {
        "source": TRACE_SOURCE,
        "task": instance,
        "target_identity": "target",
        "label_files": sorted(label_files),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
