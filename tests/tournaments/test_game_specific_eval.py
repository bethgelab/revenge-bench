"""
Tests for game-specific _process_*_traces() methods in InverseStrategyTournament.

Verifies that BattleSnake, Halite, and HuskyBench each produce correct
trace summaries via their dedicated evaluation paths.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Helpers: build a minimal InverseStrategyTournament instance for testing
# =============================================================================


def _make_tournament(game_name: str, learner_name="learner", target_name="target"):
    """Return a lightweight mock of InverseStrategyTournament with the
    game-specific method still callable (it's the real method, just bound
    to a mock self)."""
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

    tournament = MagicMock(spec=InverseStrategyTournament)
    tournament.game = MagicMock()
    tournament.game.name = game_name
    tournament.game.submission = {
        "BattleSnake": "main.py",
        "Halite": "submission/main.py",
        "HuskyBench": "client/player.py",
    }.get(game_name, "main.py")

    tournament.learner_agent = MagicMock()
    tournament.learner_agent.name = learner_name
    tournament.target_agent = MagicMock()
    tournament.target_agent.name = target_name

    tournament.logger = MagicMock()

    # Bind real methods
    tournament._build_trace_summary = (
        InverseStrategyTournament._build_trace_summary.__get__(tournament)
    )
    tournament._process_battlesnake_traces = (
        InverseStrategyTournament._process_battlesnake_traces.__get__(tournament)
    )
    tournament._process_halite_traces = (
        InverseStrategyTournament._process_halite_traces.__get__(tournament)
    )
    tournament._process_huskybench_traces = (
        InverseStrategyTournament._process_huskybench_traces.__get__(tournament)
    )
    tournament._process_traces = InverseStrategyTournament._process_traces.__get__(
        tournament
    )
    return tournament


# =============================================================================
# Fixtures: sim data
# =============================================================================

BATTLESNAKE_TURNS = [
    # Turn 0: snake at (5,5) heading up
    {
        "turn": 0,
        "board": {
            "width": 11,
            "height": 11,
            "food": [{"x": 5, "y": 7}],
            "snakes": [
                {
                    "name": "target",
                    "head": {"x": 5, "y": 5},
                    "body": [{"x": 5, "y": 5}, {"x": 5, "y": 4}],
                    "health": 100,
                },
            ],
        },
    },
    # Turn 1: moved up to (5,6) -> action was "up"
    {
        "turn": 1,
        "board": {
            "width": 11,
            "height": 11,
            "food": [{"x": 5, "y": 7}],
            "snakes": [
                {
                    "name": "target",
                    "head": {"x": 5, "y": 6},
                    "body": [{"x": 5, "y": 6}, {"x": 5, "y": 5}],
                    "health": 99,
                },
            ],
        },
    },
    # Turn 2: moved right to (6,6) -> action was "right"
    {
        "turn": 2,
        "board": {
            "width": 11,
            "height": 11,
            "food": [],
            "snakes": [
                {
                    "name": "target",
                    "head": {"x": 6, "y": 6},
                    "body": [{"x": 6, "y": 6}, {"x": 5, "y": 6}],
                    "health": 98,
                },
            ],
        },
    },
]

HUSKYBENCH_HAND = {
    "gameId": "test-001",
    "playerNames": {"100": "target", "200": "opponent"},
    "blinds": {"small": 5, "big": 10},
    "finalBoard": ["Td", "Ts", "Kh", "Jc", "Jh"],
    "playerHands": {"100": ["Ah", "Ks"], "200": ["7c", "2d"]},
    "playerMoney": {
        "initialAmount": 10000,
        "finalMoney": {"100": 10030, "200": 9970},
        "gameScores": {"100": 30, "200": -30},
    },
    "rounds": {
        "0": {
            "pot": 30,
            "bets": {"100": 15, "200": 15},
            "actions": {"100": "RAISE", "200": "CALL"},
            "action_sequence": [
                {
                    "player": 100,
                    "action": "RAISE",
                    "amount": 15,
                    "timestamp": 1000,
                    "pot_after_action": 15,
                    "total_pot_after_action": 15,
                },
                {
                    "player": 200,
                    "action": "CALL",
                    "amount": 15,
                    "timestamp": 1001,
                    "pot_after_action": 15,
                    "total_pot_after_action": 30,
                },
            ],
        },
    },
}


@pytest.fixture
def bs_round_dir(tmp_path):
    """Round dir with a BattleSnake sim file."""
    rd = tmp_path / "rounds" / "0"
    rd.mkdir(parents=True)
    sim = rd / "sim_0.jsonl"
    sim.write_text("\n".join(json.dumps(t) for t in BATTLESNAKE_TURNS))
    return rd


@pytest.fixture
def hb_round_dir(tmp_path):
    """Round dir with a HuskyBench game_log file."""
    rd = tmp_path / "rounds" / "0"
    rd.mkdir(parents=True)
    gl = rd / "game_log_0_test-001.json"
    gl.write_text(json.dumps(HUSKYBENCH_HAND))
    return rd


@pytest.fixture
def halite_round_dir(tmp_path):
    """Round dir with a minimal Halite .hlt file."""
    rd = tmp_path / "rounds" / "0"
    rd.mkdir(parents=True)
    # Minimal .hlt: 2 players, 2 frames, 4x4 map
    hlt = {
        "version": 1,
        "width": 4,
        "height": 4,
        "num_players": 2,
        "num_frames": 2,
        "player_names": ["target", "opponent"],
        "productions": [[1] * 4 for _ in range(4)],
        "frames": [
            {
                "moves": [],
                "cells": [
                    {"owner": 1, "x": 0, "y": 0, "production": 1, "strength": 10},
                    {"owner": 2, "x": 3, "y": 3, "production": 1, "strength": 10},
                ],
            },
            {
                "moves": [{"owner": 1, "x": 0, "y": 0, "direction": 1}],
                "cells": [
                    {"owner": 1, "x": 0, "y": 0, "production": 1, "strength": 5},
                    {"owner": 1, "x": 1, "y": 0, "production": 1, "strength": 5},
                    {"owner": 2, "x": 3, "y": 3, "production": 1, "strength": 20},
                ],
            },
        ],
    }
    hlt_file = rd / "12345-67890.hlt"
    hlt_file.write_text(json.dumps(hlt))
    return rd


# =============================================================================
# Tests
# =============================================================================


class TestDispatch:
    """Test that _process_traces dispatches correctly."""

    def test_dispatch_battlesnake(self, bs_round_dir):
        t = _make_tournament("BattleSnake")
        t._process_battlesnake_traces = MagicMock(return_value={"dispatched": True})
        result = t._process_traces(bs_round_dir, 0)
        t._process_battlesnake_traces.assert_called_once_with(bs_round_dir, 0)
        assert result == {"dispatched": True}

    def test_dispatch_halite(self, halite_round_dir):
        t = _make_tournament("Halite")
        t._process_halite_traces = MagicMock(return_value={"dispatched": True})
        result = t._process_traces(halite_round_dir, 0)
        t._process_halite_traces.assert_called_once_with(halite_round_dir, 0)
        assert result == {"dispatched": True}

    def test_dispatch_huskybench(self, hb_round_dir):
        t = _make_tournament("HuskyBench")
        t._process_huskybench_traces = MagicMock(return_value={"dispatched": True})
        result = t._process_traces(hb_round_dir, 0)
        t._process_huskybench_traces.assert_called_once_with(hb_round_dir, 0)
        assert result == {"dispatched": True}

    def test_unsupported_game_returns_none(self, bs_round_dir):
        t = _make_tournament("UnknownGame")
        result = t._process_traces(bs_round_dir, 0)
        assert result is None
        t.logger.warning.assert_called()


class TestBattleSnakeTraces:
    """Test _process_battlesnake_traces end-to-end."""

    def test_perfect_match(self, bs_round_dir):
        """Learner that always returns target's action -> distance 0."""
        t = _make_tournament("BattleSnake")

        # Mock _setup_learner_for_eval to return a dummy dir
        t._setup_learner_for_eval = MagicMock(return_value=bs_round_dir)

        # Mock _load_learner_module to set a perfect move function
        def perfect_move(state):
            # Extract what the target did from position changes
            return {"move": "up"}  # We'll make the learner always say "up"

        def mock_load(code_dir):
            t._learner_move_func = lambda s: {"move": "up"}
            return True

        t._load_learner_module = mock_load

        # Mock _query_learner to use the loaded function
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t._query_learner = InverseStrategyTournament._query_learner.__get__(t)

        result = t._process_battlesnake_traces(bs_round_dir, 0)

        assert result is not None
        assert result["game"] == "BattleSnake"
        assert result["evaluation_type"] == "offline"
        # 2 turns (pairs from 3 turn records)
        assert result["total_actions"] == 2
        # First action is "up" (matches), second is "right" (doesn't match "up")
        assert result["mean_distance"] > 0
        assert (bs_round_dir / "traces.json").exists()

    def test_no_sim_files(self, tmp_path):
        """Empty round dir -> None."""
        rd = tmp_path / "empty"
        rd.mkdir()
        t = _make_tournament("BattleSnake")
        result = t._process_battlesnake_traces(rd, 0)
        assert result is None

    def test_summary_saved(self, bs_round_dir):
        """traces.json is written correctly."""
        t = _make_tournament("BattleSnake")
        t._setup_learner_for_eval = MagicMock(return_value=bs_round_dir)

        def mock_load(code_dir):
            t._learner_move_func = lambda s: {"move": "up"}
            return True

        t._load_learner_module = mock_load

        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t._query_learner = InverseStrategyTournament._query_learner.__get__(t)

        t._process_battlesnake_traces(bs_round_dir, 0)
        saved = json.loads((bs_round_dir / "traces.json").read_text())
        assert saved["round"] == 0
        assert saved["game"] == "BattleSnake"
        assert saved["learner"] == "learner"
        assert saved["target"] == "target"
        assert "per_simulation" in saved
        assert len(saved["per_simulation"]) == 1


