"""
Unit tests for HuskyBenchArena.

Tests validate_code() and get_results() methods without requiring Docker.
"""

from unittest.mock import patch
from pathlib import Path

import pytest

from revenge_bench.arenas.arena import RoundStats
from revenge_bench.arenas.huskybench.huskybench import (
    HB_LOG_ENGINE,
    HB_PORT,
    HB_REGEX_SCORE,
    HB_SCRIPT,
    HuskyBenchArena,
)

from .conftest import MockPlayer

VALID_PLAYER_PY = """
from client.base_player import BasePlayer

class Player(BasePlayer):
    def get_action(self, game_state):
        return 'fold'
"""


class TestHuskyBenchValidation:
    """Tests for HuskyBenchArena.validate_code()"""

    @pytest.fixture
    def arena(self, tmp_log_dir, minimal_config):
        """Create HuskyBenchArena instance with mocked environment."""
        from pathlib import Path

        config = minimal_config.copy()
        config["game"]["sims_per_round"] = 10
        arena = HuskyBenchArena.__new__(HuskyBenchArena)
        arena.submission = "client/player.py"
        arena.log_local = tmp_log_dir
        arena.log_env = Path("/logs")  # Container log path
        arena.config = config
        arena.num_players = 2
        arena.run_engine = f"python engine/main.py --port {HB_PORT} --players 2 --sim --sim-rounds 10"
        arena.logger = type("Logger", (), {"debug": lambda self, msg: None, "info": lambda self, msg: None})()
        return arena

    @patch("revenge_bench.arenas.huskybench.huskybench.create_file_in_container")
    def test_valid_submission(self, mock_create_file, arena, mock_player_factory):
        """Test that a valid player.py passes validation."""
        player = mock_player_factory(
            name="test_player",
            files={
                "client/main.py": "# client main",
                "client/player.py": VALID_PLAYER_PY,
            },
            command_outputs={
                "ls client": {"output": "main.py\nplayer.py\n", "returncode": 0},
                f"chmod +x {HB_SCRIPT}; ./{HB_SCRIPT}": {"output": "", "returncode": 0},
            },
        )
        is_valid, error = arena.validate_code(player)
        assert is_valid is True
        assert error is None

    def test_missing_main_file(self, arena, mock_player_factory):
        """Test that missing client/main.py fails validation."""
        player = mock_player_factory(
            name="test_player",
            files={"client/player.py": VALID_PLAYER_PY},
            command_outputs={
                "ls client": {"output": "player.py\n", "returncode": 0},
            },
        )
        is_valid, error = arena.validate_code(player)
        assert is_valid is False
        assert "main.py" in error

    def test_missing_player_file(self, arena, mock_player_factory):
        """Test that missing client/player.py fails validation."""
        player = mock_player_factory(
            name="test_player",
            files={"client/main.py": "# main"},
            command_outputs={
                "ls client": {"output": "main.py\n", "returncode": 0},
            },
        )
        is_valid, error = arena.validate_code(player)
        assert is_valid is False
        assert "player.py" in error


class TestHuskyBenchResults:
    """Tests for HuskyBenchArena.get_results()"""

    @pytest.fixture
    def arena(self, tmp_log_dir, minimal_config):
        """Create HuskyBenchArena instance."""
        config = minimal_config.copy()
        config["game"]["name"] = "HuskyBench"
        config["game"]["sims_per_round"] = 10
        arena = HuskyBenchArena.__new__(HuskyBenchArena)
        arena.submission = "client/player.py"
        arena.log_local = tmp_log_dir
        arena.config = config
        arena.num_players = 2
        arena.logger = type("Logger", (), {"debug": lambda self, msg: None, "info": lambda self, msg: None})()
        return arena

    def _create_player_log(self, round_dir, player_name: str, player_id: str):
        """Create a player log file with connection info."""
        log_file = round_dir / f"{player_name}.log"
        log_file.write_text(f"Starting client...\nConnected with player ID: {player_id}\nGame started.\n")

    def _create_engine_log(self, round_dir, scores: list[tuple[str, int]]):
        """
        Create engine log file with final scores.

        Args:
            scores: List of (player_id, final_money) tuples
        """
        log_file = round_dir / HB_LOG_ENGINE
        lines = ["Engine starting...\n", "Game initialized.\n"]
        for player_id, money in scores:
            lines.append(f"Player {player_id} delta updated: +100 - 50 = 50, money: 1000 -> {money}\n")
        log_file.write_text("".join(lines))

    def test_parse_results_player1_wins(self, arena, tmp_log_dir):
        """Test parsing results when player 1 has more chips."""
        round_dir = tmp_log_dir / "rounds" / "1"
        round_dir.mkdir(parents=True)

        # Create player logs with their IDs
        self._create_player_log(round_dir, "Alice", "1")
        self._create_player_log(round_dir, "Bob", "2")

        # Create engine log with final scores
        self._create_engine_log(round_dir, [("1", 1500), ("2", 500)])

        agents = [MockPlayer("Alice"), MockPlayer("Bob")]
        stats = RoundStats(round_num=1, agents=agents)

        arena.get_results(agents, round_num=1, stats=stats)

        assert stats.winner == "Alice"
        assert stats.scores["Alice"] == 1500
        assert stats.scores["Bob"] == 500

    def test_parse_results_player2_wins(self, arena, tmp_log_dir):
        """Test parsing results when player 2 has more chips."""
        round_dir = tmp_log_dir / "rounds" / "1"
        round_dir.mkdir(parents=True)

        self._create_player_log(round_dir, "Alice", "1")
        self._create_player_log(round_dir, "Bob", "2")
        self._create_engine_log(round_dir, [("1", 300), ("2", 1700)])

        agents = [MockPlayer("Alice"), MockPlayer("Bob")]
        stats = RoundStats(round_num=1, agents=agents)

        arena.get_results(agents, round_num=1, stats=stats)

        assert stats.winner == "Bob"
        assert stats.scores["Alice"] == 300
        assert stats.scores["Bob"] == 1700


