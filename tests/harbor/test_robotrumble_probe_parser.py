"""Parity guard for RobotRumble probe trace parsing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock


def _robotrumble_probe_replay() -> dict:
    return {
        "winner": None,
        "errors": {},
        "turns": [
            {
                "turn": 1,
                "state": {
                    "turn": 1,
                    "objs": {
                        "b1": {
                            "obj_type": "Unit",
                            "type": "Soldier",
                            "team": "Blue",
                            "coords": [1, 1],
                            "health": 5,
                        },
                        "r1": {
                            "obj_type": "Unit",
                            "type": "Soldier",
                            "team": "Red",
                            "coords": [2, 1],
                            "health": 5,
                        },
                    },
                },
                "robot_actions": {
                    "b1": {"Ok": {"type": "Move", "direction": "East"}},
                    "r1": {"Ok": {"type": "Attack", "direction": "West"}},
                },
            }
        ],
    }


def test_robotrumble_probe_payload_matches_normal_path_parser_byte_identically():
    from revenge_bench.tournaments.inverse_strategy_interventionist import (
        InverseStrategyInterventionistTournament,
    )
    from revenge_bench.traces.parsers.robotrumble import build_probe_trace_payload

    probe_id = 11
    replay_name = "sim_0.json"
    replay = _robotrumble_probe_replay()
    arena = MagicMock()

    def execute(cmd: str):
        if cmd == "ls /logs/sim_*.json 2>/dev/null || echo 'NONE'":
            return {"output": f"/logs/{replay_name}\n", "returncode": 0}
        if cmd == f"cat /logs/{replay_name}":
            return {"output": json.dumps(replay), "returncode": 0}
        raise AssertionError(f"unexpected command: {cmd}")

    arena.environment.execute.side_effect = execute

    tournament = MagicMock(spec=InverseStrategyInterventionistTournament)
    tournament._parse_robotrumble_probe_traces = (
        InverseStrategyInterventionistTournament._parse_robotrumble_probe_traces.__get__(
            tournament
        )
    )

    normal_payload = tournament._parse_robotrumble_probe_traces(arena, probe_id)
    shared_payload = build_probe_trace_payload([(replay_name, replay)], probe_id)

    assert json.dumps(normal_payload, sort_keys=True) == json.dumps(
        shared_payload, sort_keys=True
    )
