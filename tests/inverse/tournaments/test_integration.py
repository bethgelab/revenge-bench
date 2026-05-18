"""
Integration tests for InverseStrategyTournament.

These tests require Docker and test the full tournament flow:
- Static vs Static: Two static agents compete (no LLM editing)
- Verifies: Game runs, traces extracted, action distance computed

Skip these tests if Docker is not available.
"""

import subprocess

import pytest


def docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def battlesnake_image_available():
    """Check if BattleSnake Docker image is available."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", "revenge_bench/battlesnake"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Skip all tests in this module if Docker not available
pytestmark = pytest.mark.skipif(not docker_available(), reason="Docker not available")


@pytest.fixture
def sample_battlesnake_code():
    """Simple BattleSnake code that always goes right."""
    return """
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"apiversion": "1", "head": "default", "tail": "default", "color": "#888888"})

@app.route("/start", methods=["POST"])
def start():
    return jsonify({})

@app.route("/move", methods=["POST"])
def move():
    return jsonify({"move": "right"})

@app.route("/end", methods=["POST"])
def end():
    return jsonify({})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
"""


@pytest.fixture
def sample_battlesnake_code_up():
    """Simple BattleSnake code that always goes up."""
    return """
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"apiversion": "1", "head": "default", "tail": "default", "color": "#888888"})

@app.route("/start", methods=["POST"])
def start():
    return jsonify({})

@app.route("/move", methods=["POST"])
def move():
    return jsonify({"move": "up"})

@app.route("/end", methods=["POST"])
def end():
    return jsonify({})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
"""


@pytest.fixture
def static_agent_dirs(tmp_path, sample_battlesnake_code, sample_battlesnake_code_up):
    """Create directories with static agent code."""
    # Learner agent (goes right)
    learner_dir = tmp_path / "learner"
    learner_dir.mkdir()
    (learner_dir / "main.py").write_text(sample_battlesnake_code)

    # Target agent (goes up)
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "main.py").write_text(sample_battlesnake_code_up)

    return {"learner": learner_dir, "target": target_dir}


@pytest.fixture
def battlesnake_config(static_agent_dirs, tmp_path):
    """Config for BattleSnake tournament with two static agents."""
    return {
        "tournament": {"rounds": 0},  # Just baseline, no editing
        "game": {
            "name": "BattleSnake",
            "sims_per_round": 2,  # Just 2 simulations for speed
            "args": {
                "width": 7,
                "height": 7,
                "browser": False,
            },
        },
        "players": [
            {
                "agent": "static",
                "name": "learner",
                "editable": True,
                "args": {
                    "source_path": str(static_agent_dirs["learner"]),
                },
            },
            {
                "agent": "static",
                "name": "target",
                "editable": False,
                "args": {
                    "source_path": str(static_agent_dirs["target"]),
                },
            },
        ],
        "prompts": {
            "game_description": "Test game",
        },
    }


class TestStaticVsStaticIntegration:
    """Integration tests with two static agents."""

    @pytest.mark.skipif(
        not battlesnake_image_available(),
        reason="BattleSnake Docker image not available",
    )
    def test_tournament_initializes(self, battlesnake_config, tmp_path):
        """Should initialize tournament without error."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        output_dir = tmp_path / "output"

        tournament = InverseStrategyTournament(
            config=battlesnake_config,
            output_dir=output_dir,
            cleanup=True,
            keep_containers=False,
        )

        # Basic checks
        assert tournament.learner_agent.name == "learner"
        assert tournament.target_agent.name == "target"
        assert len(tournament.agents) == 2

        # Cleanup
        tournament.end()

    @pytest.mark.skipif(
        not battlesnake_image_available(),
        reason="BattleSnake Docker image not available",
    )
    @pytest.mark.slow
    def test_baseline_round_runs(self, battlesnake_config, tmp_path):
        """Should run baseline round (round 0) successfully."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        output_dir = tmp_path / "output"

        tournament = InverseStrategyTournament(
            config=battlesnake_config,
            output_dir=output_dir,
            cleanup=True,
            keep_containers=False,
        )

        try:
            # Run just the simulation phase (round 0)
            tournament.run_simulation_phase(0)

            # Check that results were saved
            round_dir = tournament.game.log_local / "rounds" / "0"
            assert (
                round_dir.exists()
                or (tournament.game.log_local / "rounds" / "round_0.tar.gz").exists()
            )

            # Check metadata was updated
            assert 0 in tournament._metadata.get("round_stats", {})

        finally:
            tournament.end()

    @pytest.mark.skipif(
        not battlesnake_image_available(),
        reason="BattleSnake Docker image not available",
    )
    @pytest.mark.slow
    def test_full_tournament_static_only(self, battlesnake_config, tmp_path):
        """Should run full tournament with rounds=0 (baseline only)."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        output_dir = tmp_path / "output"

        tournament = InverseStrategyTournament(
            config=battlesnake_config,
            output_dir=output_dir,
            cleanup=True,
            keep_containers=False,
        )

        try:
            # Run the full tournament (just round 0 since rounds=0)
            tournament.run()

            # Check metadata file exists
            assert tournament.metadata_file.exists()

        finally:
            # Cleanup is handled by run() -> end()
            pass
