#!/usr/bin/env python3
"""Run a bounded RoboCode probe against the sealed target."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from revenge_bench.traces.robocode_probe import (
    RC_FILE,
    build_checked_probe_payload,
    compile_robot_package,
    reset_robot_database,
    rewrite_robot_package,
    run_probe_simulations,
    write_probe_battle,
)


WORKSPACE = Path("/workspace")
TARGET = Path("/target")
LOGS = Path("/run/robocode_probe")
BUDGET = Path("/workspace/.probe_budget")


def _budget() -> int:
    try:
        return int(BUDGET.read_text().strip())
    except Exception:
        return 0


def _set_budget(value: int) -> None:
    BUDGET.write_text(f"{value}\n")


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


def main(argv: list[str]) -> int:
    remaining = _budget()
    if remaining <= 0:
        print(json.dumps({"error": "probe budget exhausted"}, indent=2))
        return 1

    probe_dir = WORKSPACE / "probe"
    if not (probe_dir / RC_FILE).exists():
        print(json.dumps({"error": f"missing {probe_dir / RC_FILE}"}, indent=2))
        return 1

    probe_id = 26 - remaining
    _set_budget(remaining - 1)

    if LOGS.exists():
        shutil.rmtree(LOGS)
    LOGS.mkdir(parents=True)

    _copy_bot(probe_dir, "p0")
    _copy_bot(TARGET, "p1")
    reset_robot_database(WORKSPACE)
    battle = write_probe_battle(WORKSPACE)

    sims = int(argv[1]) if len(argv) > 1 else 3
    simulations = run_probe_simulations(WORKSPACE, LOGS, sims=sims, battle=battle)
    payload = build_checked_probe_payload(simulations, probe_id)
    payload["probes_remaining"] = remaining - 1
    out = WORKSPACE / f"probe_trace_{probe_id}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    os.chown(out, 1000, 1000)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        raise
