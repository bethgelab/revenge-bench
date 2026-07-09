#!/usr/bin/env python3
"""Score the starter RoboCode policy against visible round-0 traces."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/opt/robocode")

from score_robocode_submission import evaluate


def main() -> int:
    evaluate(
        Path("/workspace/main.py"),
        Path("/workspace/rounds/0"),
        Path("/workspace/rounds/0"),
        0,
    )
    eval_path = Path("/workspace/rounds/0/eval.json")
    traces_path = Path("/workspace/rounds/0/traces.json")
    traces_path.write_text(eval_path.read_text())
    eval_path.unlink(missing_ok=True)
    (Path("/workspace/rounds/0/reward.txt")).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
