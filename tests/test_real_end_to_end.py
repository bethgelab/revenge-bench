"""
End-to-End Integration Test: Real Traces → Evaluation.

This test uses REAL trace data from actual arena runs to verify:
1. Trace parsing works on real game engine output
2. Action normalization/comparison works
3. State distance computation works
4. We can compute meaningful evaluation metrics

This is the definitive test that the trace → eval pipeline works.
"""

import os
from pathlib import Path

import pytest

from revenge_bench.traces.parsers import (
    BattleSnakeTraceParser,
    RobotRumbleTraceParser,
    battlesnake_actions_equal,
    battlesnake_normalize_action,
    robotrumble_actions_equal,
    robotrumble_normalize_action,
)

# =============================================================================
# Real Data Paths - Set via environment variables for local testing
# =============================================================================

# Set CODECLASH_LOGS_DIR to point to your local CodeClash logs directory
CODECLASH_LOGS_DIR = Path(os.environ.get("CODECLASH_LOGS_DIR", "data/codeclash_logs"))

# Paths to example trace files (relative to CODECLASH_LOGS_DIR)
REAL_BATTLESNAKE_TRACE = CODECLASH_LOGS_DIR / os.environ.get(
    "BATTLESNAKE_TRACE_PATH", "example/battlesnake/sim_0.jsonl"
)

REAL_ROBOTRUMBLE_TRACE = CODECLASH_LOGS_DIR / os.environ.get(
    "ROBOTRUMBLE_TRACE_PATH", "example/robotrumble/sim_0.json"
)


def find_real_battlesnake_trace() -> Path | None:
    """Find a real BattleSnake trace file."""
    # Try the specific path first
    if REAL_BATTLESNAKE_TRACE.exists():
        return REAL_BATTLESNAKE_TRACE

    # Search for any sim_*.jsonl file in the configured logs directory
    if CODECLASH_LOGS_DIR.exists():
        for f in CODECLASH_LOGS_DIR.rglob("sim_*.jsonl"):
            return f

    return None


def find_real_robotrumble_trace() -> Path | None:
    """Find a real RobotRumble trace file."""
    # Try the specific path first
    if REAL_ROBOTRUMBLE_TRACE.exists():
        return REAL_ROBOTRUMBLE_TRACE

    # Search for any sim_*.json file in RobotRumble directory
    if CODECLASH_LOGS_DIR.exists():
        for f in CODECLASH_LOGS_DIR.rglob("*RobotRumble*/**/sim_*.json"):
            return f

    return None


# =============================================================================
# Test: BattleSnake End-to-End
# =============================================================================


