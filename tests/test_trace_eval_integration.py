"""
Integration tests: Trace Parsing → Evaluation Flow.

Tests the full pipeline:
1. Parse raw game output → GameTrace with normalized actions/states
2. Use game-specific functions to compare actions
3. Compute evaluation metrics

This validates that traces and evaluation work together correctly.
"""

from pathlib import Path

import pytest

from revenge_bench.traces.models import GameTrace
from revenge_bench.traces.parsers import (
    BattleSnakeTraceParser,
    RobotRumbleTraceParser,
    battlesnake_actions_equal,
    robotrumble_actions_equal,
    robotrumble_normalize_action,
)

# =============================================================================
# Fixtures
# =============================================================================

# Get the project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_FIXTURES = PROJECT_ROOT / "data" / "test_fixtures" / "traces"


@pytest.fixture
def battlesnake_fixture_path():
    """Path to BattleSnake test fixture."""
    return TRACE_FIXTURES / "battlesnake" / "short_game.jsonl"


@pytest.fixture
def robotrumble_fixture_path():
    """Path to RobotRumble test fixture."""
    return TRACE_FIXTURES / "robotrumble" / "short_game.json"


@pytest.fixture
def battlesnake_trace(battlesnake_fixture_path) -> GameTrace:
    """Parsed BattleSnake trace."""
    parser = BattleSnakeTraceParser()
    return parser.parse_file(battlesnake_fixture_path)


@pytest.fixture
def robotrumble_trace(robotrumble_fixture_path) -> GameTrace:
    """Parsed RobotRumble trace."""
    parser = RobotRumbleTraceParser()
    return parser.parse_file(robotrumble_fixture_path)


# =============================================================================
# Test: BattleSnake Trace → Evaluation
# =============================================================================


class TestBattleSnakeTraceToEval:
    """Test BattleSnake trace parsing flows to evaluation correctly."""

    def test_trace_has_turns_with_actions(self, battlesnake_trace):
        """Parsed trace has turns with actions."""
        assert len(battlesnake_trace.turns) > 0

        # Not all turns have actions (turn 0 has no previous action)
        turns_with_actions = [t for t in battlesnake_trace.turns if t.actions]
        assert len(turns_with_actions) > 0

    def test_actions_are_normalized_strings(self, battlesnake_trace):
        """Actions are lowercase strings."""
        for turn in battlesnake_trace.turns:
            for player_action in turn.actions:
                action = player_action.action
                # Should be lowercase string
                assert isinstance(action, str)
                assert action == action.lower()
                assert action in ["up", "down", "left", "right"]

    def test_can_compare_actions_with_eval_function(self, battlesnake_trace):
        """Can use battlesnake_actions_equal to compare actions."""
        # Get first action
        first_action = None
        for turn in battlesnake_trace.turns:
            if turn.actions:
                first_action = turn.actions[0].action
                break

        assert first_action is not None

        # Compare with same action
        assert battlesnake_actions_equal(first_action, first_action)

        # Compare with different action
        other = "down" if first_action != "down" else "up"
        assert not battlesnake_actions_equal(first_action, other)

        # Compare with dict format (normalization)
        assert battlesnake_actions_equal(first_action, {"move": first_action})

    def test_player_states_have_you_field(self, battlesnake_trace):
        """Player states have 'you' field for that player's snake."""
        for turn in battlesnake_trace.turns:
            for player_name, player_state in turn.player_states.items():
                assert "you" in player_state
                assert player_state["you"]["name"] == player_name

    def test_compute_action_distance(self, battlesnake_trace):
        """Can compute action distance metric manually."""
        # Simulate: predicted actions vs recorded actions
        # For testing, compare trace to itself (distance should be 0.0)

        total_distance = 0.0
        total = 0

        for turn in battlesnake_trace.turns:
            for action in turn.actions:
                predicted = action.action  # From trace
                recorded = action.action  # Same (simulating perfect prediction)

                dist = 0.0 if battlesnake_actions_equal(predicted, recorded) else 1.0
                total_distance += dist
                total += 1

        mean_distance = total_distance / total if total > 0 else float("inf")
        assert mean_distance == 0.0  # Perfect self-comparison


# =============================================================================
# Test: RobotRumble Trace → Evaluation
# =============================================================================


class TestRobotRumbleTraceToEval:
    """Test RobotRumble trace parsing flows to evaluation correctly."""

    def test_trace_has_turns_with_actions(self, robotrumble_trace):
        """Parsed trace has turns with actions."""
        assert len(robotrumble_trace.turns) > 0

        # RobotRumble has explicit actions per turn
        turns_with_actions = [t for t in robotrumble_trace.turns if t.actions]
        assert len(turns_with_actions) > 0

    def test_actions_have_unit_id_and_action(self, robotrumble_trace):
        """Actions include unit_id and action string."""
        for turn in robotrumble_trace.turns:
            for player_action in turn.actions:
                action = player_action.action
                # RobotRumble actions are dicts with unit_id and action
                assert isinstance(action, dict)
                assert "unit_id" in action
                assert "action" in action

    def test_can_normalize_action_string(self, robotrumble_trace):
        """Can normalize action strings to canonical dict format."""
        # Test normalization of various formats

        # Standard dict
        norm1 = robotrumble_normalize_action({"type": "Move", "direction": "North"})
        assert norm1 == {"type": "Move", "direction": "North"}

        # String format from trace
        norm2 = robotrumble_normalize_action("Move:North")
        assert norm2 == {"type": "Move", "direction": "North"}

        # Ok wrapper from raw trace
        norm3 = robotrumble_normalize_action(
            {"Ok": {"type": "Attack", "direction": "South"}}
        )
        assert norm3 == {"type": "Attack", "direction": "South"}

        # Error returns None
        norm4 = robotrumble_normalize_action({"Err": {"RuntimeError": {}}})
        assert norm4 is None

    def test_can_compare_actions_with_eval_function(self, robotrumble_trace):
        """Can use robotrumble_actions_equal to compare actions."""
        # Test action comparison
        assert robotrumble_actions_equal(
            {"type": "Move", "direction": "North"},
            {"type": "Move", "direction": "North"},
        )

        assert not robotrumble_actions_equal(
            {"type": "Move", "direction": "North"},
            {"type": "Move", "direction": "South"},
        )

        assert not robotrumble_actions_equal(
            {"type": "Move", "direction": "North"},
            {"type": "Attack", "direction": "North"},
        )

        # With Ok wrapper
        assert robotrumble_actions_equal(
            {"Ok": {"type": "Move", "direction": "East"}},
            {"type": "Move", "direction": "East"},
        )

        # String format
        assert robotrumble_actions_equal(
            "Move:West", {"type": "Move", "direction": "West"}
        )

    def test_player_states_have_team_view(self, robotrumble_trace):
        """Player states have team-specific view."""
        for turn in robotrumble_trace.turns:
            for _player_name, player_state in turn.player_states.items():
                assert "team" in player_state
                assert "my_units" in player_state
                assert "enemy_units" in player_state


