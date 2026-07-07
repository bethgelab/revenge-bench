#!/usr/bin/env python3
"""Generate normal-path-style RoboCode round traces inside Harbor image."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from revenge_bench.traces.robocode_probe import (
    RC_FILE,
    compile_robot_package,
    rewrite_robot_package,
    robocode_round_battle_content,
)

WORKSPACE = Path("/workspace")
TARGET = Path("/target")
OPPONENTS = Path("/opt/revengebench/opponents")
OUT = Path(os.environ.get("ROBOCODE_TRACE_OUT", "/workspace/rounds/0"))
RESOLVED_TASK = Path(os.environ.get("ROBOCODE_RESOLVED_TASK", "/target/resolved_task.json"))
TRACE_SOURCE = os.environ.get("ROBOCODE_TRACE_SOURCE", "harbor-image-build")


def _copy_bot(src: Path, pkg: str) -> None:
    dest = WORKSPACE / "robots" / pkg
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    java_file = dest / RC_FILE
    if not java_file.exists():
        raise FileNotFoundError(f"missing {RC_FILE}: {src}")
    rewrite_robot_package(dest, pkg)
    compile_robot_package(WORKSPACE, pkg)


def _write_battle_file() -> Path:
    battle = WORKSPACE / "battles" / "harbor.battle"
    battle.parent.mkdir(parents=True, exist_ok=True)
    battle.write_text(robocode_round_battle_content(["p0", "p1"], robot_class=RC_FILE.stem))
    return battle


def _run_one_opponent(opponent: Path, opp_idx: int, sims: int) -> None:
    opp_dir = OUT / f"opp_{opp_idx}"
    opp_dir.mkdir(parents=True, exist_ok=True)
    print(f"generating RoboCode traces for opponent {opp_idx}: {opponent.name} ({sims} sims)", flush=True)

    # Keep target alias stable across the multi-opponent Harbor labels. The
    # normal evaluator resolves a single package alias for the round.
    _copy_bot(TARGET, "p0")
    _copy_bot(opponent, "p1")
    battle = _write_battle_file()
    (opp_dir / "_pkg_to_agent.json").write_text(json.dumps({"p0": "target", "p1": "opponent"}) + "\n")

    for sim_idx in range(sims):
        record = opp_dir / f"record_{sim_idx}.xml"
        results = opp_dir / f"results_{sim_idx}.txt"
        cmd = [
            "./robocode.sh",
            "-nodisplay",
            "-nosound",
            "-battle",
            str(battle),
            "-results",
            str(results),
            "-recordXML",
            str(record),
        ]
        proc = subprocess.run(
            cmd,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            tail = (proc.stdout + "\n" + proc.stderr)[-4000:]
            raise RuntimeError(
                f"RoboCode simulation failed for opponent {opponent.name} "
                f"sim {sim_idx} with rc={proc.returncode}:\n{tail}"
            )
        if not record.exists() or record.stat().st_size == 0:
            raise RuntimeError(f"RoboCode produced empty/missing XML trace: {record}")
        if not results.exists() or results.stat().st_size == 0:
            raise RuntimeError(f"RoboCode produced empty/missing results file: {results}")

    # RoboCode can leave JVM helper processes around briefly.
    time.sleep(0.1)


def main() -> int:
    instance = json.loads(RESOLVED_TASK.read_text())
    opponents = instance["opponents"]
    total_sims = int(instance["sims_per_round"])

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    per_opp = total_sims // len(opponents)
    remainder = total_sims % len(opponents)
    for opp_idx, rel in enumerate(opponents):
        sims = per_opp + (1 if opp_idx < remainder else 0)
        if sims <= 0:
            continue
        opponent = OPPONENTS / Path(rel).name
        _run_one_opponent(opponent, opp_idx, sims)

    manifest = {
        "source": TRACE_SOURCE,
        "task": instance,
        "target_identity": "p0",
        "label_files": [
            p.relative_to(OUT).as_posix() for p in sorted(OUT.rglob("record_*.xml"))
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
