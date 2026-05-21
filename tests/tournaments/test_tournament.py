"""
Tests for tournaments/tournament.py - AbstractTournament base class.

Tests:
- Tournament ID generation
- Metadata management
- Output directory handling
- File handler cleanup
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from revenge_bench.tournaments.tournament import AbstractTournament

# =============================================================================
# Test: AbstractTournament
# =============================================================================


class TestAbstractTournament:
    """Tests for AbstractTournament base class."""

    @pytest.fixture
    def basic_config(self):
        """Basic tournament config."""
        return {
            "tournament": {"rounds": 5},
            "game": {"name": "BattleSnake", "sims_per_round": 100},
            "players": [
                {"agent": "static", "name": "player1"},
                {"agent": "static", "name": "player2"},
            ],
            "prompts": {},
        }

    @pytest.fixture
    def tournament(self, basic_config, tmp_path):
        """Create a basic tournament instance."""
        return AbstractTournament(
            config=basic_config,
            name="TestTournament",
            output_dir=tmp_path / "output",
        )

    def test_creates_tournament_id(self, tournament):
        """Should generate a valid tournament ID."""
        assert tournament.tournament_id is not None
        assert "TestTournament" in tournament.tournament_id
        assert "BattleSnake" in tournament.tournament_id
        # Format: TestTournament.BattleSnake.YYMMDDHHMMSS
        parts = tournament.tournament_id.split(".")
        assert len(parts) == 3

    def test_stores_config(self, tournament, basic_config):
        """Should store the config."""
        assert tournament.config == basic_config
        assert tournament.name == "TestTournament"

    def test_creates_metadata(self, tournament):
        """Should create metadata dict."""
        metadata = tournament.get_metadata()

        assert "name" in metadata
        assert "tournament_id" in metadata
        assert "config" in metadata
        assert "created_timestamp" in metadata
        assert metadata["name"] == "TestTournament"

    def test_local_output_dir_creates_path(self, tournament, tmp_path):
        """Should create output directory path."""
        output_dir = tournament.local_output_dir

        assert output_dir is not None
        assert isinstance(output_dir, Path)

    def test_local_output_dir_pytest_override(self, basic_config, tmp_path):
        """Should use /tmp path when in pytest."""
        import os

        # PYTEST_CURRENT_TEST is set by pytest
        assert "PYTEST_CURRENT_TEST" in os.environ

        tournament = AbstractTournament(
            config=basic_config,
            name="TestTournament",
            output_dir=tmp_path / "output",
        )

        # In pytest, should use /tmp/revenge_bench/
        assert "/tmp/revenge-bench" in str(tournament.local_output_dir)

    def test_cleanup_handlers(self, tournament):
        """Should clean up file handlers without error."""
        # This should not raise
        tournament.cleanup_handlers()

    def test_copy_game_log_to_agent(self, tournament):
        """Should handle log copying (with mock agent)."""
        mock_agent = MagicMock()
        mock_agent.environment = MagicMock()
        mock_agent.name = "test_agent"

        # This should not raise even if environment is mock
        tournament._copy_game_log_to_agent(
            mock_agent, round_num=1, log_output="test log content"
        )


# =============================================================================
# Test: Tournament ID Format
# =============================================================================


class TestTournamentIdFormat:
    """Tests for tournament ID generation."""

    def test_id_contains_name(self, tmp_path):
        """Tournament ID should contain the tournament name."""
        config = {"game": {"name": "TestGame"}}
        tournament = AbstractTournament(
            config=config,
            name="MyTournament",
            output_dir=tmp_path,
        )

        assert "MyTournament" in tournament.tournament_id

    def test_id_contains_game_name(self, tmp_path):
        """Tournament ID should contain the game name."""
        config = {"game": {"name": "RobotRumble"}}
        tournament = AbstractTournament(
            config=config,
            name="TestTournament",
            output_dir=tmp_path,
        )

        assert "RobotRumble" in tournament.tournament_id

    def test_id_contains_timestamp(self, tmp_path):
        """Tournament ID should contain a timestamp."""
        config = {"game": {"name": "TestGame"}}
        tournament = AbstractTournament(
            config=config,
            name="TestTournament",
            output_dir=tmp_path,
        )

        # Last part should be numeric (YYMMDDHHMMSS)
        parts = tournament.tournament_id.split(".")
        assert parts[-1].isdigit()
        assert len(parts[-1]) == 12  # YYMMDDHHMMSS
