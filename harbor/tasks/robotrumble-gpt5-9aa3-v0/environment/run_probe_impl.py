#!/usr/bin/env python3
"""Implementation for the root-only RobotRumble probe oracle."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from revenge_bench.traces.parsers.robotrumble import build_probe_trace_payload


def _copy_robot(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(src, dest / "robot.js")
    return dest / "robot.js"


def main(argv: list[str]) -> int:
    probe_id = int(argv[1])
    sims = int(argv[2])
    arena = Path(f"/run/robotrumble_probe_{probe_id}")
    logs = arena / "logs"
    if arena.exists():
        shutil.rmtree(arena)
    logs.mkdir(parents=True)

    probe_js = _copy_robot(Path("/workspace/probe.js"), arena / "probe")
    target_js = _copy_robot(Path("/target/robot.js"), arena / "target")

    simulations: list[tuple[str, dict]] = []
    cmd = [
        "./rumblebot",
        "run",
        "term",
        "--raw",
        str(probe_js),
        str(target_js),
    ]
    for sim_idx in range(sims):
        dest = logs / f"sim_{sim_idx}.json"
        with dest.open("w", encoding="utf-8") as fh:
            subprocess.run(
                cmd,
                cwd="/workspace",
                stdout=fh,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=120,
            )
        try:
            simulations.append((dest.name, json.loads(dest.read_text())))
        except json.JSONDecodeError:
            continue

    remaining = int(Path("/workspace/.probe_budget").read_text())
    payload = build_probe_trace_payload(simulations, probe_id)
    payload["probes_remaining"] = remaining
    out = Path(f"/workspace/probe_trace_{probe_id}.json")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    shutil.chown(out, user="agent", group="agent")
    shutil.rmtree(arena, ignore_errors=True)
    print(json.dumps({"probe_trace": str(out), "probes_remaining": remaining}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