class TestHaliteTraces:
    """Test _process_halite_traces end-to-end."""

    def test_no_hlt_files(self, tmp_path):
        """Empty round dir -> None."""
        rd = tmp_path / "empty"
        rd.mkdir()
        t = _make_tournament("Halite")
        result = t._process_halite_traces(rd, 0)
        assert result is None

    def test_no_target_hlt_name(self, halite_round_dir):
        """Missing _target_hlt_name -> error dict."""
        t = _make_tournament("Halite")
        t._setup_compiled_learner = MagicMock(return_value="./run_bot")
        # Don't set _target_hlt_name
        del t._target_hlt_name
        result = t._process_halite_traces(halite_round_dir, 0)
        assert isinstance(result, dict) and "error" in result

    def test_setup_failure_surfaces_error(self, halite_round_dir):
        """Any RuntimeError from _setup_compiled_learner (copy failure,
        missing submission, missing main file, compile error, timeout) must
        surface as an error dict with the specific reason — no longer
        masked as the misleading 'Failed to compile learner bot'."""
        t = _make_tournament("Halite")
        t._setup_compiled_learner = MagicMock(
            side_effect=RuntimeError("Failed to copy learner code: simulated detail")
        )
        result = t._process_halite_traces(halite_round_dir, 0)
        assert isinstance(result, dict) and "error" in result
        # The specific cause is preserved verbatim (not collapsed to
        # the old "Failed to compile learner bot" string).
        assert "Failed to copy learner code" in result["error"]
        assert "simulated detail" in result["error"]
        assert "syntax errors" not in result["error"]

    @patch("revenge_bench.traces.parsers.halite.extract_state_action_pairs")
    @patch("revenge_bench.traces.parsers.halite.load_hlt_file")
    @patch("revenge_bench.traces.parsers.halite.query_compiled_bot")
    @patch("revenge_bench.traces.parsers.halite.actions_distance")
    def test_success(
        self, mock_dist, mock_query, mock_load_hlt, mock_extract, halite_round_dir
    ):
        """End to end with mocked parser functions."""
        t = _make_tournament("Halite")
        t._setup_compiled_learner = MagicMock(return_value="./run_bot")
        t._target_hlt_name = "target"

        # Parser returns 2 state-action pairs
        mock_extract.return_value = [
            ({"turn": 0}, [{"x": 0, "y": 0, "direction": 1}]),
            ({"turn": 1}, []),
        ]
        mock_load_hlt.return_value = {"player_names": ["target", "opponent"]}
        mock_query.return_value = [
            [{"x": 0, "y": 0, "direction": 1}],  # matches
            [{"x": 1, "y": 1, "direction": 2}],  # doesn't matter
        ]
        mock_dist.side_effect = [0.0, 0.5]  # first matches, second differs

        result = t._process_halite_traces(halite_round_dir, 0)

        assert result is not None
        assert result["game"] == "Halite"
        assert result["evaluation_type"] == "offline_subprocess"
        assert result["total_actions"] == 2
        assert result["total_distance"] == 0.5
        assert (halite_round_dir / "traces.json").exists()


