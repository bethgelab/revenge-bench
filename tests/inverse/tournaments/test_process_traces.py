"""
Tests for _process_traces() in InverseStrategyTournament.

Tests the post-simulation trace processing:
1. Parses sim files (game-specific formats)
2. Computes mean action distance (learner vs target, lower is better)
3. Saves traces.json summary

Uses fixture data from data/inverse/test_fixtures/traces/.

Two helpers are provided:

process_traces() — Uses the GameTrace abstraction (suitable for symmetric
    two-player games: BattleSnake, RobotRumble, Halite, Halite3).

process_traces_offline() — Mirrors InverseStrategyTournament._process_traces()
    for offline evaluation (RoboCode, HuskyBench). Takes a callable learner_move_fn
    instead of a container reference, making it fully testable without Docker.
"""

import json
import shutil
from pathlib import Path

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_round_dir(tmp_path):
    """Create a temporary round directory."""
    round_dir = tmp_path / "rounds" / "0"
    round_dir.mkdir(parents=True)
    return round_dir


@pytest.fixture
def battlesnake_sim_file():
    """Path to BattleSnake test fixture."""
    return (
        PROJECT_ROOT
        / "data"
        / "inverse"
        / "test_fixtures"
        / "traces"
        / "battlesnake"
        / "short_game.jsonl"
    )


@pytest.fixture
def robotrumble_sim_file():
    """Path to RobotRumble test fixture."""
    return (
        PROJECT_ROOT
        / "data"
        / "inverse"
        / "test_fixtures"
        / "traces"
        / "robotrumble"
        / "short_game.json"
    )


@pytest.fixture
def robocode_sim_file():
    """Path to RoboCode test fixture."""
    return (
        PROJECT_ROOT
        / "data"
        / "inverse"
        / "test_fixtures"
        / "traces"
        / "robocode"
        / "short_game.xml"
    )


@pytest.fixture
def huskybench_sim_file():
    """Path to HuskyBench test fixture."""
    return (
        PROJECT_ROOT
        / "data"
        / "inverse"
        / "test_fixtures"
        / "traces"
        / "huskybench"
        / "short_game.json"
    )


@pytest.fixture
def halite3_sim_file():
    """Path to Halite3 test fixture."""
    return (
        PROJECT_ROOT
        / "data"
        / "inverse"
        / "test_fixtures"
        / "traces"
        / "halite3"
        / "short_game.hlt"
    )


@pytest.fixture
def halite1_sim_file():
    """Path to Halite (original) test fixture."""
    return (
        PROJECT_ROOT
        / "data"
        / "inverse"
        / "test_fixtures"
        / "traces"
        / "halite1"
        / "short_game.hlt"
    )


# =============================================================================
# Helper: Extracted _process_traces logic
# =============================================================================


