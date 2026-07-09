#!/usr/bin/env python3
"""Write the normal-path initial ``traces.json`` for the Harbor workspace.

The native inverse-strategy loop gives the learner a round-0 trace summary
before editing. Harbor has the same visible target-vs-opponent traces under
``/workspace/rounds/0``; this script replays the starter ``/workspace/main.py``
against those traces with the shared normal-path scorer and writes the same
summary shape to ``/workspace/rounds/0/traces.json``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROUND_DIR = Path(os.environ.get("BATTLESNAKE_INITIAL_ROUND", "/workspace/rounds/0"))
SUBMISSION = Path(os.environ.get("BATTLESNAKE_INITIAL_SUBMISSION", "/workspace/main.py"))
OUT = Path(os.environ.get("BATTLESNAKE_INITIAL_TRACE_JSON", ROUND_DIR / "traces.json"))


def main() -> int:
    from revenge_bench.harbor.traces.offline_eval import evaluate_battlesnake_submission

    if not SUBMISSION.exists():
        raise FileNotFoundError(f"missing initial submission: {SUBMISSION}")

    summary = evaluate_battlesnake_submission(
        round_dir=ROUND_DIR,
        round_num=0,
        target_name="target",
        learner_name="learner",
        learner_code_dir=SUBMISSION.parent,
        submission=SUBMISSION.name,
        include_diagnostics=True,
    )
    if summary.get("error"):
        print(f"failed to generate initial traces.json: {summary['error']}", file=sys.stderr)
        return 1

    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        "initial traces.json: "
        f"mean_distance={summary.get('mean_distance')} "
        f"actions={summary.get('total_actions')} "
        f"sims={summary.get('num_simulations')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
