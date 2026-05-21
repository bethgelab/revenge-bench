"""Tests for the round-outcome classifier and its propagation.

`submission_status` is the canonical "what happened to this round?"
field. Four states:

- ``submitted``             — model called the MCP submit() tool (marker present)
- ``exited_without_submit`` — process exited cleanly, no marker
- ``timeout``               — wall-clock fired, helper SIGTERM'd codex
- ``error``                 — non-zero exit or Python-level exception

These are surfaced in trajectory + agent_stats, and run_round() returns
this string so tournament logging carries it through.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revenge_bench.agents.codex_agent import (
    CodexInverseStrategyAgent,
    _classify_submission,
)
from revenge_bench.agents.utils import GameContext


# --------------------------------------------------------------------- #
# Pure classifier
# --------------------------------------------------------------------- #


class TestClassifySubmission:
    def test_marker_wins_when_clean_exit(self):
        assert _classify_submission("ok", marker_present=True) == "submitted"

    def test_marker_wins_even_on_timeout(self):
        # The helper grace period can race: model writes marker, then
        # helper SIGTERMs before the process can exit cleanly. We
        # treat that as a successful submit.
        assert _classify_submission("timeout", marker_present=True) == "submitted"

    def test_marker_wins_on_error(self):
        # Defensive — model submits, then the codex process happens
        # to crash on cleanup. The submission still counts.
        assert _classify_submission("error(returncode=1)", True) == "submitted"

    def test_clean_exit_without_marker(self):
        assert (
            _classify_submission("ok", marker_present=False)
            == "exited_without_submit"
        )

    def test_timeout_without_marker(self):
        assert (
            _classify_submission("timeout", marker_present=False) == "timeout"
        )

    def test_nonzero_exit_classified_as_error(self):
        assert (
            _classify_submission("error(returncode=2)", False) == "error"
        )

    def test_python_exception_classified_as_error(self):
        # The agent stores type(e).__name__ as exit_status on Python
        # exceptions; anything not "ok"/"timeout" maps to "error".
        assert _classify_submission("RuntimeError", False) == "error"


# --------------------------------------------------------------------- #
# End-to-end through the agent
# --------------------------------------------------------------------- #


def _make_agent(tmp_path: Path) -> CodexInverseStrategyAgent:
    env = MagicMock()
    env.execute.return_value = {"output": "deadbeef\n", "returncode": 0}
    log_local = tmp_path / "logs"
    log_local.mkdir()
    config = {
        "name": "learner",
        "agent": "inverse_codex",
        "config": {
            "codex": {
                "command": "codex",
                "model": "gpt-5.4-mini",
                "auth_file": None,
                "max_round_seconds": 60,
            },
            "agent": {"system_template": "S", "instance_template": "I"},
        },
    }
    gc = GameContext(
        id="g", log_env=Path("/logs"), log_local=log_local, name="T",
        player_id="learner", prompts={},
        round=1, rounds=1, working_dir="/workspace", context_mode="reset",
    )
    return CodexInverseStrategyAgent(config, environment=env, game_context=gc)


def _run_with_router(agent, router):
    agent.environment.execute.side_effect = router
    with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
         patch("revenge_bench.agents.codex_agent.copy_to_container"):
        agent.run()


class TestRunPropagation:
    def test_reset_run_records_exited_without_submit(self, tmp_path):
        """No marker + clean process exit → submission_status =
        'exited_without_submit', exit_status = 'ok'."""
        agent = _make_agent(tmp_path)

        def router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}  # no marker
            return {"output": "", "returncode": 0}

        _run_with_router(agent, router)
        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["submission_status"] == "exited_without_submit"
        assert stats["exit_status"] == "ok"

    def test_reset_run_records_submitted(self, tmp_path):
        agent = _make_agent(tmp_path)

        def router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 0}  # marker exists
            return {"output": "", "returncode": 0}

        _run_with_router(agent, router)
        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["submission_status"] == "submitted"
        assert stats["exit_status"] == "ok"

    def test_reset_run_records_timeout(self, tmp_path):
        agent = _make_agent(tmp_path)

        def router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}  # no marker
            if "codex" in cmd and "exec" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
            return {"output": "deadbeef\n", "returncode": 0}

        _run_with_router(agent, router)
        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["submission_status"] == "timeout"
        assert stats["exit_status"] == "timeout"

    def test_reset_run_records_error_on_nonzero(self, tmp_path):
        agent = _make_agent(tmp_path)

        def router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            if "codex" in cmd and "exec" in cmd:
                return {"output": "boom", "returncode": 7}
            return {"output": "", "returncode": 0}

        _run_with_router(agent, router)
        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["submission_status"] == "error"
        assert stats["exit_status"] == "error(returncode=7)"


class TestRunRoundReturnValue:
    """Persistent mode: run_round must return submission_status so the
    tournament can log + propagate the round-level outcome."""

    def test_run_round_returns_submission_status(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()

        def router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 0}  # marker exists
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = router
        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            result = agent.run_round(round_num=1, transition_summary=None)

        assert result == "submitted"

    def test_timeout_propagates_to_run_round_return(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()

        def router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            if "codex" in cmd and "exec" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
            return {"output": "deadbeef\n", "returncode": 0}

        agent.environment.execute.side_effect = router
        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            result = agent.run_round(round_num=1, transition_summary=None)

        assert result == "timeout"
        # Timeout flips next-round-fresh flag.
        assert agent._needs_fresh_session is True
