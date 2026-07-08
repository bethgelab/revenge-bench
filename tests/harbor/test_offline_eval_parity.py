"""Differential parity test: native tournament vs Harbor in-container scorer.

The whole point of the ``revenge_bench.traces.offline_eval`` refactor is that
the Harbor verifier reproduces the *exact* result of the native tournament for a
given round. This test proves it end-to-end for BattleSnake: it drives the
**real** ``InverseStrategyTournament._process_battlesnake_traces`` (bound to a
lightweight mock ``self``) and the Harbor scorer entry point
(``evaluate_battlesnake_submission``) over the *same* frozen traces and the
*same* ``main.py``, then asserts the two summaries are byte-identical.

Because both paths call the same shared functions, this also transitively
validates the deployed ``score_task.py`` (which writes ``eval.json`` from
``evaluate_battlesnake_submission``).

Requires ``zstandard`` (the only import-time dep of the BattleSnake parser).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("zstandard")


def _turn(turn_num: int, head_x: int, head_y: int, name: str = "target") -> dict:
    """Minimal BattleSnake turn record the parser recognises (has 'board')."""
    snake = {
        "id": "s1",
        "name": name,
        "health": 100,
        "body": [{"x": head_x, "y": head_y}],
        "head": {"x": head_x, "y": head_y},
        "length": 1,
    }
    return {
        "turn": turn_num,
        "board": {
            "height": 11,
            "width": 11,
            "snakes": [snake],
            "food": [],
            "hazards": [],
        },
        "you": snake,
    }


def _write_round(round_dir: Path, target_name: str = "target") -> None:
    """Target path: right, then up -> a mix of matching / non-matching actions."""
    round_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        {"id": "game-1", "ruleset": {"name": "standard"}},  # metadata (no board)
        _turn(0, 0, 5, target_name),
        _turn(1, 1, 5, target_name),  # moved right
        _turn(2, 1, 6, target_name),  # moved up
        {"winnerName": target_name, "isDraw": False},  # results (no board)
    ]
    (round_dir / "sim_0.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n"
    )


# A policy that always says "right": matches turn 0's action, misses turn 1's
# ("up"), so the summary carries a non-zero distance entry (exercises the full
# per-simulation / nonzero_distances schema).
_MAIN_PY = "def move(state):\n    return 'right'\n"


def _run_tournament_path(
    round_dir: Path,
    code_dir: Path,
    *,
    round_num: int,
    learner_name: str,
    target_name: str,
) -> dict:
    """Invoke the REAL tournament BattleSnake scorer bound to a mock ``self``."""
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

    t = MagicMock(spec=InverseStrategyTournament)
    t.game = MagicMock()
    t.game.name = "BattleSnake"
    t.game.submission = "main.py"
    t.learner_agent = MagicMock()
    t.learner_agent.name = learner_name
    t.target_agent = MagicMock()
    t.target_agent.name = target_name
    t.logger = MagicMock()

    # Bind the real methods under test.
    t._process_battlesnake_traces = (
        InverseStrategyTournament._process_battlesnake_traces.__get__(t)
    )
    t._build_trace_summary = InverseStrategyTournament._build_trace_summary.__get__(t)
    t._load_learner_module = InverseStrategyTournament._load_learner_module.__get__(t)
    t._query_learner = InverseStrategyTournament._query_learner.__get__(t)

    # The only container-coupled step: hand the scorer the local code dir that
    # holds main.py (in-container, copy_from_container would have produced this).
    t._setup_learner_for_eval = MagicMock(return_value=code_dir)

    return t._process_battlesnake_traces(round_dir, round_num)


def _run_harbor_path(
    round_dir: Path,
    code_dir: Path,
    *,
    round_num: int,
    learner_name: str,
    target_name: str,
) -> dict:
    """Invoke the Harbor scorer entry point (what score_task.py calls)."""
    from revenge_bench.traces.offline_eval import evaluate_battlesnake_submission

    return evaluate_battlesnake_submission(
        round_dir=round_dir,
        round_num=round_num,
        target_name=target_name,
        learner_name=learner_name,
        learner_code_dir=code_dir,
        submission="main.py",
    )


def test_tournament_and_harbor_scorer_are_byte_identical(tmp_path: Path):
    round_num = 0
    learner_name = "learner"
    target_name = "target"

    # Native tournament round layout.
    tourn_round = tmp_path / "tournament" / "rounds" / "0"
    _write_round(tourn_round, target_name)
    tourn_code = tmp_path / "tournament" / "code"
    tourn_code.mkdir(parents=True)
    (tourn_code / "main.py").write_text(_MAIN_PY)

    # Harbor labels layout (identical relative structure: sim_0.jsonl at root).
    harbor_round = tmp_path / "harbor" / "labels"
    _write_round(harbor_round, target_name)
    harbor_code = tmp_path / "harbor" / "workspace"
    harbor_code.mkdir(parents=True)
    (harbor_code / "main.py").write_text(_MAIN_PY)

    tournament_summary = _run_tournament_path(
        tourn_round,
        tourn_code,
        round_num=round_num,
        learner_name=learner_name,
        target_name=target_name,
    )
    harbor_summary = _run_harbor_path(
        harbor_round,
        harbor_code,
        round_num=round_num,
        learner_name=learner_name,
        target_name=target_name,
    )

    # Sanity: the round actually scored actions with a mix of match/mismatch.
    assert tournament_summary["total_actions"] == 2
    assert tournament_summary["mean_distance"] == 0.5
    assert len(tournament_summary["nonzero_distances"]) == 1

    # The core requirement: identical result for one round, byte for byte.
    assert json.dumps(tournament_summary, sort_keys=True) == json.dumps(
        harbor_summary, sort_keys=True
    )

    # And the tournament persisted the same object to traces.json.
    persisted = json.loads((tourn_round / "traces.json").read_text())
    assert json.dumps(persisted, sort_keys=True) == json.dumps(
        harbor_summary, sort_keys=True
    )


def _write_halite_round(round_dir: Path, target_name: str = "target") -> None:
    """Minimal Halite replay: target stays, then moves east."""
    round_dir.mkdir(parents=True, exist_ok=True)
    replay = {
        "version": 11,
        "width": 1,
        "height": 1,
        "num_players": 1,
        "num_frames": 3,
        "player_names": [target_name],
        "productions": [[1]],
        "frames": [
            [[[1, 10]]],
            [[[1, 10]]],
            [[[1, 10]]],
        ],
        "moves": [
            [[0]],
            [[2]],
        ],
    }
    (round_dir / "sim_0.hlt").write_text(json.dumps(replay))


def test_halite_tournament_and_shared_scorer_are_byte_identical(tmp_path: Path):
    from unittest.mock import patch

    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
    from revenge_bench.traces.offline_eval import (
        evaluate_halite_submission_with_action_provider,
    )

    round_num = 0
    learner_name = "learner"
    target_name = "target"
    learner_actions = [
        [[0, 0, 0]],  # matches target turn 0
        [[0, 0, 0]],  # misses target turn 1, which moves east
    ]

    round_dir = tmp_path / "halite" / "rounds" / "0"
    _write_halite_round(round_dir, target_name)

    tournament = MagicMock(spec=InverseStrategyTournament)
    tournament.learner_agent = MagicMock()
    tournament.learner_agent.name = learner_name
    tournament.logger = MagicMock()
    tournament._target_hlt_name = target_name
    tournament._setup_compiled_learner = MagicMock(return_value="dummy-executable")
    tournament._process_halite_traces = (
        InverseStrategyTournament._process_halite_traces.__get__(tournament)
    )

    with patch(
        "revenge_bench.traces.parsers.halite.query_compiled_bot",
        return_value=learner_actions,
    ):
        tournament_summary = tournament._process_halite_traces(round_dir, round_num)

    shared_summary = evaluate_halite_submission_with_action_provider(
        round_dir=round_dir,
        round_num=round_num,
        target_hlt_name=target_name,
        learner_name=learner_name,
        action_provider=lambda _hlt_data, _player_tag: learner_actions,
        evaluation_type="offline_subprocess",
    )

    assert tournament_summary["total_actions"] == 2
    assert tournament_summary["mean_distance"] == 0.5
    assert len(tournament_summary["nonzero_distances"]) == 1
    assert json.dumps(tournament_summary, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )


def test_robocode_tournament_and_shared_scorer_are_byte_identical(tmp_path: Path):
    from unittest.mock import patch

    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
    from revenge_bench.traces.offline_eval import (
        evaluate_robocode_submission_with_move_provider,
        load_move_function,
        make_inprocess_move_provider,
    )

    round_num = 0
    learner_name = "learner"
    target_name = "target"
    round_dir = tmp_path / "robocode" / "rounds" / "0" / "opp_0"
    round_dir.mkdir(parents=True)
    (round_dir / "record_0.xml").write_text("<record></record>")
    (round_dir / "_pkg_to_agent.json").write_text(json.dumps({"p0": "target", "p1": "opponent"}))

    code_dir = tmp_path / "robocode" / "code"
    code_dir.mkdir()
    main_py = code_dir / "main.py"
    main_py.write_text(
        "def move(state):\n"
        "    return {'velocity': 1, 'turn_body': 0, 'turn_gun': 0, 'turn_radar': 0, 'fire_power': 0}\n"
    )

    def fake_pairs(path, player_name):
        assert Path(path).name == "record_0.xml"
        assert player_name == "p0"
        return [
            (
                {"tick": 0},
                {
                    "velocity": 1,
                    "turn_body": 0,
                    "turn_gun": 0,
                    "turn_radar": 0,
                    "fire_power": 0,
                },
            ),
            (
                {"tick": 1},
                {
                    "velocity": -1,
                    "turn_body": 0,
                    "turn_gun": 0,
                    "turn_radar": 0,
                    "fire_power": 0,
                },
            ),
        ]

    tournament = MagicMock(spec=InverseStrategyTournament)
    tournament.learner_agent = MagicMock()
    tournament.learner_agent.name = learner_name
    tournament.target_agent = MagicMock()
    tournament.target_agent.name = target_name
    tournament.game = MagicMock()
    tournament.game.submission = "main.py"
    tournament.logger = MagicMock()
    tournament._setup_learner_for_eval = MagicMock(return_value=code_dir)
    tournament._process_robocode_traces = (
        InverseStrategyTournament._process_robocode_traces.__get__(tournament)
    )
    tournament._load_learner_module = InverseStrategyTournament._load_learner_module.__get__(tournament)
    tournament._query_learner = InverseStrategyTournament._query_learner.__get__(tournament)

    module, move_func, _kind = load_move_function(main_py, code_dir)
    assert module is not None
    assert move_func is not None

    with patch(
        "revenge_bench.traces.parsers.robocode.extract_state_action_pairs",
        side_effect=fake_pairs,
    ):
        tournament_summary = tournament._process_robocode_traces(round_dir.parent, round_num)
        shared_summary = evaluate_robocode_submission_with_move_provider(
            round_dir=round_dir.parent,
            round_num=round_num,
            target_name=target_name,
            learner_name=learner_name,
            move_provider=make_inprocess_move_provider(move_func),
            parser_target_name="p0",
            evaluation_type="offline",
        )

    assert tournament_summary["total_actions"] == 2
    assert len(tournament_summary["nonzero_distances"]) == 1
    assert json.dumps(tournament_summary, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )

    persisted = json.loads((round_dir.parent / "traces.json").read_text())
    assert json.dumps(persisted, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )


def test_robocode_shared_scorer_resolves_target_alias_per_opponent(tmp_path: Path):
    from unittest.mock import patch

    from revenge_bench.traces.offline_eval import (
        evaluate_robocode_submission_with_move_provider,
    )

    round_dir = tmp_path / "robocode" / "rounds" / "0"
    opp0 = round_dir / "opp_0"
    opp1 = round_dir / "opp_1"
    opp0.mkdir(parents=True)
    opp1.mkdir(parents=True)
    (opp0 / "record_0.xml").write_text("<record></record>")
    (opp1 / "record_0.xml").write_text("<record></record>")
    (opp0 / "_pkg_to_agent.json").write_text(json.dumps({"p0": "target", "p1": "opponent"}))
    (opp1 / "_pkg_to_agent.json").write_text(json.dumps({"p0": "opponent", "p1": "target"}))

    seen: list[tuple[str, str]] = []

    def fake_pairs(path, player_name):
        seen.append((Path(path).parent.name, player_name))
        return [
            (
                {"tick": 0},
                {
                    "velocity": 1,
                    "turn_body": 0,
                    "turn_gun": 0,
                    "turn_radar": 0,
                    "fire_power": 0,
                },
            )
        ]

    with patch(
        "revenge_bench.traces.parsers.robocode.extract_state_action_pairs",
        side_effect=fake_pairs,
    ):
        summary = evaluate_robocode_submission_with_move_provider(
            round_dir=round_dir,
            round_num=0,
            target_name="target",
            learner_name="learner",
            move_provider=lambda _state: {
                "velocity": 1,
                "turn_body": 0,
                "turn_gun": 0,
                "turn_radar": 0,
                "fire_power": 0,
            },
        )

    assert seen == [("opp_0", "p0"), ("opp_1", "p1")]
    assert summary["total_actions"] == 2
    assert summary["mean_distance"] == 0.0


def _write_robotrumble_round(round_dir: Path) -> None:
    round_dir.mkdir(parents=True, exist_ok=True)
    replay = {
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
            },
            {
                "turn": 2,
                "state": {
                    "turn": 2,
                    "objs": {
                        "b1": {
                            "obj_type": "Unit",
                            "type": "Soldier",
                            "team": "Blue",
                            "coords": [2, 1],
                            "health": 5,
                        },
                        "r1": {
                            "obj_type": "Unit",
                            "type": "Soldier",
                            "team": "Red",
                            "coords": [3, 1],
                            "health": 5,
                        },
                    },
                },
                "robot_actions": {
                    "b1": {"Ok": {"type": "Move", "direction": "South"}},
                    "r1": {"Ok": {"type": "Move", "direction": "North"}},
                },
            },
        ],
    }
    (round_dir / "sim_0.json").write_text(json.dumps(replay))
    (round_dir / "_target_team.txt").write_text("Blue\n")


def test_robotrumble_tournament_and_shared_scorer_are_byte_identical(
    tmp_path: Path,
):
    from unittest.mock import patch

    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
    from revenge_bench.traces.offline_eval import (
        evaluate_robotrumble_submission_with_action_provider,
    )

    round_num = 0
    learner_name = "learner"
    learner_actions = [
        [{"unit_id": "b1", "action": {"type": "Move", "direction": "East"}}],
        [{"unit_id": "b1", "action": {"type": "Move", "direction": "East"}}],
    ]

    round_dir = tmp_path / "robotrumble" / "rounds" / "0"
    _write_robotrumble_round(round_dir)
    code_dir = tmp_path / "robotrumble" / "code" / "workspace"
    code_dir.mkdir(parents=True)
    (code_dir / "robot.js").write_text("function robot(state, unit) {}\n")

    tournament = MagicMock(spec=InverseStrategyTournament)
    tournament.learner_agent = MagicMock()
    tournament.learner_agent.name = learner_name
    tournament.logger = MagicMock()
    tournament._setup_learner_for_eval = MagicMock(return_value=code_dir.parent)
    tournament._process_robotrumble_traces = (
        InverseStrategyTournament._process_robotrumble_traces.__get__(tournament)
    )

    with patch(
        "revenge_bench.traces.offline_eval.make_robotrumble_js_action_provider",
        return_value=lambda _inputs: learner_actions,
    ):
        tournament_summary = tournament._process_robotrumble_traces(
            round_dir, round_num
        )

    shared_summary = evaluate_robotrumble_submission_with_action_provider(
        round_dir=round_dir,
        round_num=round_num,
        learner_name=learner_name,
        action_provider=lambda _inputs: learner_actions,
        fallback_target_team="Blue",
        evaluation_type="offline",
    )

    assert tournament_summary["total_actions"] == 2
    assert tournament_summary["mean_distance"] == 0.25
    assert len(tournament_summary["nonzero_distances"]) == 1
    assert json.dumps(tournament_summary, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )

    persisted = json.loads((round_dir / "traces.json").read_text())
    assert json.dumps(persisted, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )


def test_huskybench_tournament_and_shared_scorer_are_byte_identical(tmp_path: Path):
    from unittest.mock import patch

    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
    from revenge_bench.traces.offline_eval import (
        evaluate_huskybench_submission_with_action_provider,
    )

    round_num = 0
    learner_name = "learner"
    target_name = "target"
    round_dir = tmp_path / "huskybench" / "rounds" / "0"
    round_dir.mkdir(parents=True)
    fixture = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "test_fixtures"
        / "traces"
        / "huskybench"
        / "short_game.json"
    )
    (round_dir / "game_log_0.json").write_text(fixture.read_text())

    code_dir = tmp_path / "huskybench" / "code" / "workspace"
    submission = code_dir / "client" / "player.py"
    submission.parent.mkdir(parents=True)
    submission.write_text("# scorer provider is patched in this test\n")

    provider = lambda _state: "CHECK"

    tournament = MagicMock(spec=InverseStrategyTournament)
    tournament.learner_agent = MagicMock()
    tournament.learner_agent.name = learner_name
    tournament.target_agent = MagicMock()
    tournament.target_agent.name = target_name
    tournament.game = MagicMock()
    tournament.game.submission = "client/player.py"
    tournament.logger = MagicMock()
    tournament._setup_learner_for_eval = MagicMock(return_value=code_dir.parent)
    tournament._process_huskybench_traces = (
        InverseStrategyTournament._process_huskybench_traces.__get__(tournament)
    )

    with patch(
        "revenge_bench.traces.offline_eval.make_huskybench_bot_action_provider",
        return_value=(provider, None),
    ):
        tournament_summary = tournament._process_huskybench_traces(round_dir, round_num)

    shared_summary = evaluate_huskybench_submission_with_action_provider(
        round_dir=round_dir,
        round_num=round_num,
        target_name=target_name,
        learner_name=learner_name,
        action_provider=provider,
        evaluation_type="offline_bot_class",
    )

    assert tournament_summary["total_actions"] == 3
    assert len(tournament_summary["nonzero_distances"]) == 2
    assert json.dumps(tournament_summary, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )

    persisted = json.loads((round_dir / "traces.json").read_text())
    assert json.dumps(persisted, sort_keys=True) == json.dumps(
        shared_summary, sort_keys=True
    )
