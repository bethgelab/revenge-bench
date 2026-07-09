#!/usr/bin/env python3
"""Generate the visible round-0 RobotRumble traces.json for the starter bot."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_evaluate():
    scorer = Path(__file__).with_name("score_robotrumble_submission.py")
    spec = importlib.util.spec_from_file_location("score_robotrumble_submission", scorer)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {scorer}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate


def main() -> int:
    evaluate = _load_evaluate()
    evaluate(
        submission=Path("/workspace/robot.js"),
        labels=Path("/workspace/rounds/0"),
        out_dir=Path("/workspace/rounds/0"),
        round_num=0,
    )
    # The scorer writes eval.json; normal-path feedback is called traces.json.
    eval_path = Path("/workspace/rounds/0/eval.json")
    traces_path = Path("/workspace/rounds/0/traces.json")
    traces_path.write_text(eval_path.read_text())
    eval_path.unlink(missing_ok=True)
    Path("/workspace/rounds/0/reward.txt").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
