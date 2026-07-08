#!/usr/bin/env python3
"""Implementation for the root-only RobotRumble probe oracle."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from revenge_bench.traces.parsers.robotrumble import build_probe_trace_payload


WORKSPACE = Path("/workspace")


def _copy_robot(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(src, dest / "robot.js")
    return dest / "robot.js"


def _run_simulation(cmd: list[str], dest: Path, sim_idx: int) -> dict:
    try:
        with dest.open("w", encoding="utf-8") as fh:
            proc = subprocess.run(
                cmd,
                cwd=WORKSPACE,
                stdout=fh,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=120,
            )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"probe sim {sim_idx} timed out after {exc.timeout}s") from exc

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "")[-4000:]
        raise RuntimeError(
            f"probe sim {sim_idx} failed with exit code {proc.returncode}:\n{stderr_tail}"
        )
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"probe sim {sim_idx} produced no JSON")
    try:
        return json.loads(dest.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"probe sim {sim_idx} produced invalid JSON: {exc}") from exc


def _run(argv: list[str]) -> int:
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
    try:
        for sim_idx in range(sims):
            dest = logs / f"sim_{sim_idx}.json"
            simulations.append((dest.name, _run_simulation(cmd, dest, sim_idx)))

        remaining = int((WORKSPACE / ".probe_budget").read_text())
        payload = build_probe_trace_payload(simulations, probe_id)
        payload["probes_remaining"] = remaining
        out = WORKSPACE / f"probe_trace_{probe_id}.json"
        out.write_text(json.dumps(payload, indent=2) + "\n")
        shutil.chown(out, user="agent", group="agent")
        print(json.dumps({"probe_trace": str(out), "probes_remaining": remaining}))
        return 0
    finally:
        shutil.rmtree(arena, ignore_errors=True)


def main(argv: list[str]) -> int:
    try:
        return _run(argv)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