class TestHuskyBenchTraces:
    """Test _process_huskybench_traces end-to-end."""

    def test_no_game_logs(self, tmp_path):
        """Empty round dir -> None."""
        rd = tmp_path / "empty"
        rd.mkdir()
        t = _make_tournament("HuskyBench")
        result = t._process_huskybench_traces(rd, 0)
        assert result is None

    def test_no_learner_code(self, hb_round_dir):
        """Learner code copy fails -> error dict."""
        t = _make_tournament("HuskyBench")
        t._setup_learner_for_eval = MagicMock(return_value=None)
        result = t._process_huskybench_traces(hb_round_dir, 0)
        assert isinstance(result, dict) and "error" in result

    def test_success_with_mock_bot(self, hb_round_dir, tmp_path):
        """Full eval with a mock Bot subclass that always folds."""

        t = _make_tournament("HuskyBench")

        # Create a fake learner workspace with player.py
        ws = tmp_path / "learner_code" / "workspace" / "client"
        ws.mkdir(parents=True)

        # Write the type modules the player.py imports
        type_dir = ws / "type"
        type_dir.mkdir()
        (type_dir / "__init__.py").write_text("")
        (type_dir / "poker_action.py").write_text(
            "from enum import Enum\n"
            "class PokerAction(Enum):\n"
            "    FOLD = 1\n"
            "    CHECK = 2\n"
            "    CALL = 3\n"
            "    RAISE = 4\n"
            "    ALL_IN = 5\n"
        )
        (type_dir / "round_state.py").write_text(
            "from dataclasses import dataclass\n"
            "from typing import Dict, List, Any\n"
            "@dataclass\n"
            "class RoundStateClient:\n"
            "    round_num: int\n"
            "    round: str\n"
            "    community_cards: List[str]\n"
            "    pot: int\n"
            "    current_player: List[int]\n"
            "    current_bet: int\n"
            "    min_raise: int\n"
            "    max_raise: int\n"
            "    player_bets: Dict[str, int]\n"
            "    player_actions: Dict[str, str]\n"
            "    player_money: Dict[str, int] = None\n"
            "    side_pots: List[Dict[str, Any]] = None\n"
        )
        (ws / "bot.py").write_text(
            "from abc import ABC, abstractmethod\n"
            "from typing import List, Tuple\n"
            "from type.round_state import RoundStateClient\n"
            "from type.poker_action import PokerAction\n"
            "class Bot(ABC):\n"
            "    def __init__(self): self.id = None\n"
            "    def on_start(self, *a, **k): pass\n"
            "    def on_round_start(self, *a, **k): pass\n"
            "    @abstractmethod\n"
            "    def get_action(self, rs, rc): pass\n"
            "    def on_end_round(self, *a, **k): pass\n"
            "    def on_end_game(self, *a, **k): pass\n"
        )
        (ws / "player.py").write_text(
            "from bot import Bot\n"
            "from type.poker_action import PokerAction\n"
            "from type.round_state import RoundStateClient\n"
            "class SimplePlayer(Bot):\n"
            "    def __init__(self): super().__init__()\n"
            "    def on_start(self, chips, hands, blind, bb, sb, all_p):\n"
            "        self.my_hand = hands\n"
            "    def on_round_start(self, rs, rc): pass\n"
            "    def get_action(self, rs, rc):\n"
            "        return (PokerAction.FOLD, 0)\n"
            "    def on_end_round(self, *a): pass\n"
            "    def on_end_game(self, *a): pass\n"
        )

        t._setup_learner_for_eval = MagicMock(return_value=tmp_path / "learner_code")

        result = t._process_huskybench_traces(hb_round_dir, 0)

        assert result is not None
        assert result["game"] == "HuskyBench"
        assert result["evaluation_type"] == "offline_bot_class"
        # The sample hand has 1 target action (player 100 = target has RAISE in round 0)
        assert result["total_actions"] >= 1
        assert "mean_distance" in result
        assert (hb_round_dir / "traces.json").exists()

        # Bot always folds, target raised -> distance should be > 0
        assert result["mean_distance"] > 0


