#!/usr/bin/env python3
"""BattleSnake learner action runner for Harbor verification.

The root verifier owns hidden labels and writes only target-observed states to a
query artifact. This process runs as the unprivileged ``agent`` user, imports
the learner's ``main.py``, and writes an action artifact. Stdout is for logs
only; correctness is communicated through ``--actions``.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def _load_move(submission: Path):
    code_dir = submission.parent
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))

    spec = importlib.util.spec_from_file_location("learner_main", submission)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load submission spec for {submission}")

    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)

    move_func = getattr(module, "move", None)
    if move_func is None:
        move_func = getattr(module, "choose_move", None)
    if move_func is None:
        move_func = getattr(module, "robot", None)
    if move_func is None:
        raise RuntimeError(f"{submission} defines no move(), choose_move(), or robot()")
    return move_func


def _normalize_action(result: Any) -> Any:
    if isinstance(result, dict) and "move" in result:
        return result["move"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", default="/workspace/main.py")
    parser.add_argument("--queries", required=True)
    parser.add_argument("--actions", required=True)
    args = parser.parse_args(argv)

    actions_path = Path(args.actions)
    actions_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        move_func = _load_move(Path(args.submission))
    except Exception as exc:  # noqa: BLE001 - report a protocol-level failure
        actions_path.write_text(
            json.dumps({"error": f"load failed: {exc}"}, separators=(",", ":")) + "\n"
        )
        print(f"BattleSnake learner load failed: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 0

    total = 0
    with Path(args.queries).open(encoding="utf-8") as queries, actions_path.open(
        "w", encoding="utf-8"
    ) as actions:
        for line in queries:
            line = line.strip()
            if not line:
                continue
            try:
                query = json.loads(line)
                state = query.get("state", query)
                with contextlib.redirect_stdout(sys.stderr):
                    action = _normalize_action(move_func(state))
                payload = {"id": query.get("id", total), "action": action}
            except Exception as exc:  # noqa: BLE001 - one bad query maps to no action
                payload = {"id": total, "action": None, "error": str(exc)}
                traceback.print_exc(file=sys.stderr)
            actions.write(json.dumps(payload, separators=(",", ":")) + "\n")
            total += 1

    print(f"BattleSnake learner wrote {total} actions to {actions_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