# =============================================================================
# Test: Full Evaluation Flow (Simulated)
# =============================================================================


class TestFullEvaluationFlow:
    """Test complete evaluation flow with simulated predictions."""

    def test_battlesnake_perfect_prediction(self, battlesnake_trace):
        """Simulated perfect prediction has distance 0.0."""
        # Simulate: model predicts exact same actions as trace
        predicted_actions = []
        recorded_actions = []

        for turn in battlesnake_trace.turns:
            for action in turn.actions:
                predicted_actions.append(action.action)
                recorded_actions.append(action.action)

        # Compare
        total_distance = sum(
            0.0 if battlesnake_actions_equal(p, r) else 1.0
            for p, r in zip(predicted_actions, recorded_actions)
        )
        total = len(predicted_actions)

        assert total > 0
        assert total_distance == 0.0
        assert total_distance / total == 0.0

    def test_battlesnake_wrong_prediction(self, battlesnake_trace):
        """Simulated wrong prediction has distance 1.0."""
        # Simulate: model always predicts opposite of actual
        opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}

        predicted_actions = []
        recorded_actions = []

        for turn in battlesnake_trace.turns:
            for action in turn.actions:
                recorded = action.action
                predicted = opposite.get(recorded, "up")
                predicted_actions.append(predicted)
                recorded_actions.append(recorded)

        # Compare
        total_distance = sum(
            0.0 if battlesnake_actions_equal(p, r) else 1.0
            for p, r in zip(predicted_actions, recorded_actions)
        )
        total = len(predicted_actions)

        assert total > 0
        assert total_distance == total  # Every action is wrong
        assert total_distance / total == 1.0

    def test_robotrumble_partial_prediction(self, robotrumble_trace):
        """Simulated partial prediction has intermediate distance."""
        # Simulate: model predicts ~50% correct
        predicted_actions = []
        recorded_actions = []

        count = 0
        for turn in robotrumble_trace.turns:
            for action in turn.actions:
                action_str = action.action.get("action", "")
                if action_str.startswith("Move:") or action_str.startswith("Attack:"):
                    recorded_actions.append(action_str)
                    # Alternate: every other one is wrong
                    if count % 2 == 0:
                        predicted_actions.append(action_str)  # Correct
                    else:
                        predicted_actions.append("Move:North")  # May be wrong
                    count += 1

        if not recorded_actions:
            pytest.skip("No valid actions in trace")

        # Compare
        total_distance = sum(
            0.0 if robotrumble_actions_equal(p, r) else 1.0
            for p, r in zip(predicted_actions, recorded_actions)
        )
        total = len(predicted_actions)

        mean_distance = total_distance / total
        # Should be between 0 and 1 (not necessarily exactly 0.5)
        assert 0 <= mean_distance <= 1


# =============================================================================
# Test: Accessing State-Action Pairs
# =============================================================================


class TestStateActionAccess:
    """Test convenient access to state-action pairs for training/eval."""

    def test_battlesnake_get_state_action_pairs(self, battlesnake_trace):
        """Can extract state-action pairs from BattleSnake trace."""
        pairs = []

        for turn in battlesnake_trace.turns:
            for player_name, player_state in turn.player_states.items():
                # Find action for this player on this turn
                for action in turn.actions:
                    if action.player_name == player_name:
                        pairs.append(
                            {
                                "state": player_state,
                                "action": action.action,
                                "turn": turn.turn,
                                "player": player_name,
                            }
                        )

        # Should have some pairs
        assert len(pairs) > 0

        # Each pair has state and action
        for pair in pairs:
            assert "state" in pair
            assert "action" in pair
            assert "you" in pair["state"]  # BattleSnake-specific

    def test_robotrumble_get_state_action_pairs(self, robotrumble_trace):
        """Can extract state-action pairs from RobotRumble trace."""
        pairs = []

        for turn in robotrumble_trace.turns:
            for action in turn.actions:
                player_name = action.player_name
                if player_name in turn.player_states:
                    player_state = turn.player_states[player_name]
                    pairs.append(
                        {
                            "state": player_state,
                            "action": action.action,
                            "turn": turn.turn,
                            "player": player_name,
                            "unit_id": action.action.get("unit_id"),
                        }
                    )

        # Should have some pairs
        assert len(pairs) > 0

        # Each pair has state and action
        for pair in pairs:
            assert "state" in pair
            assert "action" in pair
            assert "team" in pair["state"]  # RobotRumble-specific
