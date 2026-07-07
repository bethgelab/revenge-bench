"""Parity guard for Halite probe trace parsing.

The normal interventionist path and Harbor ``sudo run_probe`` path may have
different orchestration, but the probe trace payload semantics must be shared.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


def _halite_probe_replay() -> dict:
    return {
        "version": 11,
        "width": 2,
        "height": 1,
        "num_players": 2,
        "num_frames": 3,
        "player_names": ["ProbeBot", "TargetBot"],
        "productions": [[1, 2]],
        "frames": [
            [[[1, 10], [2, 20]]],
            [[[1, 11], [2, 19]]],
            [[[1, 12], [2, 18]]],
        ],
        "moves": [
            [[2, 4]],
            [[0, 1]],
        ],
    }


def test_halite_probe_payload_matches_normal_path_parser_byte_identically():
    from revenge_bench.tournaments.inverse_strategy_interventionist import (
        InverseStrategyInterventionistTournament,
    )
    from revenge_bench.traces.parsers.halite import build_probe_trace_payload

    probe_id = 7
    replay_name = "probe_7_sim_0.hlt"
    replay = _halite_probe_replay()

    arena = MagicMock()

    def execute(cmd: str):
        if cmd == "ls /logs/*.hlt 2>/dev/null || echo 'NONE'":
            return {"output": f"/logs/{replay_name}\n", "returncode": 0}
        if cmd == f"cat /logs/{replay_name}":
            return {"output": json.dumps(replay), "returncode": 0}
        raise AssertionError(f"unexpected command: {cmd}")

    arena.environment.execute.side_effect = execute

    tournament = MagicMock(spec=InverseStrategyInterventionistTournament)
    tournament._parse_halite_probe_traces = (
        InverseStrategyInterventionistTournament._parse_halite_probe_traces.__get__(
            tournament
        )
    )

    normal_payload = tournament._parse_halite_probe_traces(arena, probe_id)
    shared_payload = build_probe_trace_payload([(replay_name, replay)], probe_id)

    assert json.dumps(normal_payload, sort_keys=True) == json.dumps(
        shared_payload, sort_keys=True
    )


def test_halite_probe_payload_written_by_harbor_adds_only_remaining(tmp_path: Path):
    from revenge_bench.traces.parsers.halite import build_probe_trace_payload

    probe_id = 3
    replay_name = "probe_3_sim_0.hlt"
    replay = _halite_probe_replay()

    payload = build_probe_trace_payload([(replay_name, replay)], probe_id)
    payload["probes_remaining"] = 4

    out = tmp_path / "probe_trace_3.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")

    written = json.loads(out.read_text())
    expected = build_probe_trace_payload([(replay_name, replay)], probe_id)
    expected["probes_remaining"] = 4

    assert json.dumps(written, sort_keys=True) == json.dumps(
        expected, sort_keys=True
    )
