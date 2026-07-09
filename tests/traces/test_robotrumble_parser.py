"""
Tests for RobotRumble trace parser.
"""
from pathlib import Path

import pytest

from revenge_bench.traces.models import GameTrace
from revenge_bench.traces.parsers.robotrumble import RobotRumbleTraceParser


@pytest.fixture
def parser():
    return RobotRumbleTraceParser()


@pytest.fixture
def parser_with_names():
    return RobotRumbleTraceParser(player_names={"Blue": "player_a", "Red": "player_b"})


@pytest.fixture
def fixtures_dir():
    return (
        Path(__file__).resolve().parents[2]
        / "data"
        / "test_fixtures"
        / "traces"
        / "robotrumble"
    )


@pytest.fixture
def short_game_path(fixtures_dir):
    return fixtures_dir / "short_game.json"


@pytest.fixture
def draw_game_path(fixtures_dir):
    return fixtures_dir / "draw_game.json"


class TestRobotRumbleTraceParser:
    """Tests for basic RobotRumble parsing functionality."""

    def test_parse_file_returns_game_trace(self, parser, short_game_path):
        """Parser returns a GameTrace object."""
        trace = parser.parse_file(short_game_path)
        assert isinstance(trace, GameTrace)

    def test_parse_extracts_game_type(self, parser, short_game_path):
        """Parser sets game_type to RobotRumble."""
        trace = parser.parse_file(short_game_path)
        assert trace.game_type == "RobotRumble"

    def test_parse_extracts_winner(self, parser, short_game_path):
        """Parser extracts winner correctly."""
        trace = parser.parse_file(short_game_path)
        # Without player_names, winner is just the team name
        assert trace.winner == "Red"
        assert trace.is_draw is False

    def test_parse_extracts_winner_with_names(self, parser_with_names, short_game_path):
        """Parser maps team to player name for winner."""
        trace = parser_with_names.parse_file(short_game_path)
        assert trace.winner == "player_b"  # Red -> player_b

    def test_parse_handles_draw(self, parser, draw_game_path):
        """Parser handles draw games (winner=null)."""
        trace = parser.parse_file(draw_game_path)
        assert trace.winner is None
        assert trace.is_draw is True

    def test_parse_extracts_turns(self, parser, short_game_path):
        """Parser extracts all turns."""
        trace = parser.parse_file(short_game_path)
        assert len(trace.turns) == 4

    def test_parse_extracts_board_size(self, parser, short_game_path):
        """Parser infers board size from wall positions."""
        trace = parser.parse_file(short_game_path)
        assert trace.metadata.config["width"] == 5
        assert trace.metadata.config["height"] == 5

    def test_parse_extracts_initial_units(self, parser, short_game_path):
        """Parser counts initial units per team."""
        trace = parser.parse_file(short_game_path)
        assert trace.metadata.config["initial_units_blue"] == 1
        assert trace.metadata.config["initial_units_red"] == 1

    def test_actions_include_unit_id(self, parser, short_game_path):
        """Actions include unit_id in action dict."""
        trace = parser.parse_file(short_game_path)

        turn0_actions = trace.turns[0].actions
        assert len(turn0_actions) == 2

        # Check that actions have unit_id
        for action in turn0_actions:
            assert "unit_id" in action.action
            assert "action" in action.action

    def test_move_action_format(self, parser, short_game_path):
        """Move actions are formatted as Move:Direction."""
        trace = parser.parse_file(short_game_path)

        # Turn 0: unit 100 moves East, unit 101 moves West
        turn0_actions = trace.turns[0].actions

        blue_action = next(a for a in turn0_actions if a.player_id == "Blue")
        assert blue_action.action["action"] == "Move:East"

        red_action = next(a for a in turn0_actions if a.player_id == "Red")
        assert red_action.action["action"] == "Move:West"

    def test_attack_action_format(self, parser, short_game_path):
        """Attack actions are formatted as Attack:Direction."""
        trace = parser.parse_file(short_game_path)

        # Turn 2: unit 100 attacks North, unit 101 attacks South
        turn2_actions = trace.turns[2].actions

        blue_action = next(a for a in turn2_actions if a.player_id == "Blue")
        assert blue_action.action["action"] == "Attack:North"

        red_action = next(a for a in turn2_actions if a.player_id == "Red")
        assert red_action.action["action"] == "Attack:South"

    def test_wait_action_format(self, parser, short_game_path):
        """Null actions are formatted as 'wait'."""
        trace = parser.parse_file(short_game_path)

        # Turn 3: only unit 101 remains with null action
        turn3_actions = trace.turns[3].actions
        assert len(turn3_actions) == 1
        assert turn3_actions[0].action["action"] == "wait"

    def test_get_player_actions_by_team(self, parser, short_game_path):
        """get_player_actions works with team names."""
        trace = parser.parse_file(short_game_path)

        blue_actions = trace.get_player_actions("Blue")
        red_actions = trace.get_player_actions("Red")

        assert len(blue_actions) > 0
        assert len(red_actions) > 0

        # All blue actions should be from Blue team
        for action in blue_actions:
            assert action.player_id == "Blue"

    def test_get_player_actions_by_name(self, parser_with_names, short_game_path):
        """get_player_actions works with player names."""
        trace = parser_with_names.parse_file(short_game_path)

        player_a_actions = trace.get_player_actions("player_a")
        player_b_actions = trace.get_player_actions("player_b")

        assert len(player_a_actions) > 0
        assert len(player_b_actions) > 0

    def test_player_states_have_team_view(self, parser_with_names, short_game_path):
        """Each turn has player-specific states with team perspective."""
        trace = parser_with_names.parse_file(short_game_path)

        turn0 = trace.turns[0]

        # Both players should have states
        assert "player_a" in turn0.player_states
        assert "player_b" in turn0.player_states

        # Player A (Blue) state should have Blue as "my_units"
        player_a_state = turn0.player_states["player_a"]
        assert player_a_state["team"] == "Blue"
        assert len(player_a_state["my_units"]) == 1
        assert player_a_state["my_units"][0]["team"] == "Blue"

    def test_unit_dies_mid_game(self, parser, short_game_path):
        """Parser handles units disappearing during game."""
        trace = parser.parse_file(short_game_path)

        # Turn 0: 2 units (1 blue, 1 red)
        # Turn 3: 1 unit (blue died)
        turn0_state = trace.turns[0].state
        turn3_state = trace.turns[3].state

        # Count units in each turn
        turn0_units = [
            u for u in turn0_state["objs"].values() if u.get("obj_type") == "Unit"
        ]
        turn3_units = [
            u for u in turn3_state["objs"].values() if u.get("obj_type") == "Unit"
        ]

        assert len(turn0_units) == 2
        assert len(turn3_units) == 1


class TestRobotRumbleTraceParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content_raises_error(self, parser):
        """Parser raises error on empty content."""
        with pytest.raises(Exception):
            parser.parse_content("{}")

    def test_parse_content_directly(self, parser, short_game_path):
        """Parser can parse JSON content string directly."""
        with open(short_game_path) as f:
            content = f.read()

        trace = parser.parse_content(content)
        assert trace.game_type == "RobotRumble"

    def test_valid_actions_list(self, parser, short_game_path):
        """Actions include list of valid actions."""
        trace = parser.parse_file(short_game_path)

        action = trace.turns[0].actions[0]
        assert action.valid_actions is not None
        assert "wait" in action.valid_actions
        assert "Move:North" in action.valid_actions
        assert "Attack:South" in action.valid_actions


class TestRobotRumbleActionsDistance:
    """Tests for actions_distance function."""

    def test_identical_actions_zero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a = {"type": "Move", "direction": "North"}
        assert actions_distance(a, a) == 0.0

    def test_same_type_different_direction_half_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = {"type": "Move", "direction": "North"}
        a2 = {"type": "Move", "direction": "South"}
        assert actions_distance(a1, a2) == 0.5  # right behavior, wrong direction

    def test_different_types_nonzero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = {"type": "Move", "direction": "North"}
        a2 = {"type": "Attack", "direction": "North"}
        assert actions_distance(a1, a2) == 1.0

    def test_none_none_zero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        assert actions_distance(None, None) == 0.0

    def test_none_vs_action_nonzero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a = {"type": "Move", "direction": "North"}
        assert actions_distance(None, a) == 1.0

    def test_ok_wrapped_format(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = {"Ok": {"type": "Move", "direction": "East"}}
        a2 = {"type": "Move", "direction": "East"}
        assert actions_distance(a1, a2) == 0.0

    # --- Multi-unit list distance tests ---

    def test_identical_lists_zero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a = [{"unit_id": "1", "action": {"type": "Move", "direction": "North"}}]
        assert actions_distance(a, a) == 0.0

    def test_different_lists_nonzero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = [{"unit_id": "1", "action": {"type": "Move", "direction": "North"}}]
        a2 = [{"unit_id": "1", "action": {"type": "Move", "direction": "South"}}]
        assert actions_distance(a1, a2) == 0.5

    def test_different_type_lists_full_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = [{"unit_id": "1", "action": {"type": "Move", "direction": "North"}}]
        a2 = [{"unit_id": "1", "action": {"type": "Attack", "direction": "North"}}]
        assert actions_distance(a1, a2) == 1.0

    def test_missing_unit_penalty(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = [
            {"unit_id": "1", "action": {"type": "Move", "direction": "North"}},
            {"unit_id": "2", "action": {"type": "Move", "direction": "East"}},
        ]
        a2 = [{"unit_id": "1", "action": {"type": "Move", "direction": "North"}}]
        # unit 1 matches (0.0), unit 2 missing in a2 (1.0) → avg = 0.5
        assert actions_distance(a1, a2) == 0.5

    def test_multi_unit_average(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        a1 = [
            {"unit_id": "1", "action": {"type": "Move", "direction": "North"}},
            {"unit_id": "2", "action": {"type": "Attack", "direction": "East"}},
        ]
        a2 = [
            {"unit_id": "1", "action": {"type": "Move", "direction": "North"}},  # 0.0
            {"unit_id": "2", "action": {"type": "Attack", "direction": "West"}},  # 0.5
        ]
        assert actions_distance(a1, a2) == 0.25

    def test_empty_lists_zero_distance(self):
        from revenge_bench.traces.parsers.robotrumble import actions_distance

        assert actions_distance([], []) == 0.0


class TestRobotRumbleExtractStateActionPairs:
    """Tests for extract_state_action_pairs function."""

    def test_extracts_pairs_for_blue(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Blue")
        assert len(pairs) > 0

    def test_extracts_pairs_for_red(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Red")
        assert len(pairs) > 0

    def test_state_has_team_perspective(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Blue")
        state, _ = pairs[0]
        assert state["team"] == "Blue"
        assert "my_units" in state
        assert "enemy_units" in state
        assert all(u["team"] == "Blue" for u in state["my_units"])
        assert all(u["team"] == "Red" for u in state["enemy_units"])

    def test_actions_are_sorted_by_unit_id(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Blue")
        for _, actions in pairs:
            unit_ids = [a["unit_id"] for a in actions]
            assert unit_ids == sorted(unit_ids)

    def test_actions_are_normalized(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Blue")
        # Blue unit 100 moves East on turn 1
        _, actions = pairs[0]
        assert len(actions) == 1
        assert actions[0]["unit_id"] == "100"
        assert actions[0]["action"] == {"type": "Move", "direction": "East"}

    def test_red_first_action(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Red")
        _, actions = pairs[0]
        assert len(actions) == 1
        assert actions[0]["unit_id"] == "101"
        assert actions[0]["action"] == {"type": "Move", "direction": "West"}

    def test_returns_empty_for_invalid_team(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "InvalidTeam")
        assert pairs == []

    def test_blue_and_red_turn_counts(self, short_game_path):
        """Blue unit dies mid-game; last turn has all-None actions (filtered).

        Blue unit 100 dies after turn 3. Turn 4 has no Blue units and
        Red's actions are all None (game over). The None filter makes
        both teams end up with the same number of extracted pairs.
        """
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        blue_pairs = extract_state_action_pairs(short_game_path, "Blue")
        red_pairs = extract_state_action_pairs(short_game_path, "Red")
        assert len(blue_pairs) == 3
        assert len(red_pairs) == 3

    def test_state_includes_turn_number(self, short_game_path):
        from revenge_bench.traces.parsers.robotrumble import extract_state_action_pairs

        pairs = extract_state_action_pairs(short_game_path, "Blue")
        turns = [state["turn"] for state, _ in pairs]
        # Should be consecutive turns starting from 1
        assert turns[0] == 1


class TestTraceCollectorIntegration:
    """Tests for integration with TraceCollector."""

    def test_collector_uses_parser(self, fixtures_dir):
        """TraceCollector can use RobotRumble parser via collect_from_round."""
        from revenge_bench.traces.collector import TraceCollector

        collector = TraceCollector(game_type="RobotRumble")
        # collect_from_round expects sim_*.json files in directory
        traces = collector.collect_from_round(
            log_dir=fixtures_dir, source={"test": True}
        )

        # We have short_game.json and draw_game.json, but collect_from_round
        # looks for sim_*.json pattern, so this might be empty
        # Just verify it doesn't crash
        assert isinstance(traces, list)