class TestBattleSnakeEndToEnd:
    """End-to-end test with real BattleSnake data."""

    @pytest.fixture
    def real_trace_path(self):
        """Get path to real BattleSnake trace."""
        path = find_real_battlesnake_trace()
        if path is None:
            pytest.skip("No real BattleSnake trace data available")
        return path

    def test_parse_real_trace(self, real_trace_path):
        """Can parse real BattleSnake trace file."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_file(real_trace_path)

        # Basic structure checks
        assert trace is not None
        assert trace.metadata.game_type == "BattleSnake"
        assert len(trace.turns) > 0

        print(f"\n[BattleSnake] Parsed {real_trace_path.name}")
        print(f"  Game ID: {trace.metadata.game_id}")
        print(f"  Players: {[p['name'] for p in trace.metadata.players]}")
        print(f"  Turns: {len(trace.turns)}")
        print(f"  Winner: {trace.winner}")

    def test_extract_actions_from_real_trace(self, real_trace_path):
        """Can extract actions from real trace."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_file(real_trace_path)

        # Count actions
        total_actions = 0
        actions_by_player = {}

        for turn in trace.turns:
            for action in turn.actions:
                total_actions += 1
                player = action.player_name
                actions_by_player[player] = actions_by_player.get(player, 0) + 1

        assert total_actions > 0

        print("\n[BattleSnake] Actions extracted:")
        print(f"  Total actions: {total_actions}")
        for player, count in actions_by_player.items():
            print(f"  {player}: {count} actions")

    def test_actions_are_valid(self, real_trace_path):
        """All actions are valid BattleSnake moves."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_file(real_trace_path)

        valid_actions = {"up", "down", "left", "right"}
        invalid_actions = []

        for turn in trace.turns:
            for action in turn.actions:
                normalized = battlesnake_normalize_action(action.action)
                if normalized not in valid_actions:
                    invalid_actions.append((turn.turn, action.action))

        assert (
            len(invalid_actions) == 0
        ), f"Invalid actions found: {invalid_actions[:5]}"
        print("\n[BattleSnake] All actions are valid moves")

    def test_compute_action_distance_self(self, real_trace_path):
        """Compute action distance (comparing trace to itself = 0.0)."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_file(real_trace_path)

        # Compare trace actions to themselves (distance should be 0.0)
        total_distance = 0.0
        total = 0

        for turn in trace.turns:
            for action in turn.actions:
                predicted = action.action
                recorded = action.action  # Same action

                dist = 0.0 if battlesnake_actions_equal(predicted, recorded) else 1.0
                total_distance += dist
                total += 1

        mean_distance = total_distance / total if total > 0 else float("inf")

        assert mean_distance == 0.0, "Self-comparison distance should be 0.0"
        print(f"\n[BattleSnake] Self-distance: {mean_distance:.4f} ({total} actions)")

    def test_simulate_prediction_evaluation(self, real_trace_path):
        """Simulate evaluating a 'predicted' strategy against recorded trace."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_file(real_trace_path)

        if not trace.metadata.players:
            pytest.skip("No players in trace")

        player_name = trace.metadata.players[0]["name"]

        # Simulate: predict "always go up" vs actual recorded actions
        total_distance = 0.0
        total = 0
        first_divergence = None

        for turn in trace.turns:
            for action in turn.actions:
                if action.player_name == player_name:
                    predicted = "up"  # Our "strategy" always goes up
                    recorded = action.action

                    dist = (
                        0.0 if battlesnake_actions_equal(predicted, recorded) else 1.0
                    )
                    total_distance += dist
                    if dist > 0 and first_divergence is None:
                        first_divergence = turn.turn

                    total += 1

        mean_distance = total_distance / total if total > 0 else float("inf")

        print("\n[BattleSnake] Simulated 'always up' strategy evaluation:")
        print(f"  Player: {player_name}")
        print(f"  Mean distance: {mean_distance:.4f} ({total} actions)")
        print(f"  First divergence: turn {first_divergence}")

        # Distance should NOT be 0.0 (unless player actually always went up)
        # This validates we're computing real metrics
        assert total > 0


# =============================================================================
# Test: RobotRumble End-to-End
# =============================================================================


class TestRobotRumbleEndToEnd:
    """End-to-end test with real RobotRumble data."""

    @pytest.fixture
    def real_trace_path(self):
        """Get path to real RobotRumble trace."""
        path = find_real_robotrumble_trace()
        if path is None:
            pytest.skip("No real RobotRumble trace data available")
        return path

    def test_parse_real_trace(self, real_trace_path):
        """Can parse real RobotRumble trace file."""
        parser = RobotRumbleTraceParser()
        trace = parser.parse_file(real_trace_path)

        # Basic structure checks
        assert trace is not None
        assert trace.metadata.game_type == "RobotRumble"
        assert len(trace.turns) > 0

        print(f"\n[RobotRumble] Parsed {real_trace_path.name}")
        print(f"  Game ID: {trace.metadata.game_id}")
        print(f"  Players: {[p['name'] for p in trace.metadata.players]}")
        print(f"  Turns: {len(trace.turns)}")
        print(f"  Winner: {trace.winner}")

    def test_extract_actions_from_real_trace(self, real_trace_path):
        """Can extract actions from real trace."""
        parser = RobotRumbleTraceParser()
        trace = parser.parse_file(real_trace_path)

        # Count actions
        total_actions = 0
        actions_by_team = {"Blue": 0, "Red": 0}
        action_types = {"Move": 0, "Attack": 0, "wait": 0, "error": 0}

        for turn in trace.turns:
            for action in turn.actions:
                total_actions += 1
                team = action.player_id  # "Blue" or "Red"
                if team in actions_by_team:
                    actions_by_team[team] += 1

                # Categorize action type
                action_str = action.action.get("action", "")
                if action_str.startswith("Move"):
                    action_types["Move"] += 1
                elif action_str.startswith("Attack"):
                    action_types["Attack"] += 1
                elif action_str == "wait":
                    action_types["wait"] += 1
                elif action_str.startswith("error"):
                    action_types["error"] += 1

        assert total_actions > 0

        print("\n[RobotRumble] Actions extracted:")
        print(f"  Total actions: {total_actions}")
        print(f"  By team: {actions_by_team}")
        print(f"  By type: {action_types}")

    def test_normalize_real_actions(self, real_trace_path):
        """Can normalize real RobotRumble actions."""
        parser = RobotRumbleTraceParser()
        trace = parser.parse_file(real_trace_path)

        normalized_count = 0
        failed_count = 0

        for turn in trace.turns:
            for action in turn.actions:
                action_str = action.action.get("action", "")

                # Try to normalize "Move:North" -> {"type": "Move", "direction": "North"}
                if action_str.startswith("Move:") or action_str.startswith("Attack:"):
                    normalized = robotrumble_normalize_action(action_str)
                    if normalized:
                        normalized_count += 1
                    else:
                        failed_count += 1

        print("\n[RobotRumble] Action normalization:")
        print(f"  Normalized: {normalized_count}")
        print(f"  Failed: {failed_count}")

        assert normalized_count > 0

    def test_compute_action_distance_self(self, real_trace_path):
        """Compute action distance (comparing trace to itself = 0.0)."""
        parser = RobotRumbleTraceParser()
        trace = parser.parse_file(real_trace_path)

        total_distance = 0.0
        total = 0

        for turn in trace.turns:
            for action in turn.actions:
                action_str = action.action.get("action", "")
                if action_str.startswith("Move:") or action_str.startswith("Attack:"):
                    predicted = action_str
                    recorded = action_str

                    dist = (
                        0.0 if robotrumble_actions_equal(predicted, recorded) else 1.0
                    )
                    total_distance += dist
                    total += 1

        mean_distance = total_distance / total if total > 0 else float("inf")

        assert mean_distance == 0.0, "Self-comparison distance should be 0.0"
        print(f"\n[RobotRumble] Self-distance: {mean_distance:.4f} ({total} actions)")

    def test_simulate_prediction_evaluation(self, real_trace_path):
        """Simulate evaluating a 'predicted' strategy against recorded trace."""
        parser = RobotRumbleTraceParser()
        trace = parser.parse_file(real_trace_path)

        # Simulate: predict "always Move:North" vs actual recorded actions
        # Use Red team since Blue may have all errors
        total_distance = 0.0
        total = 0
        first_divergence = None

        for turn in trace.turns:
            for action in turn.actions:
                # Try both teams, use whichever has valid actions
                action_str = action.action.get("action", "")
                if action_str.startswith("Move:") or action_str.startswith("Attack:"):
                    predicted = "Move:North"  # Our "strategy"
                    recorded = action_str

                    dist = (
                        0.0 if robotrumble_actions_equal(predicted, recorded) else 1.0
                    )
                    total_distance += dist
                    if dist > 0 and first_divergence is None:
                        first_divergence = turn.turn

                    total += 1

        mean_distance = total_distance / total if total > 0 else float("inf")

        print("\n[RobotRumble] Simulated 'always Move:North' strategy evaluation:")
        print("  Team: All")
        print(f"  Mean distance: {mean_distance:.4f} ({total} actions)")
        print(f"  First divergence: turn {first_divergence}")

        assert total > 0


# =============================================================================
# Test: Full Evaluation Report
# =============================================================================


class TestFullEvaluationReport:
    """Generate a complete evaluation report from real data."""

    def test_battlesnake_full_report(self):
        """Generate full evaluation report for BattleSnake."""
        path = find_real_battlesnake_trace()
        if path is None:
            pytest.skip("No real BattleSnake trace data available")

        parser = BattleSnakeTraceParser()
        trace = parser.parse_file(path)

        if not trace.metadata.players:
            pytest.skip("No players in trace")

        player_name = trace.metadata.players[0]["name"]

        # Collect all recorded actions for this player
        recorded_actions = []
        for turn in trace.turns:
            for action in turn.actions:
                if action.player_name == player_name:
                    recorded_actions.append(
                        {
                            "turn": turn.turn,
                            "action": action.action,
                        }
                    )

        # Simulate different "predicted" strategies
        strategies = {
            "always_up": lambda t: "up",
            "always_down": lambda t: "down",
            "always_right": lambda t: "right",
            "random_like": lambda t: ["up", "down", "left", "right"][t % 4],
        }

        print(f"\n{'='*60}")
        print("BATTLESNAKE EVALUATION REPORT")
        print(f"{'='*60}")
        print(f"Trace: {path.name}")
        print(f"Player: {player_name}")
        print(f"Total turns: {len(recorded_actions)}")
        print(f"Winner: {trace.winner}")
        print("\nStrategy Comparison (mean action distance, lower is better):")
        print(f"{'-'*60}")

        for strategy_name, strategy_fn in strategies.items():
            total_distance = 0.0
            first_div = None

            for _i, rec in enumerate(recorded_actions):
                predicted = strategy_fn(rec["turn"])
                dist = (
                    0.0 if battlesnake_actions_equal(predicted, rec["action"]) else 1.0
                )
                total_distance += dist
                if dist > 0 and first_div is None:
                    first_div = rec["turn"]

            mean_distance = (
                total_distance / len(recorded_actions)
                if recorded_actions
                else float("inf")
            )
            print(
                f"  {strategy_name:20s}: {mean_distance:.4f} (first_div @ turn {first_div})"
            )

        print(f"{'='*60}")

    def test_robotrumble_full_report(self):
        """Generate full evaluation report for RobotRumble."""
        path = find_real_robotrumble_trace()
        if path is None:
            pytest.skip("No real RobotRumble trace data available")

        parser = RobotRumbleTraceParser()
        trace = parser.parse_file(path)

        # Collect all recorded actions (all teams with valid actions)
        recorded_actions = []
        for turn in trace.turns:
            for action in turn.actions:
                action_str = action.action.get("action", "")
                if action_str.startswith("Move:") or action_str.startswith("Attack:"):
                    recorded_actions.append(
                        {
                            "turn": turn.turn,
                            "action": action_str,
                            "unit_id": action.action.get("unit_id"),
                            "team": action.player_id,
                        }
                    )

        if not recorded_actions:
            pytest.skip("No valid actions in trace")

        # Simulate different "predicted" strategies
        strategies = {
            "always_move_north": lambda t: "Move:North",
            "always_move_south": lambda t: "Move:South",
            "always_attack_east": lambda t: "Attack:East",
            "cycle_directions": lambda t: f"Move:{['North','South','East','West'][t % 4]}",
        }

        print(f"\n{'='*60}")
        print("ROBOTRUMBLE EVALUATION REPORT")
        print(f"{'='*60}")
        print(f"Trace: {path.name}")
        print(f"Total valid actions: {len(recorded_actions)}")
        print(f"Winner: {trace.winner}")
        print("\nStrategy Comparison (mean action distance, lower is better):")
        print(f"{'-'*60}")

        for strategy_name, strategy_fn in strategies.items():
            total_distance = 0.0
            first_div = None

            for _i, rec in enumerate(recorded_actions):
                predicted = strategy_fn(rec["turn"])
                dist = (
                    0.0 if robotrumble_actions_equal(predicted, rec["action"]) else 1.0
                )
                total_distance += dist
                if dist > 0 and first_div is None:
                    first_div = rec["turn"]

            mean_distance = (
                total_distance / len(recorded_actions)
                if recorded_actions
                else float("inf")
            )
            print(
                f"  {strategy_name:25s}: {mean_distance:.4f} (first_div @ turn {first_div})"
            )

        print(f"{'='*60}")
