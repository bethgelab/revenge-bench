#!/usr/bin/env python3
"""Artifact runner for querying a Halite learner bot as the agent user."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/halite")

from halite_common import compile_submission, copy_workspace_submission
from revenge_bench.harbor.traces.parsers.halite import query_compiled_bot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    shutil.rmtree(args.work_dir, ignore_errors=True)
    copy_workspace_submission(args.submission, args.work_dir)
    executable = compile_submission(args.work_dir / "submission")

    args.actions.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.queries.open(encoding="utf-8") as queries, args.actions.open(
        "w", encoding="utf-8"
    ) as actions:
        for line in queries:
            try:
                query = json.loads(line)
                learner_actions = query_compiled_bot(
                    executable,
                    query["hlt_data"],
                    int(query["player_tag"]),
                    timeout=10.0,
                )
                payload = {"id": query.get("id", total), "actions": learner_actions}
            except Exception as exc:  # noqa: BLE001 - one failed replay maps to no moves
                payload = {"id": total, "actions": [], "error": str(exc)}
            actions.write(json.dumps(payload, separators=(",", ":")) + "\n")
            total += 1
    print(f"Halite learner wrote {total} action batches to {args.actions}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
