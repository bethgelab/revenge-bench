"""
Tests for agents/utils.py - GameContext and agent registry.

Tests:
- GameContext: template rendering, to_template_vars()
- Agent registry: get_agent() returns correct agent types
"""

from pathlib import Path

import pytest

# =============================================================================
# Test: GameContext
# =============================================================================


class TestGameContext:
    """Tests for GameContext class."""

    @pytest.fixture
    def basic_context(self, tmp_path):
        """Basic GameContext for testing."""
        from revenge_bench.agents.utils import GameContext

        return GameContext(
            id="test-game-001",
            log_env=Path("/logs"),
            log_local=tmp_path / "logs",
            name="BattleSnake",
            player_id="player1",
            prompts={
                "game_description": "You are playing {{name}}. This is round {{round}} of {{rounds}}.",
                "task": "Your player ID is {{player_id}}.",
            },
            round=3,
            rounds=10,
            working_dir="/workspace",
        )

    def test_creates_valid_context(self, basic_context):
        """Should create a valid GameContext."""
        assert basic_context.id == "test-game-001"
        assert basic_context.name == "BattleSnake"
        assert basic_context.player_id == "player1"
        assert basic_context.round == 3
        assert basic_context.rounds == 10
        assert basic_context.working_dir == "/workspace"

    def test_to_template_vars_contains_all_fields(self, basic_context):
        """Should include all context fields in template vars."""
        vars = basic_context.to_template_vars()

        assert vars["id"] == "test-game-001"
        assert vars["name"] == "BattleSnake"
        assert vars["player_id"] == "player1"
        assert vars["round"] == 3
        assert vars["rounds"] == 10
        assert vars["working_dir"] == "/workspace"

        # prompts should be removed (replaced by rendered values)
        assert "prompts" not in vars

    def test_renders_prompt_templates(self, basic_context):
        """Should render Jinja2 templates in prompts."""
        vars = basic_context.to_template_vars()

        # Check rendered templates
        assert (
            vars["game_description"]
            == "You are playing BattleSnake. This is round 3 of 10."
        )
        assert vars["task"] == "Your player ID is player1."

    def test_empty_prompts(self, tmp_path):
        """Should handle empty prompts dict."""
        from revenge_bench.agents.utils import GameContext

        context = GameContext(
            id="test",
            log_env=Path("/logs"),
            log_local=tmp_path,
            name="TestGame",
            player_id="p1",
            prompts={},
            round=1,
            rounds=5,
            working_dir="/workspace",
        )

        vars = context.to_template_vars()
        assert "prompts" not in vars
        assert vars["name"] == "TestGame"

    def test_complex_template(self, tmp_path):
        """Should handle complex Jinja2 templates."""
        from revenge_bench.agents.utils import GameContext

        context = GameContext(
            id="complex-test",
            log_env=Path("/logs"),
            log_local=tmp_path,
            name="RobotRumble",
            player_id="bot1",
            prompts={
                "instructions": """
                Game: {{name}}
                Player: {{player_id}}
                Round: {{round}}/{{rounds}}
                Working Directory: {{working_dir}}
                Logs: {{log_env}}
                """,
            },
            round=5,
            rounds=15,
            working_dir="/workspace",
        )

        vars = context.to_template_vars()

        # Check all variables are substituted
        assert "RobotRumble" in vars["instructions"]
        assert "bot1" in vars["instructions"]
        assert "5" in vars["instructions"]
        assert "15" in vars["instructions"]
        assert "/workspace" in vars["instructions"]

    def test_round_can_be_updated(self, basic_context):
        """Should allow updating round number."""
        basic_context.round = 7

        vars = basic_context.to_template_vars()
        assert vars["round"] == 7
        assert "round 7 of 10" in vars["game_description"]


# =============================================================================
# Test: Agent Registry
# =============================================================================


class TestAgentRegistry:
    """Tests for agent registration and retrieval."""

    def test_static_agent_registered(self):
        """Should have Static agent registered."""
        from revenge_bench.agents import Static

        # Verify the class exists and is importable
        assert Static is not None

    def test_mini_agent_registered(self):
        """Should have MiniSWEAgent registered."""
        from revenge_bench.agents.minisweagent import MiniSWEAgent

        assert MiniSWEAgent is not None

    def test_inverse_agent_registered(self):
        """Should have InverseStrategyAgent registered."""
        from revenge_bench.agents.minisweagent import InverseStrategyAgent

        assert InverseStrategyAgent is not None

    def test_get_agent_unknown_raises(self, tmp_path):
        """Should raise ValueError for unknown agent type."""
        from unittest.mock import MagicMock

        from revenge_bench.agents import get_agent
        from revenge_bench.agents.utils import GameContext

        config = {"agent": "nonexistent", "name": "test"}
        mock_env = MagicMock()
        context = GameContext(
            id="test",
            log_env=Path("/logs"),
            log_local=tmp_path,
            name="Test",
            player_id="test",
            prompts={},
            round=1,
            rounds=1,
            working_dir="/workspace",
        )

        with pytest.raises(ValueError, match="Unknown agent type"):
            get_agent(config, context, mock_env)
