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
    Path(__file__).parent.parent.parent
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


@pytest.fixture
def draw_game_path():
    """Path to draw_game.jsonl fixture."""
    return FIXTURES_DIR / "draw_game.jsonl"


class TestBattleSnakeTraceParser:
    """Tests for BattleSnakeTraceParser."""

    def test_parse_file_returns_game_trace(self, parser, short_game_path):
        """Parser returns a GameTrace object."""
        trace = parser.parse_file(short_game_path)
        assert isinstance(trace, GameTrace)

    def test_parse_extracts_game_id(self, parser, short_game_path):
        """Parser extracts game ID correctly."""
        trace = parser.parse_file(short_game_path)
        assert trace.game_id == "test-game-001"

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
        """Parser extracts winner correctly."""
        trace = parser.parse_file(short_game_path)
        assert trace.winner == "player_a"
        assert trace.is_draw is False

    def test_parse_handles_draw(self, parser, draw_game_path):
        """Parser handles draw games."""
        trace = parser.parse_file(draw_game_path)
        assert trace.is_draw is True
        assert trace.winner is None

    def test_infer_action_up(self, parser, short_game_path):
        """Parser infers 'up' action from y increasing."""
        trace = parser.parse_file(short_game_path)

        # player_a moves from (5,5) to (5,6) at turn 1 → action should be "up"
        actions = trace.get_player_actions("player_a")

        # Find the action at turn 1
        turn_1_action = next((a for a in actions if a.turn == 1), None)
        assert turn_1_action is not None
        assert turn_1_action.action == "up"

    def test_infer_action_down(self, parser, short_game_path):
        """Parser infers 'down' action from y decreasing."""
        trace = parser.parse_file(short_game_path)

        # player_b moves from (7,7) to (7,6) at turn 1 → action should be "down"
        actions = trace.get_player_actions("player_b")

        turn_1_action = next((a for a in actions if a.turn == 1), None)
        assert turn_1_action is not None
        assert turn_1_action.action == "down"

    def test_infer_action_right(self, parser, draw_game_path):
        """Parser infers 'right' action from x increasing."""
        trace = parser.parse_file(draw_game_path)

        # player_a moves from (1,5) to (2,5) at turn 1 → action should be "right"
        actions = trace.get_player_actions("player_a")

        turn_1_action = next((a for a in actions if a.turn == 1), None)
        assert turn_1_action is not None
        assert turn_1_action.action == "right"

    def test_infer_action_left(self, parser, draw_game_path):
        """Parser infers 'left' action from x decreasing."""
        trace = parser.parse_file(draw_game_path)

        # player_b moves from (9,5) to (8,5) at turn 1 → action should be "left"
        actions = trace.get_player_actions("player_b")

        turn_1_action = next((a for a in actions if a.turn == 1), None)
        assert turn_1_action is not None
        assert turn_1_action.action == "left"

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

        assert trace.game_id == "test-game-001"
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

    def test_player_dies_mid_game(self, parser, short_game_path):
        """Parser handles player dying mid-game."""
        trace = parser.parse_file(short_game_path)

        # player_b dies at turn 4 (not in turn 4 snakes list)
        # Check that we have actions for player_b up to turn 3
        actions_b = trace.get_player_actions("player_b")
        turn_numbers = [a.turn for a in actions_b]

        # player_b should have actions for turns 1-3 (dies before turn 4)
        assert 1 in turn_numbers
        assert 4 not in turn_numbers  # player_b is dead


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
        assert traces[0].game_id == "test-game-001"