@pytest.fixture
def hb_arena(tmp_path, minimal_config):
    """HuskyBenchArena instance for empty-scores tests; log_local set per-test."""
    config = minimal_config.copy()
    config["game"]["name"] = "HuskyBench"
    config["game"]["sims_per_round"] = 10
    arena = HuskyBenchArena.__new__(HuskyBenchArena)
    arena.submission = "client/player.py"
    arena.log_local = tmp_path
    arena.config = config
    arena.num_players = 2
    arena.logger = type(
        "Logger",
        (),
        {
            "debug": lambda self, msg: None,
            "info": lambda self, msg: None,
            "warning": lambda self, msg: None,
        },
    )()
    return arena


@pytest.fixture
def hb_agents():
    return [MockPlayer("target"), MockPlayer("opponent")]


@pytest.fixture
def hb_round_stats(hb_agents):
    return RoundStats(round_num=0, agents=hb_agents)


def _write_logs(round_dir, engine_lines, agent_logs):
    """agent_logs: dict[str, list[str]] mapping agent name -> log lines."""
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "engine.log").write_text("\n".join(engine_lines) + "\n")
    for name, lines in agent_logs.items():
        (round_dir / f"{name}.log").write_text("\n".join(lines) + "\n")


def test_get_results_empty_scores_only_target_connected_target_wins(tmp_path, hb_arena, hb_agents, hb_round_stats):
    """When engine produced no score updates and only the target connected,
    the opponent failed to connect and the target should win."""
    round_dir = tmp_path / "rounds" / "0"
    _write_logs(
        round_dir,
        engine_lines=[],  # no "Player N delta updated" lines at all
        agent_logs={
            "target": ["Connected with player ID: 12345"],
            "opponent": ["Failed to bind socket: address already in use"],
        },
    )
    hb_arena.log_local = tmp_path
    hb_arena.get_results(hb_agents, round_num=0, stats=hb_round_stats)

    assert hb_round_stats.winner == "target"
    assert hb_round_stats.scores == {"target": 1, "opponent": 0}
    assert hb_round_stats.player_stats["target"].score == 1
    assert hb_round_stats.player_stats["opponent"].score == 0


def test_get_results_empty_scores_only_opponent_connected_opponent_wins(tmp_path, hb_arena, hb_agents, hb_round_stats):
    round_dir = tmp_path / "rounds" / "0"
    _write_logs(
        round_dir,
        engine_lines=[],
        agent_logs={
            "target": ["python: command not found"],
            "opponent": ["Connected with player ID: 99"],
        },
    )
    hb_arena.log_local = tmp_path
    hb_arena.get_results(hb_agents, round_num=0, stats=hb_round_stats)
    assert hb_round_stats.winner == "opponent"
    assert hb_round_stats.scores == {"target": 0, "opponent": 1}