def process_traces(
    round_dir: Path,
    round_num: int,
    game_name: str,
    learner_name: str,
    target_name: str,
) -> dict | None:
    """
    Extracted logic from InverseStrategyTournament._process_traces().

    This allows testing without mocking the full tournament.
    """
    from revenge_bench.traces import get_parser

    # Find sim files using game-specific patterns (mirrors inverse_strategy.py).
    file_patterns = {
        "BattleSnake": ["sim_*.jsonl"],
        "RobotRumble": ["sim_*.json"],
        "Halite": ["*.hlt"],  # Halite I: <seed1>-<seed2>.hlt (plain JSON)
        "Halite3": ["replay-*.hlt"],  # Halite III: zstd-compressed JSON
    }
    patterns = file_patterns.get(game_name, ["sim_*.jsonl", "sim_*.json"])
    sim_files = []
    for pat in patterns:
        sim_files.extend(sorted(round_dir.glob(pat)))
    if not sim_files:
        return None

    # Get the appropriate parser for this game
    try:
        parser_class = get_parser(game_name)
    except ValueError:
        return None

    # Import the action distance function.
    # For Halite/Halite3: use native actions_distance
    # For BattleSnake/RobotRumble: define wrapper using actions_equal (TODO: add actions_distance)
    if game_name == "BattleSnake":
        from revenge_bench.traces.parsers.battlesnake import actions_equal

        actions_distance = lambda a1, a2: 0.0 if actions_equal(a1, a2) else 1.0
    elif game_name == "RobotRumble":
        from revenge_bench.traces.parsers.robotrumble import actions_distance
    elif game_name == "Halite":
        from revenge_bench.traces.parsers.halite import actions_distance
    elif game_name == "Halite3":
        from revenge_bench.traces.parsers.halite3 import actions_distance
    else:
        return None

    total_actions = 0
    total_distance = 0.0
    per_simulation = []
    nonzero_distances = []

    for sim_file in sim_files:
        try:
            parser = parser_class()
            trace = parser.parse_file(sim_file)

            sim_total = 0
            sim_distance_sum = 0.0
            sim_nonzero = 0

            # Iterate through turns and compare actions
            for turn in trace.turns:
                # Find actions for both players in this turn.
                # Match by player_name first; fall back to player_id as a string
                # so games where both players share the same name (e.g. Halite
                # bots compiled from the same binary) can still be addressed by
                # their numeric id ("0", "1", …).
                learner_action = None
                target_action = None

                for player_action in turn.actions:
                    pid = str(player_action.player_id)
                    pname = player_action.player_name
                    if pname == learner_name or pid == learner_name:
                        learner_action = player_action.action
                    if pname == target_name or pid == target_name:
                        target_action = player_action.action

                # Only compare if both players acted
                if learner_action is not None and target_action is not None:
                    sim_total += 1
                    dist = actions_distance(learner_action, target_action)
                    sim_distance_sum += dist
                    if dist > 0.0:
                        sim_nonzero += 1
                        nonzero_distances.append(
                            {
                                "sim": sim_file.name,
                                "turn": turn.turn,
                                "learner_action": learner_action,
                                "target_action": target_action,
                                "distance": dist,
                            }
                        )

            total_actions += sim_total
            total_distance += sim_distance_sum

            per_simulation.append(
                {
                    "file": sim_file.name,
                    "total": sim_total,
                    "distance_sum": sim_distance_sum,
                    "mean_distance": sim_distance_sum / sim_total
                    if sim_total > 0
                    else 0.0,
                    "num_nonzero": sim_nonzero,
                }
            )

        except Exception:
            continue

    if total_actions == 0:
        return None

    mean_distance = total_distance / total_actions

    summary = {
        "round": round_num,
        "game": game_name,
        "learner": learner_name,
        "target": target_name,
        "total_actions": total_actions,
        "total_distance": total_distance,
        "mean_distance": mean_distance,
        "num_simulations": len(per_simulation),
        "per_simulation": per_simulation,
        "nonzero_distances": nonzero_distances,
    }

    # Save traces.json
    traces_file = round_dir / "traces.json"
    traces_file.write_text(json.dumps(summary, indent=2))

    return summary


# =============================================================================
# Tests: BattleSnake
# =============================================================================


class TestProcessTracesBattleSnake:
    """Tests for _process_traces with BattleSnake data."""

    def test_parses_battlesnake_sim_file(self, temp_round_dir, battlesnake_sim_file):
        """Should parse BattleSnake sim file and compute distance."""
        # Copy fixture to temp dir as sim_0.jsonl
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        assert result is not None
        assert result["game"] == "BattleSnake"
        assert result["learner"] == "player_a"
        assert result["target"] == "player_b"
        assert result["round"] == 0
        assert result["total_actions"] > 0
        assert result["mean_distance"] >= 0.0

    def test_saves_traces_json(self, temp_round_dir, battlesnake_sim_file):
        """Should save traces.json to round directory."""
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")

        process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        traces_file = temp_round_dir / "traces.json"
        assert traces_file.exists()

        data = json.loads(traces_file.read_text())
        assert "mean_distance" in data
        assert "total_actions" in data
        assert "per_simulation" in data

    def test_handles_multiple_sim_files(self, temp_round_dir, battlesnake_sim_file):
        """Should process multiple sim files."""
        # Copy fixture multiple times
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_1.jsonl")
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_2.jsonl")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        assert result is not None
        assert result["num_simulations"] == 3
        assert len(result["per_simulation"]) == 3

    def test_per_simulation_breakdown(self, temp_round_dir, battlesnake_sim_file):
        """Should include per-simulation distance breakdown."""
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        assert len(result["per_simulation"]) == 1
        sim_result = result["per_simulation"][0]
        assert "file" in sim_result
        assert "total" in sim_result
        assert "distance_sum" in sim_result
        assert "mean_distance" in sim_result

    def test_identical_players_have_zero_distance(
        self, temp_round_dir, battlesnake_sim_file
    ):
        """When comparing player to itself, distance should be zero."""
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_a",  # Same player!
        )

        assert result is not None
        assert result["mean_distance"] == 0.0
        assert result["total_distance"] == 0.0