class TestBuildTraceSummary:
    """Test the shared _build_trace_summary helper."""

    def test_empty_input(self, tmp_path):
        t = _make_tournament("BattleSnake")
        result = t._build_trace_summary(
            0, "BattleSnake", "target", "offline", 0, 0.0, [], [], tmp_path
        )
        assert result["total_actions"] == 0
        assert result["mean_distance"] == float("inf")
        assert (tmp_path / "traces.json").exists()

    def test_single_sim(self, tmp_path):
        t = _make_tournament("BattleSnake")
        per_sim = [
            {
                "total": 3,
                "mean_distance": 0.25,
                "distance_sum": 0.75,
                "num_nonzero": 2,
                "file": "sim.jsonl",
            }
        ]
        result = t._build_trace_summary(
            1, "BattleSnake", "target", "offline", 3, 0.75, per_sim, [], tmp_path
        )
        assert result["total_actions"] == 3
        assert result["mean_distance"] == 0.25
        assert result["distance_std"] == 0.0  # single sim -> 0 stdev

    def test_multi_sim(self, tmp_path):
        t = _make_tournament("BattleSnake")
        per_sim = [
            {
                "total": 2,
                "mean_distance": 0.0,
                "distance_sum": 0.0,
                "num_nonzero": 0,
                "file": "s1.jsonl",
            },
            {
                "total": 2,
                "mean_distance": 1.0,
                "distance_sum": 2.0,
                "num_nonzero": 2,
                "file": "s2.jsonl",
            },
        ]
        result = t._build_trace_summary(
            2, "BattleSnake", "target", "offline", 4, 2.0, per_sim, [], tmp_path
        )
        assert result["mean_distance"] == 0.5
        assert result["mean_distance_across_sims"] == 0.5
        assert result["distance_std"] > 0
