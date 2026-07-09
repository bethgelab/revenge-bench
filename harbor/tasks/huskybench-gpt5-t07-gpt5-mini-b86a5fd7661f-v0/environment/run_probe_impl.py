#!/usr/bin/env python3
"""Run a bounded HuskyBench probe against the sealed target."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from huskybench_common import run_husky_game
from revenge_bench.harbor.traces.parsers.huskybench import build_probe_trace_payload


WORKSPACE = Path("/workspace")
TARGET = Path("/target")
LOGS = Path("/run/huskybench_probe")
BUDGET = Path("/workspace/.probe_budget")


def _budget() -> int:
    try:
        return int(BUDGET.read_text().strip())
    except Exception:
        return 0


def _set_budget(value: int) -> None:
    BUDGET.write_text(f"{value}\n")


def _run(argv: list[str]) -> int:
    remaining = _budget()
    if remaining <= 0:
        print(json.dumps({"error": "probe budget exhausted"}, indent=2))
        return 0

    probe_dir = WORKSPACE / "probe"
    if not (probe_dir / "client" / "player.py").exists():
        print(json.dumps({"error": f"missing {probe_dir / 'client' / 'player.py'}"}, indent=2))
        return 0
    if not (probe_dir / "client" / "main.py").exists():
        print(json.dumps({"error": f"missing {probe_dir / 'client' / 'main.py'}"}, indent=2))
        return 0

    probe_id = 26 - remaining
    _set_budget(remaining - 1)

    if LOGS.exists():
        shutil.rmtree(LOGS)
    LOGS.mkdir(parents=True)

    sims = int(argv[1]) if len(argv) > 1 else 50
    # Normal interventionist HuskyBench probes start the probe client first and
    # the target client second. Keep that order fixed because poker position can
    # affect the state/action distribution.
    players = [("probe", probe_dir), ("target", TARGET)]
    game_logs = run_husky_game(players, sims, LOGS)
    simulations = [(path.name, json.loads(path.read_text())) for path in game_logs]
    payload = build_probe_trace_payload(simulations, probe_id)
    payload["probes_remaining"] = remaining - 1

    out = WORKSPACE / f"probe_trace_{probe_id}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    shutil.chown(out, user="agent", group="agent")
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str]) -> int:
    try:
        return _run(argv)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