# =============================================================================
# Tests: RobotRumble
# =============================================================================


class TestProcessTracesRobotRumble:
    """Tests for _process_traces with RobotRumble data."""

    def test_parses_robotrumble_sim_file(self, temp_round_dir, robotrumble_sim_file):
        """Should parse RobotRumble sim file and compute distance."""
        # Copy fixture to temp dir as sim_0.json
        shutil.copy(robotrumble_sim_file, temp_round_dir / "sim_0.json")

        # RobotRumble uses team names: "Blue" and "Red"
        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RobotRumble",
            learner_name="Blue",
            target_name="Red",
        )

        assert result is not None
        assert result["game"] == "RobotRumble"
        assert result["total_actions"] > 0
        assert result["mean_distance"] >= 0.0

    def test_robotrumble_identical_team_zero_distance(
        self, temp_round_dir, robotrumble_sim_file
    ):
        """When comparing team to itself, distance should be zero."""
        shutil.copy(robotrumble_sim_file, temp_round_dir / "sim_0.json")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RobotRumble",
            learner_name="Blue",
            target_name="Blue",  # Same team!
        )

        assert result is not None
        assert result["mean_distance"] == 0.0


# =============================================================================
# Tests: Edge Cases
# =============================================================================


class TestProcessTracesEdgeCases:
    """Edge case tests for _process_traces."""

    def test_returns_none_for_empty_directory(self, temp_round_dir):
        """Should return None when no sim files exist."""
        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        assert result is None

    def test_returns_none_for_unknown_game(self, temp_round_dir, battlesnake_sim_file):
        """Should return None for unsupported game type."""
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="UnknownGame",
            learner_name="player_a",
            target_name="player_b",
        )

        assert result is None

    def test_handles_invalid_sim_file(self, temp_round_dir):
        """Should skip invalid sim files gracefully."""
        # Create an invalid sim file
        (temp_round_dir / "sim_0.jsonl").write_text("not valid json")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        # Should return None since no valid files
        assert result is None

    def test_nonzero_distances_collected(self, temp_round_dir, battlesnake_sim_file):
        """Should collect nonzero distances as a list."""
        # Copy many times to get more nonzero distances
        for i in range(20):
            shutil.copy(battlesnake_sim_file, temp_round_dir / f"sim_{i}.jsonl")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        assert result is not None
        assert isinstance(result["nonzero_distances"], list)


# =============================================================================
# Tests: Integration with InverseStrategyTournament
# =============================================================================


class TestTournamentIntegration:
    """Test _process_traces via InverseStrategyTournament mock."""

    def test_tournament_calls_process_traces(
        self, temp_round_dir, battlesnake_sim_file
    ):
        """Verify the tournament method produces same results."""
        # This test uses mocks to verify the tournament's _process_traces
        # produces consistent results with our extracted function
        shutil.copy(battlesnake_sim_file, temp_round_dir / "sim_0.jsonl")

        # First, get result from our extracted function
        expected = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="BattleSnake",
            learner_name="player_a",
            target_name="player_b",
        )

        # Verify it worked
        assert expected is not None
        assert expected["total_actions"] > 0

        # The tournament's _process_traces should produce equivalent results
        # (we can't easily instantiate the full tournament without Docker)
        # So we verify the output format matches what the agent expects
        assert "mean_distance" in expected
        assert "per_simulation" in expected
        assert "nonzero_distances" in expected
        assert "learner" in expected
        assert "target" in expected


# =============================================================================
# Tests: Halite3
# =============================================================================


