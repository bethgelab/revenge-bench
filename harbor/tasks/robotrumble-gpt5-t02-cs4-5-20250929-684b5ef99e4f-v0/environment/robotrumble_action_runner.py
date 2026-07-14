#!/usr/bin/env python3
"""Artifact runner for querying a RobotRumble learner robot as the agent user."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _robotrumble_parser_dir() -> Path:
    import revenge_bench.harbor.traces.parsers.robotrumble as robotrumble

    return Path(robotrumble.__file__).resolve().parent


def _run_harness(robot_js: Path, harness_inputs: list[dict]) -> list[Any]:
    parsers_dir = _robotrumble_parser_dir()
    harness_js = parsers_dir / "robotrumble_eval_harness.js"
    stdlib_js = parsers_dir / "robotrumble_stdlib.js"
    lodash_js = parsers_dir / "robotrumble_lodash.min.js"
    payload = "\n".join(json.dumps(item, separators=(",", ":")) for item in harness_inputs) + "\n"
    proc = subprocess.run(
        ["node", str(harness_js), str(stdlib_js), str(robot_js), str(lodash_js)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"JS evaluation failed: {proc.stderr[:500]}")
    parsed: list[Any] = []
    for line in proc.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--actions", type=Path, required=True)
    args = parser.parse_args()

    queries = [json.loads(line) for line in args.queries.read_text().splitlines() if line.strip()]
    query_ids = [query.get("id", idx) for idx, query in enumerate(queries)]
    harness_inputs = [query["input"] for query in queries]
    try:
        action_batches = _run_harness(args.submission, harness_inputs)
    except Exception as exc:  # noqa: BLE001
        action_batches = [{"error": str(exc)} for _ in queries]
    while len(action_batches) < len(queries):
        action_batches.append(None)

    args.actions.parent.mkdir(parents=True, exist_ok=True)
    with args.actions.open("w", encoding="utf-8") as handle:
        for idx, action in zip(query_ids, action_batches, strict=False):
            handle.write(json.dumps({"id": idx, "action": action}, separators=(",", ":")) + "\n")
    print(f"RobotRumble learner wrote {len(queries)} actions to {args.actions}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
