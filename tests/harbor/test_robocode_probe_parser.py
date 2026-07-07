from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from revenge_bench.tournaments.inverse_strategy_interventionist import (
    InverseStrategyInterventionistTournament,
)
from revenge_bench.traces.parsers.robocode import build_probe_trace_payload


def test_robocode_probe_payload_helper_matches_normal_parser(tmp_path: Path):
    xml = tmp_path / "record_0.xml"
    xml.write_text("<record></record>")
    expected = {
        "probe_id": 7,
        "description": "probe (p0) vs target (p1) — action comparison per tick",
        "total_turns": 1,
        "num_simulations": 1,
        "per_simulation": [{"file": "record_0.xml", "num_turns": 1}],
        "pairs": [
            {
                "turn": 3,
                "probe_action": {"velocity": 1.0},
                "target_action": {"velocity": 2.0},
                "distance": 0.0125,
                "target_state": {"tick": 3},
            }
        ],
    }

    def fake_pairs(path, player):
        assert Path(path).name == "record_0.xml"
        if player == "p1":
            return [({"tick": 3}, {"velocity": 2.0})]
        if player == "p0":
            return [({"tick": 3}, {"velocity": 1.0})]
        return []

    with patch("revenge_bench.traces.parsers.robocode.extract_state_action_pairs", side_effect=fake_pairs):
        direct = build_probe_trace_payload([("record_0.xml", xml)], 7)

    assert json.dumps(direct, sort_keys=True) == json.dumps(expected, sort_keys=True)

    arena = MagicMock()
    arena.environment.execute.return_value = {"output": "/logs/record_0.xml\n", "returncode": 0}

    tournament = MagicMock(spec=InverseStrategyInterventionistTournament)
    tournament.logger = MagicMock()
    tournament._parse_robocode_probe_traces = (
        InverseStrategyInterventionistTournament._parse_robocode_probe_traces.__get__(tournament)
    )

    with tempfile.TemporaryDirectory() as tmp:
        copied = Path(tmp) / "record_0.xml"

        def fake_copy_from_container(_env, _src, dest):
            Path(dest).write_text(copied.read_text() if copied.exists() else "<record></record>")

        with patch(
            "revenge_bench.tournaments.inverse_strategy_interventionist.copy_from_container",
            side_effect=fake_copy_from_container,
        ), patch(
            "revenge_bench.traces.parsers.robocode.extract_state_action_pairs",
            side_effect=fake_pairs,
        ):
            normal = tournament._parse_robocode_probe_traces(arena, 7)

    assert json.dumps(normal, sort_keys=True) == json.dumps(expected, sort_keys=True)