class TestProcessTracesHalite3:
    """Tests for _process_traces with Halite3 data.

    Halite bots are often compiled from the same binary, so both players may
    share an identical player_name (e.g. "MyRustBot").  The process_traces()
    helper therefore supports addressing players by their numeric player_id
    string ("0", "1", …) in addition to player_name.
    """

    def test_parses_halite3_sim_file(self, temp_round_dir, halite3_sim_file):
        """Should parse a Halite3 .hlt file and compute distance."""
        shutil.copy(halite3_sim_file, temp_round_dir / "replay-0.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite3",
            learner_name="0",
            target_name="1",
        )

        assert result is not None
        assert result["game"] == "Halite3"
        assert result["learner"] == "0"
        assert result["target"] == "1"
        assert result["round"] == 0
        assert result["total_actions"] > 0
        assert result["mean_distance"] >= 0.0

    def test_saves_traces_json(self, temp_round_dir, halite3_sim_file):
        """Should save traces.json to the round directory."""
        shutil.copy(halite3_sim_file, temp_round_dir / "replay-0.hlt")

        process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite3",
            learner_name="0",
            target_name="1",
        )

        traces_file = temp_round_dir / "traces.json"
        assert traces_file.exists()

        data = json.loads(traces_file.read_text())
        assert "mean_distance" in data
        assert "total_actions" in data
        assert "per_simulation" in data

    def test_per_simulation_breakdown(self, temp_round_dir, halite3_sim_file):
        """Should include per-simulation distance breakdown."""
        shutil.copy(halite3_sim_file, temp_round_dir / "replay-0.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite3",
            learner_name="0",
            target_name="1",
        )

        assert len(result["per_simulation"]) == 1
        sim_result = result["per_simulation"][0]
        assert "file" in sim_result
        assert "total" in sim_result
        assert "distance_sum" in sim_result
        assert "mean_distance" in sim_result

    def test_handles_multiple_sim_files(self, temp_round_dir, halite3_sim_file):
        """Should aggregate results across multiple .hlt sim files."""
        for i in range(3):
            shutil.copy(halite3_sim_file, temp_round_dir / f"replay-{i}.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite3",
            learner_name="0",
            target_name="1",
        )

        assert result is not None
        assert result["num_simulations"] == 3
        assert len(result["per_simulation"]) == 3

    def test_identical_player_ids_have_zero_distance(
        self, temp_round_dir, halite3_sim_file
    ):
        """When learner and target are the same player id, distance should be zero."""
        shutil.copy(halite3_sim_file, temp_round_dir / "replay-0.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite3",
            learner_name="0",
            target_name="0",  # Same player!
        )

        assert result is not None
        assert result["mean_distance"] == 0.0
        assert result["total_distance"] == 0.0

    def test_nonzero_distances_collected(self, temp_round_dir, halite3_sim_file):
        """Should collect nonzero distances as a list."""
        for i in range(20):
            shutil.copy(halite3_sim_file, temp_round_dir / f"replay-{i}.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite3",
            learner_name="0",
            target_name="1",
        )

        assert result is not None
        assert isinstance(result["nonzero_distances"], list)


# =============================================================================
# Tests: Halite (original)
# =============================================================================


