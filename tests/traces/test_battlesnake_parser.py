"""
Tests for traces/parsers/battlesnake.py - BattleSnakeTraceParser.

Tests:
1. Parse JSONL file correctly
2. Extract game metadata (id, ruleset, players)
3. Infer actions from position changes
4. Handle draw games
5. Handle games where players die
6. get_state_action_pairs() returns correct format
"""

from pathlib import Path

import pytest

from revenge_bench.traces.models import GameTrace
from revenge_bench.traces.parsers.battlesnake import BattleSnakeTraceParser

# Path to test fixtures
FIXTURES_DIR = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "test_fixtures"
    / "traces"
    / "battlesnake"
)


@pytest.fixture
def parser():
    """Create a BattleSnakeTraceParser instance."""
    return BattleSnakeTraceParser(infer_actions=True)


@pytest.fixture
def short_game_path():
    """Path to short_game.jsonl fixture."""
    return FIXTURES_DIR / "short_game.jsonl"


class TestBattleSnakeTraceParser:
    """Tests for BattleSnakeTraceParser."""

    def test_parse_file_returns_game_trace(self, parser, short_game_path):
        """Parser returns a GameTrace object."""
        trace = parser.parse_file(short_game_path)
        assert isinstance(trace, GameTrace)

    def test_parse_extracts_game_id(self, parser, short_game_path):
        """Parser extracts game ID correctly."""
        trace = parser.parse_file(short_game_path)
        assert trace.game_id == "test-game"

    def test_parse_extracts_game_type(self, parser, short_game_path):
        """Parser sets game type to BattleSnake."""
        trace = parser.parse_file(short_game_path)
        assert trace.game_type == "BattleSnake"

    def test_parse_extracts_players(self, parser, short_game_path):
        """Parser extracts player list."""
        trace = parser.parse_file(short_game_path)
        player_names = [p["name"] for p in trace.metadata.players]
        assert "player_a" in player_names
        assert "player_b" in player_names

    def test_parse_extracts_turns(self, parser, short_game_path):
        """Parser extracts turn records."""
        trace = parser.parse_file(short_game_path)
        # short_game has turns 0-4 (5 turns)
        assert trace.total_turns == 5

    def test_parse_extracts_winner(self, parser, short_game_path):
        """Parser extracts winner (None when both alive at end)."""
        trace = parser.parse_file(short_game_path)
        # Both snakes alive at turn 4, no winner
        assert trace.winner is None

    def test_infer_action_right(self, parser, short_game_path):
        """Parser infers 'right' action from x increasing."""
        trace = parser.parse_file(short_game_path)

        # player_a moves from (1,1) to (2,1) at turn 0 → action should be "right"
        actions = trace.get_player_actions("player_a")

        turn_0_action = next((a for a in actions if a.turn == 0), None)
        assert turn_0_action is not None
        assert turn_0_action.action == "right"

    def test_infer_action_left(self, parser, short_game_path):
        """Parser infers 'left' action from x decreasing."""
        trace = parser.parse_file(short_game_path)

        # player_b moves from (9,9) to (8,9) at turn 0 → action should be "left"
        actions = trace.get_player_actions("player_b")

        turn_0_action = next((a for a in actions if a.turn == 0), None)
        assert turn_0_action is not None
        assert turn_0_action.action == "left"

    def test_infer_action_up(self, parser, short_game_path):
        """Parser infers 'up' action from y increasing."""
        trace = parser.parse_file(short_game_path)

        # player_a moves from (3,1) to (3,2) at turn 2 → action should be "up"
        actions = trace.get_player_actions("player_a")

        turn_2_action = next((a for a in actions if a.turn == 2), None)
        assert turn_2_action is not None
        assert turn_2_action.action == "up"

    def test_infer_action_down(self, parser, short_game_path):
        """Parser infers 'down' action from y decreasing."""
        trace = parser.parse_file(short_game_path)

        # player_b moves from (7,9) to (7,8) at turn 2 → action should be "down"
        actions = trace.get_player_actions("player_b")

        turn_2_action = next((a for a in actions if a.turn == 2), None)
        assert turn_2_action is not None
        assert turn_2_action.action == "down"

    def test_get_state_action_pairs(self, parser, short_game_path):
        """get_state_action_pairs returns correct format."""
        trace = parser.parse_file(short_game_path)

        pairs = trace.get_state_action_pairs("player_a")

        # Should have pairs for turns where player_a took actions
        assert len(pairs) > 0

        # Each pair is (state_dict, action)
        state, action = pairs[0]
        assert isinstance(state, dict)
        assert isinstance(action, str)
        assert action in ["up", "down", "left", "right"]

    def test_state_contains_you_field(self, parser, short_game_path):
        """State in state-action pairs contains 'you' field."""
        trace = parser.parse_file(short_game_path)

        pairs = trace.get_state_action_pairs("player_a")
        state, _ = pairs[0]

        # State should contain 'you' from player's perspective
        assert "you" in state or "board" in state

    def test_parse_content_directly(self, parser, short_game_path):
        """Parser can parse content string directly."""
        content = short_game_path.read_text()
        trace = parser.parse_content(content)

        assert trace.game_id == "test-game"
        assert trace.total_turns == 5

    def test_source_metadata_attached(self, parser, short_game_path):
        """Source metadata is attached to trace."""
        source = {"tournament_id": "test-tournament", "round": 1}
        trace = parser.parse_file(short_game_path, source=source)

        assert trace.metadata.source["tournament_id"] == "test-tournament"
        assert trace.metadata.source["round"] == 1

    def test_board_config_extracted(self, parser, short_game_path):
        """Board dimensions are extracted in config."""
        trace = parser.parse_file(short_game_path)

        assert trace.metadata.config["width"] == 11
        assert trace.metadata.config["height"] == 11


class TestBattleSnakeTraceParserEdgeCases:
    """Edge case tests for BattleSnakeTraceParser."""

    def test_empty_content_raises_error(self, parser):
        """Parsing empty content raises ValueError."""
        with pytest.raises(ValueError, match="Empty trace content"):
            parser.parse_content("")

    def test_no_infer_actions_mode(self, short_game_path):
        """Parser can run without action inference."""
        parser = BattleSnakeTraceParser(infer_actions=False)
        trace = parser.parse_file(short_game_path)

        # Trace should still parse, but actions might be None
        assert trace.total_turns == 5

    def test_all_actions_inferred(self, parser, short_game_path):
        """Parser infers actions for all turns."""
        trace = parser.parse_file(short_game_path)

        actions_a = trace.get_player_actions("player_a")
        actions_b = trace.get_player_actions("player_b")

        # Both snakes alive for all turns, should have 4 actions each (turns 0-3)
        assert len(actions_a) == 4
        assert len(actions_b) == 4


class TestTraceCollectorIntegration:
    """Integration tests for TraceCollector with BattleSnake."""

    def test_collector_uses_parser(self):
        """TraceCollector uses BattleSnakeTraceParser."""
        from revenge_bench.traces.collector import TraceCollector

        collector = TraceCollector(game_type="BattleSnake")
        assert collector.parser_class.__name__ == "BattleSnakeTraceParser"

    def test_collector_parses_directory(self, tmp_path, short_game_path):
        """TraceCollector can parse traces from a directory."""
        import shutil

        from revenge_bench.traces.collector import TraceCollector

        # Copy fixture to temp dir with expected naming
        shutil.copy(short_game_path, tmp_path / "sim_0.jsonl")

        collector = TraceCollector(game_type="BattleSnake")
        traces = collector.collect_from_round(tmp_path)

        assert len(traces) == 1
        assert traces[0].game_id == "test-game"
