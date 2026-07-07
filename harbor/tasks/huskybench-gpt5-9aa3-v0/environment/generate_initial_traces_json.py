#!/usr/bin/env python3
"""Score the visible round-0 HuskyBench starter traces with shared code."""

from __future__ import annotations

import json
from pathlib import Path

from revenge_bench.traces.offline_eval import (
    evaluate_huskybench_submission_with_action_provider,
    make_huskybench_bot_action_provider,
)


def main() -> int:
    round_dir = Path("/workspace/rounds/0")
    submission = Path("/workspace/client/player.py")
    provider, error = make_huskybench_bot_action_provider(submission, submission.parent)
    if provider is None:
        payload = {"error": error or "failed to load HuskyBench starter"}
    else:
        payload = evaluate_huskybench_submission_with_action_provider(
            round_dir=round_dir,
            round_num=0,
            target_name="target",
            learner_name="learner",
            action_provider=provider,
            evaluation_type="offline_bot_class",
            include_diagnostics=True,
        )
    (round_dir / "traces.json").write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