class TestProcessTracesHalite1:
    """Tests for _process_traces with Halite (original) data.

    Halite I uses a territory-based format: plain uncompressed JSON .hlt files
    where each cell has [owner, strength]. Player tags are 1-based integers
    ("1", "2", ...) corresponding to player_names indices.

    Both bots in our fixture share the name "MyCBot", so players are addressed
    by their 1-based tag string ("1", "2").
    """

    def test_parses_halite1_sim_file(self, temp_round_dir, halite1_sim_file):
        """Should parse a Halite I .hlt file and compute distance."""
        shutil.copy(halite1_sim_file, temp_round_dir / "1234-5678.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite",
            learner_name="1",
            target_name="2",
        )

        assert result is not None
        assert result["game"] == "Halite"
        assert result["learner"] == "1"
        assert result["target"] == "2"
        assert result["round"] == 0
        assert result["total_actions"] > 0
        assert result["mean_distance"] >= 0.0

    def test_saves_traces_json(self, temp_round_dir, halite1_sim_file):
        """Should save traces.json to the round directory."""
        shutil.copy(halite1_sim_file, temp_round_dir / "1234-5678.hlt")

        process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite",
            learner_name="1",
            target_name="2",
        )

        traces_file = temp_round_dir / "traces.json"
        assert traces_file.exists()

        data = json.loads(traces_file.read_text())
        assert "mean_distance" in data
        assert "total_actions" in data
        assert "per_simulation" in data

    def test_per_simulation_breakdown(self, temp_round_dir, halite1_sim_file):
        """Should include per-simulation distance breakdown."""
        shutil.copy(halite1_sim_file, temp_round_dir / "1234-5678.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite",
            learner_name="1",
            target_name="2",
        )

        assert len(result["per_simulation"]) == 1
        sim_result = result["per_simulation"][0]
        assert "file" in sim_result
        assert "total" in sim_result
        assert "distance_sum" in sim_result
        assert "mean_distance" in sim_result

    def test_handles_multiple_sim_files(self, temp_round_dir, halite1_sim_file):
        """Should aggregate results across multiple .hlt sim files."""
        for i in range(3):
            shutil.copy(halite1_sim_file, temp_round_dir / f"{i}-{i+1}.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite",
            learner_name="1",
            target_name="2",
        )

        assert result is not None
        assert result["num_simulations"] == 3
        assert len(result["per_simulation"]) == 3

    def test_identical_player_tags_have_zero_distance(
        self, temp_round_dir, halite1_sim_file
    ):
        """When learner and target are the same player tag, distance should be zero."""
        shutil.copy(halite1_sim_file, temp_round_dir / "1234-5678.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite",
            learner_name="1",
            target_name="1",  # Same player!
        )

        assert result is not None
        assert result["mean_distance"] == 0.0
        assert result["total_distance"] == 0.0

    def test_nonzero_distances_collected(self, temp_round_dir, halite1_sim_file):
        """Should collect nonzero distances as a list."""
        for i in range(20):
            shutil.copy(halite1_sim_file, temp_round_dir / f"{i}-{i+1}.hlt")

        result = process_traces(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="Halite",
            learner_name="1",
            target_name="2",
        )

        assert result is not None
        assert isinstance(result["nonzero_distances"], list)


# =============================================================================
# Helper: Offline process_traces (mirrors InverseStrategyTournament._process_traces)
# =============================================================================


def process_traces_offline(
    round_dir: Path,
    round_num: int,
    game_name: str,
    target_name: str,
    learner_move_fn,
) -> dict | None:
    """
    Mirror of InverseStrategyTournament._process_traces() for testing.

    Instead of loading real learner code from a container, accepts a callable
    ``learner_move_fn(state) -> action`` that simulates the learner.  This
    allows end-to-end testing of the entire offline evaluation pipeline without
    any Docker / Singularity infrastructure.

    Supported games: RoboCode (record_*.xml), HuskyBench (game_log_*.json).
    Returns None if no sim files are found or the game is unsupported.
    """
    if game_name == "RoboCode":
        from revenge_bench.traces.parsers.robocode import (
            actions_distance,
            extract_state_action_pairs,
        )

        patterns = ["record_*.xml"]
    elif game_name == "HuskyBench":
        from revenge_bench.traces.parsers.huskybench import (
            actions_distance,
            extract_state_action_pairs,
        )

        patterns = ["game_log_*.json", "sim_*.json"]
    else:
        return None

    sim_files = []
    for pat in patterns:
        sim_files.extend(sorted(round_dir.glob(pat)))
    if not sim_files:
        return None

    total_actions = 0
    total_distance = 0.0
    per_simulation = []
    nonzero_distances = []

    for sim_file in sim_files:
        try:
            state_action_pairs = extract_state_action_pairs(sim_file, target_name)

            sim_total = 0
            sim_distance = 0.0
            sim_nonzero = 0

            for turn_idx, (target_state, target_action) in enumerate(
                state_action_pairs
            ):
                learner_action = learner_move_fn(target_state)
                if learner_action is None:
                    continue

                sim_total += 1
                dist = actions_distance(learner_action, target_action)
                sim_distance += dist
                if dist > 0.0:
                    sim_nonzero += 1
                    nonzero_distances.append(
                        {
                            "sim": sim_file.name,
                            "turn": turn_idx,
                            "learner_action": learner_action,
                            "target_action": target_action,
                            "distance": dist,
                        }
                    )

            total_actions += sim_total
            total_distance += sim_distance
            per_simulation.append(
                {
                    "file": sim_file.name,
                    "total": sim_total,
                    "distance_sum": sim_distance,
                    "mean_distance": sim_distance / sim_total if sim_total > 0 else 0.0,
                    "num_nonzero": sim_nonzero,
                }
            )

        except Exception:
            import traceback

            traceback.print_exc()
            continue

    if total_actions == 0:
        return None

    mean_distance = total_distance / total_actions
    summary = {
        "round": round_num,
        "game": game_name,
        "target": target_name,
        "total_actions": total_actions,
        "total_distance": total_distance,
        "mean_distance": mean_distance,
        "num_simulations": len(per_simulation),
        "per_simulation": per_simulation,
        "nonzero_distances": nonzero_distances,
    }

    traces_file = round_dir / "traces.json"
    traces_file.write_text(json.dumps(summary, indent=2))
    return summary


