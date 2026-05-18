"""Tests for GameContext.context_mode field."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from revenge_bench.agents.utils import GameContext


def _ctx(**overrides):
    base = dict(
        id="g", log_env=Path("/logs"), log_local=Path("/tmp"),
        name="Test", player_id="learner", prompts={}, round=1, rounds=3,
        working_dir="/work",
    )
    return GameContext(**(base | overrides))


class TestContextMode:
    def test_default_is_persistent(self):
        ctx = _ctx()
        assert ctx.context_mode == "persistent"

    def test_can_be_set_to_reset(self):
        ctx = _ctx(context_mode="reset")
        assert ctx.context_mode == "reset"

    def test_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            _ctx(context_mode="something_else")

    def test_template_vars_include_context_mode(self):
        ctx = _ctx(context_mode="reset")
        vars = ctx.to_template_vars()
        assert vars["context_mode"] == "reset"


class TestPromptConditional:
    """The instance prompt selects different round-context wording per mode."""

    def _render_default_prompt(self, context_mode):
        import yaml
        from jinja2 import Template
        from revenge_bench.agents.utils import GameContext

        with open("configs/inverse/prompts/system/default.yaml") as f:
            tpl = yaml.safe_load(f)["instance_template"]
        ctx = GameContext(
            id="g", log_env=Path("/logs"), log_local=Path("/tmp"),
            name="BattleSnake", player_id="learner", prompts={},
            round=1, rounds=5, working_dir="/work",
            context_mode=context_mode,
            distance_history={0: 0.5},
        )
        # The actual rendering combines GameContext vars with the agent
        # config dataclass vars; for this test, just render with GameContext
        # vars (sufficient to test the conditional branch).
        template_vars = ctx.to_template_vars()
        # game_description is a custom prompts key — provide a stub.
        template_vars.setdefault("game_description", "")
        template_vars.setdefault("step_limit", 30)
        template_vars.setdefault("cost_limit", 1.0)
        template_vars.setdefault("working_dir", "/work")
        return Template(tpl).render(**template_vars)

    def test_persistent_mode_mentions_persistent_context(self):
        rendered = self._render_default_prompt("persistent")
        # Normalize wrapping so the assertion is whitespace-tolerant.
        normalized = " ".join(rendered.split())
        assert "conversation history persists across rounds" in normalized
        assert "Each round starts fresh" not in rendered

    def test_reset_mode_mentions_starts_fresh(self):
        rendered = self._render_default_prompt("reset")
        assert "Each round starts fresh" in rendered
        assert "persists across rounds" not in rendered
        assert "README_agent.md" in rendered
        # distance_progress was rendered (with seeded distance_history={0: 0.5})
        assert "Round 0:" in rendered
