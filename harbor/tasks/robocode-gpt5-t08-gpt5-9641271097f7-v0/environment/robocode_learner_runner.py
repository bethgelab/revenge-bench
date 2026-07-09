#!/usr/bin/env python3
"""Artifact runner for querying a RoboCode learner move(state) function."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from revenge_bench.traces.offline_eval import load_move_function, query_move


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--actions", type=Path, required=True)
    args = parser.parse_args()

    submission = args.submission.resolve()
    with contextlib.redirect_stdout(sys.stderr):
        module, move_func, _kind = load_move_function(submission, submission.parent)
    if module is None or move_func is None:
        args.actions.write_text(
            json.dumps({"error": "failed to load move function"}, separators=(",", ":")) + "\n"
        )
        return 2

    args.actions.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.queries.open(encoding="utf-8") as queries, args.actions.open(
        "w", encoding="utf-8"
    ) as actions:
        for line in queries:
            try:
                query = json.loads(line)
                state = query.get("state", query)
                with contextlib.redirect_stdout(sys.stderr):
                    action = query_move(move_func, state)
                payload = {"id": query.get("id", total), "action": action}
            except Exception as exc:  # noqa: BLE001 - isolate learner errors
                payload = {"id": total, "action": None, "error": str(exc)}
            actions.write(json.dumps(payload, separators=(",", ":")) + "\n")
            total += 1
    print(f"RoboCode learner wrote {total} actions to {args.actions}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