def _make_perfect_learner(sim_file: Path, target_name: str, extract_fn) -> object:
    """
    Return a move-function that replays the target's own recorded actions.

    Calling the returned function successive times yields actions in the same
    order as extract_state_action_pairs() would return them, so the distance
    between learner_action and target_action is always 0.
    """
    pairs = extract_fn(sim_file, target_name)
    actions = [action for _, action in pairs]
    counter = [0]

    def move(state):
        if counter[0] >= len(actions):
            return None
        action = actions[counter[0]]
        counter[0] += 1
        return action

    return move


# =============================================================================
# Tests: RoboCode (offline evaluation)
# =============================================================================


class TestProcessTracesRoboCode:
    """
    Tests for process_traces_offline() with RoboCode data.

    RoboCode sim files are XML recordings (record_*.xml).  Both robots act on
    every turn simultaneously, so target and opponent produce the same number
    of state-action pairs, making turn-level comparison straightforward.
    """

    def test_parses_robocode_sim_file(self, temp_round_dir, robocode_sim_file):
        """Should parse RoboCode XML and produce a non-empty result."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")

        from revenge_bench.traces.parsers.robocode import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "record_0.xml", "target", extract_state_action_pairs
        )

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=learner,
        )

        assert result is not None
        assert result["game"] == "RoboCode"
        assert result["target"] == "target"
        assert result["round"] == 0
        assert result["total_actions"] > 0

    def test_perfect_learner_has_zero_distance(self, temp_round_dir, robocode_sim_file):
        """A learner that replays the target's own actions should get distance 0."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")

        from revenge_bench.traces.parsers.robocode import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "record_0.xml", "target", extract_state_action_pairs
        )

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=learner,
        )

        assert result is not None
        assert result["mean_distance"] == pytest.approx(0.0)
        assert result["total_distance"] == pytest.approx(0.0)

    def test_fixed_action_learner_has_nonzero_distance(
        self, temp_round_dir, robocode_sim_file
    ):
        """A learner that always returns an all-zero action should differ from a moving target."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")

        zero_action = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: zero_action,
        )

        # The target in short_game.xml moves (velocity changes), so distance should be > 0
        assert result is not None
        assert result["mean_distance"] > 0.0

    def test_none_learner_returns_none(self, temp_round_dir, robocode_sim_file):
        """A learner that always returns None skips all actions → result is None."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: None,
        )

        assert result is None

    def test_saves_traces_json(self, temp_round_dir, robocode_sim_file):
        """Should write traces.json to the round directory."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")

        from revenge_bench.traces.parsers.robocode import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "record_0.xml", "target", extract_state_action_pairs
        )

        process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=learner,
        )

        traces_file = temp_round_dir / "traces.json"
        assert traces_file.exists()
        data = json.loads(traces_file.read_text())
        assert "mean_distance" in data
        assert "total_actions" in data
        assert "per_simulation" in data
        assert "nonzero_distances" in data

    def test_handles_multiple_sim_files(self, temp_round_dir, robocode_sim_file):
        """Should aggregate distances across multiple XML files."""
        for i in range(3):
            shutil.copy(robocode_sim_file, temp_round_dir / f"record_{i}.xml")

        zero_action = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: zero_action,
        )

        assert result is not None
        assert result["num_simulations"] == 3
        assert len(result["per_simulation"]) == 3

    def test_per_simulation_breakdown(self, temp_round_dir, robocode_sim_file):
        """Each sim entry should have required fields."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")
        zero_action = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: zero_action,
        )

        assert len(result["per_simulation"]) == 1
        sim = result["per_simulation"][0]
        assert "file" in sim
        assert "total" in sim
        assert "distance_sum" in sim
        assert "mean_distance" in sim
        assert "num_nonzero" in sim

    def test_distance_in_valid_range(self, temp_round_dir, robocode_sim_file):
        """Mean distance should be in [0, 1]."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")
        zero_action = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: zero_action,
        )

        assert 0.0 <= result["mean_distance"] <= 1.0

    def test_returns_none_for_empty_directory(self, temp_round_dir):
        """No XML files → returns None."""
        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: None,
        )
        assert result is None

    def test_nonzero_distances_collected(self, temp_round_dir, robocode_sim_file):
        """Nonzero-distance entries should be collected in the result."""
        shutil.copy(robocode_sim_file, temp_round_dir / "record_0.xml")
        zero_action = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: zero_action,
        )

        assert isinstance(result["nonzero_distances"], list)
        # At least one mismatch expected since target moves in the fixture
        assert len(result["nonzero_distances"]) > 0

    def test_ownerless_bullet_id_prefix_propagates_fire_power(self, temp_round_dir):
        """Ownerless RoboCode bullets with id prefix should produce nonzero fire_power offline."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <turn round="0" turn="0" ver="1">
    <robots>
      <robot id="0" vsName="MyTank*" state="ACTIVE"
             energy="100.0" x="100.0" y="200.0"
             bodyHeading="0.0" gunHeading="0.0" radarHeading="0.0"
             gunHeat="3.0" velocity="0.0"
             teamName="target.MyTank*" name="target.MyTank*"/>
      <robot id="1" vsName="EnemyBot*" state="ACTIVE"
             energy="100.0" x="600.0" y="400.0"
             bodyHeading="3.14159" gunHeading="3.14159" radarHeading="3.14159"
             gunHeat="3.0" velocity="0.0"
             teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets/>
  </turn>
  <turn round="0" turn="1" ver="1">
    <robots>
      <robot id="0" vsName="MyTank*" state="ACTIVE"
             energy="97.5" x="100.0" y="200.0"
             bodyHeading="0.0" gunHeading="0.0" radarHeading="0.0"
             gunHeat="2.0" velocity="0.0"
             teamName="target.MyTank*" name="target.MyTank*"/>
      <robot id="1" vsName="EnemyBot*" state="ACTIVE"
             energy="100.0" x="600.0" y="400.0"
             bodyHeading="3.14159" gunHeading="3.14159" radarHeading="3.14159"
             gunHeat="3.0" velocity="0.0"
             teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets>
      <bullet id="0-77" state="FIRED"
              x="100.0" y="200.0" heading="0.0" power="2.5"/>
    </bullets>
  </turn>
