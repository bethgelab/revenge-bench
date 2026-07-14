#!/usr/bin/env python3
"""Implementation for the root-only Halite probe oracle."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/halite")

from halite_common import (
    compile_submission,
    copy_workspace_submission,
    prepare_submission,
    run_halite,
)
from revenge_bench.harbor.traces.parsers.halite import (
    build_probe_trace_payload,
    load_hlt_file,
)


WORKSPACE = Path("/workspace")


def _run(argv: list[str]) -> int:
    probe_id = int(argv[1])
    sims = int(argv[2])
    arena = Path(f"/run/halite_probe_{probe_id}")
    logs = arena / "logs"
    if arena.exists():
        shutil.rmtree(arena)
    logs.mkdir(parents=True)

    try:
        probe_work = arena / "probe"
        target_work = arena / "target"
        copy_workspace_submission(WORKSPACE / "probe", probe_work)
        prepare_submission(Path("/target"), target_work)
        probe_exec = compile_submission(probe_work / "submission")
        target_exec = compile_submission(target_work / "submission")

        replay_files = []
        for sim_idx in range(sims):
            produced = run_halite(logs, probe_exec, target_exec)
            if produced:
                dest = logs / f"probe_{probe_id}_sim_{sim_idx}.hlt"
                shutil.move(str(produced[-1]), dest)
                replay_files.append(dest)
                for extra in produced[:-1]:
                    extra.unlink(missing_ok=True)

        remaining = int((WORKSPACE / ".probe_budget").read_text())
        replays = [(replay.name, load_hlt_file(replay)) for replay in replay_files]
        payload = build_probe_trace_payload(replays, probe_id)
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
