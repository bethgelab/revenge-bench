#!/usr/bin/env python3
"""Hidden verifier copy of the RoboCode JSONL learner runner."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from revenge_bench.harbor.traces.offline_eval import load_move_function, query_move


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    args = parser.parse_args()

    submission = args.submission.resolve()
    with contextlib.redirect_stdout(sys.stderr):
        module, move_func, _kind = load_move_function(submission, submission.parent)
    if module is None or move_func is None:
        return 2

    for line in sys.stdin:
        try:
            state = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                action = query_move(move_func, state)
            sys.stdout.write(json.dumps({"action": action}, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(json.dumps({"action": None, "error": str(exc)}, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