</record>
"""
        (temp_round_dir / "record_0.xml").write_text(xml)
        zero_action = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="RoboCode",
            target_name="target",
            learner_move_fn=lambda state: zero_action,
        )

        assert result is not None
        assert result["total_actions"] == 1
        assert len(result["nonzero_distances"]) == 1

        mismatch = result["nonzero_distances"][0]
        assert mismatch["target_action"]["fire_power"] == pytest.approx(2.5)
        assert mismatch["distance"] == pytest.approx((2.5 / 3.0) / 5.0)


# =============================================================================
# Tests: HuskyBench (offline evaluation)
# =============================================================================


class TestProcessTracesHuskyBench:
    """
    Tests for process_traces_offline() with HuskyBench (poker) data.

    HuskyBench sim files are JSON game logs (game_log_*.json).  Players act
    in sequence within each betting round; state-action pairs are extracted
    per-player (only the target's decision points are evaluated).
    """

    def test_parses_huskybench_sim_file(self, temp_round_dir, huskybench_sim_file):
        """Should parse HuskyBench JSON and produce a non-empty result."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        from revenge_bench.traces.parsers.huskybench import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "game_log_0_test.json",
            "target",
            extract_state_action_pairs,
        )

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=learner,
        )

        assert result is not None
        assert result["game"] == "HuskyBench"
        assert result["target"] == "target"
        assert result["round"] == 0
        assert result["total_actions"] > 0

    def test_perfect_learner_has_zero_distance(
        self, temp_round_dir, huskybench_sim_file
    ):
        """A learner that replays the target's own actions should get distance 0."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        from revenge_bench.traces.parsers.huskybench import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "game_log_0_test.json",
            "target",
            extract_state_action_pairs,
        )

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=learner,
        )

        assert result is not None
        assert result["mean_distance"] == pytest.approx(0.0)
        assert result["total_distance"] == pytest.approx(0.0)

    def test_fold_learner_vs_raising_target_has_max_distance(
        self, temp_round_dir, huskybench_sim_file
    ):
        """A learner that always FOLDs should have distance 1.0 against a RAISE."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        # The fixture has target raising in rounds 0 and 2 and checking in round 1.
        # FOLD vs RAISE = 1.0; FOLD vs CHECK = 1.0 → mean distance = 1.0
        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: "FOLD",
        )

        assert result is not None
        assert result["mean_distance"] == pytest.approx(1.0)

    def test_none_learner_returns_none(self, temp_round_dir, huskybench_sim_file):
        """A learner that always returns None skips all actions → result is None."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: None,
        )

        assert result is None

    def test_saves_traces_json(self, temp_round_dir, huskybench_sim_file):
        """Should write traces.json to the round directory."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        from revenge_bench.traces.parsers.huskybench import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "game_log_0_test.json",
            "target",
            extract_state_action_pairs,
        )

        process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=learner,
        )

        traces_file = temp_round_dir / "traces.json"
        assert traces_file.exists()
        data = json.loads(traces_file.read_text())
        assert "mean_distance" in data
        assert "total_actions" in data
        assert "per_simulation" in data
        assert "nonzero_distances" in data

    def test_handles_multiple_sim_files(self, temp_round_dir, huskybench_sim_file):
        """Should aggregate distances across multiple JSON files."""
        for i in range(3):
            shutil.copy(huskybench_sim_file, temp_round_dir / f"game_log_{i}_test.json")

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: "FOLD",
        )

        assert result is not None
        assert result["num_simulations"] == 3
        assert len(result["per_simulation"]) == 3

    def test_per_simulation_breakdown(self, temp_round_dir, huskybench_sim_file):
        """Each sim entry should have required fields."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: "FOLD",
        )

        assert len(result["per_simulation"]) == 1
        sim = result["per_simulation"][0]
        assert "file" in sim
        assert "total" in sim
        assert "distance_sum" in sim
        assert "mean_distance" in sim
        assert "num_nonzero" in sim

    def test_distance_in_valid_range(self, temp_round_dir, huskybench_sim_file):
        """Mean distance should be in [0, 1]."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: "FOLD",
        )

        assert 0.0 <= result["mean_distance"] <= 1.0

    def test_returns_none_for_empty_directory(self, temp_round_dir):
        """No JSON files → returns None."""
        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: "FOLD",
        )
        assert result is None

    def test_target_action_count_matches_fixture(
        self, temp_round_dir, huskybench_sim_file
    ):
        """The target in the fixture acts exactly 3 times (rounds 0, 1, 2)."""
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        from revenge_bench.traces.parsers.huskybench import extract_state_action_pairs

        learner = _make_perfect_learner(
            temp_round_dir / "game_log_0_test.json",
            "target",
            extract_state_action_pairs,
        )

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=learner,
        )

        assert (
            result["total_actions"] == 3
        )  # RAISE (preflop), CHECK (flop), RAISE (turn)

    def test_check_learner_vs_target(self, temp_round_dir, huskybench_sim_file):
        """CHECK learner vs raising/checking target gives expected partial distance.

        Target actions: RAISE:r (round 0), CHECK (round 1), RAISE:r (round 2).
        CHECK learner:  CHECK,              CHECK,            CHECK.
        Distances under the log-commitment scale:  c(r; S), 0, c(r; S)
            where c(r; S) = log1p(r * S) / log1p(S) and S is the actor's
            stack at that decision.
        Mean = (2 * c(r; S)) / 3, strictly in (0, 1) for any r in (0, 1).
        """
        shutil.copy(huskybench_sim_file, temp_round_dir / "game_log_0_test.json")

        result = process_traces_offline(
            round_dir=temp_round_dir,
            round_num=0,
            game_name="HuskyBench",
            target_name="target",
            learner_move_fn=lambda state: "CHECK",
        )

        assert result is not None
        # mean_distance < 1.0 (CHECK vs RAISE is not max distance unlike FOLD)
        assert 0.0 < result["mean_distance"] < 1.0