def test_get_results_empty_scores_both_connected_is_tie(tmp_path, hb_arena, hb_agents, hb_round_stats):
    """Both agents connected but engine produced no score updates — fault
    unattributable, count as a Tie with zero scores."""
    round_dir = tmp_path / "rounds" / "0"
    _write_logs(
        round_dir,
        engine_lines=["random unrelated log line"],
        agent_logs={
            "target": ["Connected with player ID: 1"],
            "opponent": ["Connected with player ID: 2"],
        },
    )
    hb_arena.log_local = tmp_path
    hb_arena.get_results(hb_agents, round_num=0, stats=hb_round_stats)
    assert hb_round_stats.winner == "Tie"
    assert hb_round_stats.scores == {"target": 0, "opponent": 0}


def test_get_results_empty_scores_neither_connected_is_tie(tmp_path, hb_arena, hb_agents, hb_round_stats):
    """Neither agent connected; engine never started anything — Tie."""
    round_dir = tmp_path / "rounds" / "0"
    _write_logs(
        round_dir,
        engine_lines=[],
        agent_logs={
            "target": ["import error"],
            "opponent": ["import error"],
        },
    )
    hb_arena.log_local = tmp_path
    hb_arena.get_results(hb_agents, round_num=0, stats=hb_round_stats)
    assert hb_round_stats.winner == "Tie"
    assert hb_round_stats.scores == {"target": 0, "opponent": 0}


def test_get_results_normal_path_unchanged(tmp_path, hb_arena, hb_agents, hb_round_stats):
    """Regression: a healthy game with both connected and scores recorded
    must work exactly as before."""
    round_dir = tmp_path / "rounds" / "0"
    _write_logs(
        round_dir,
        engine_lines=[
            "Player 1 delta updated: +50 = 50, money: 0 -> 50",
            "Player 2 delta updated: +30 = 30, money: 0 -> 30",
        ],
        agent_logs={
            "target": ["Connected with player ID: 1"],
            "opponent": ["Connected with player ID: 2"],
        },
    )
    hb_arena.log_local = tmp_path
    hb_arena.get_results(hb_agents, round_num=0, stats=hb_round_stats)
    assert hb_round_stats.winner == "target"
    assert hb_round_stats.scores == {"target": 50, "opponent": 30}


class TestHuskyBenchRegex:
    """Tests for the score parsing regex."""

    def test_regex_matches_score_line(self):
        """Test that the score regex correctly parses a score line."""
        line = "Player 1 delta updated: +100 - 50 = 50, money: 1000 -> 1050"
        match = HB_REGEX_SCORE.search(line)
        assert match is not None
        assert match.group(1) == "1"  # Player ID
        assert match.group(2) == "1050"  # Final money

    def test_regex_matches_multiple_digits(self):
        """Test regex with larger numbers."""
        line = "Player 42 delta updated: +500 - 200 = 300, money: 10000 -> 15000"
        match = HB_REGEX_SCORE.search(line)
        assert match is not None
        assert match.group(1) == "42"
        assert match.group(2) == "15000"

    def test_regex_does_not_match_other_lines(self):
        """Test that regex doesn't match non-score lines."""
        lines = [
            "Game started",
            "Player 1 folded",
            "Round complete",
        ]
        for line in lines:
            assert HB_REGEX_SCORE.search(line) is None


class TestHuskyBenchConfig:
    """Tests for HuskyBenchArena configuration and properties."""

    def test_arena_name(self):
        """Test that arena has correct name."""
        assert HuskyBenchArena.name == "HuskyBench"

    def test_submission_path(self):
        """Test that submission path is correct."""
        assert HuskyBenchArena.submission == "client/player.py"

    def test_port_constant(self):
        """Test that port constant is defined."""
        assert HB_PORT == 8000

    def test_description_mentions_poker(self):
        """Test that description mentions poker."""
        assert "poker" in HuskyBenchArena.description.lower()


class TestHuskyBenchScript:
    """Tests for generated run script behavior."""

    def test_script_cleans_and_collects_multiple_output_dirs(self):
        """Should clean/move files from Docker and Singularity output roots."""
        arena = HuskyBenchArena.__new__(HuskyBenchArena)
        arena.log_env = Path("/logs")
        arena.logger = type("Logger", (), {"debug": lambda self, msg: None, "info": lambda self, msg: None})()

        agents = [MockPlayer("A"), MockPlayer("B")]
        script = arena._construct_game_script(
            agents=agents,
            run_client="echo run {agent.name}",
            run_engine="echo engine",
            log_outputs=True,
        )

        assert "for out_dir in /app/output output /workspace/output; do" in script
        assert "find \"$out_dir\" -mindepth 1 -maxdepth 1 -type f -delete" in script
        assert "find \"$out_dir\" -mindepth 1 -maxdepth 1 -type f -exec mv -f {} /logs/ \\;" in script
