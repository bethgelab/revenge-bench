#!/usr/bin/env python3
"""Parse BattleSnake probe simulation traces (in-container, trusted phase).

Mirrors ``InverseStrategyInterventionist._parse_battlesnake_probe_traces``:
reads the ``sim_*.jsonl`` files produced by a probe-vs-target game and emits the
``pairs`` payload the agent consumes to learn the target's policy. This runs as
root inside ``run_probe`` *after* the live game, so it never exposes target
source — only the target's observable moves (the intended oracle signal).

Usage:
    parse_probe_traces.py <logs_dir> <out_json> <probe_id> <probes_remaining>

``probes_remaining`` may be the literal ``null``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _load_parser():
    from revenge_bench.traces.parsers.battlesnake import (
        actions_distance,
        extract_player_action,
        extract_player_state,
    )

    return actions_distance, extract_player_action, extract_player_state


def parse_probe_logs(
    logs_dir: Path,
    probe_id: int,
    *,
    probe_name: str = "probe",
    target_name: str = "target",
) -> dict[str, Any]:
    """Build the probe trace payload from ``sim_*.jsonl`` files in ``logs_dir``."""
    actions_distance, extract_player_action, extract_player_state = _load_parser()

    sim_files = sorted(logs_dir.glob("sim_*.jsonl"))
    if not sim_files:
        return {"error": "No simulation files found", "probe_id": probe_id}

    all_pairs: list[dict[str, Any]] = []
    per_simulation: list[dict[str, Any]] = []

    for sim_file in sim_files:
        lines = sim_file.read_text().strip().split("\n")
        turns = []
        for line in lines:
            try:
                turn_data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "board" in turn_data:
                turns.append(turn_data)

        sim_pairs = []
        for i in range(len(turns) - 1):
            turn_data = turns[i]
            next_turn_data = turns[i + 1]
            turn_num = turn_data.get("turn", i)

            target_state = extract_player_state(turn_data, target_name)
            probe_state = extract_player_state(turn_data, probe_name)
            if target_state is None or probe_state is None:
                continue

            target_action = extract_player_action(turn_data, next_turn_data, target_name)
            probe_action = extract_player_action(turn_data, next_turn_data, probe_name)
            if target_action is None or probe_action is None:
                continue

            pair = {
                "turn": turn_num,
                "probe_action": probe_action,
                "target_action": target_action,
                "distance": actions_distance(probe_action, target_action),
                "target_state": target_state,
            }
            sim_pairs.append(pair)
            all_pairs.append(pair)

        per_simulation.append({"file": sim_file.name, "num_turns": len(sim_pairs)})

    return {
        "probe_id": probe_id,
        "description": "probe vs target - showing what each did in the same state",
        "total_turns": len(all_pairs),
        "num_simulations": len(per_simulation),
        "per_simulation": per_simulation,
        "pairs": all_pairs,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 4:
        print("usage: parse_probe_traces.py <logs_dir> <out_json> <probe_id> <remaining>", file=sys.stderr)
        return 2
    logs_dir, out_json, probe_id_s, remaining_s = argv[:4]

    payload = parse_probe_logs(Path(logs_dir), int(probe_id_s))
    payload["probes_remaining"] = None if remaining_s == "null" else int(remaining_s)

    Path(out_json).write_text(json.dumps(payload, indent=2))

    summary = {
        "probe_id": payload.get("probe_id"),
        "saved_to": out_json,
        "probes_remaining": payload.get("probes_remaining"),
        "total_turns": payload.get("total_turns"),
        "num_simulations": payload.get("num_simulations"),
        "error": payload.get("error"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
