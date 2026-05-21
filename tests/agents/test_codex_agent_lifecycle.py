"""Reset-mode lifecycle tests for CodexInverseStrategyAgent.

Mocks the container environment so `run()` can be exercised without
actually launching `codex exec`. Verifies:
- prompt is rendered + staged in the container,
- argv passed to `execute(...)` looks like a codex exec command,
- trajectory file and metadata are written with the Codex schema,
- submission marker presence flips submission_status to "submitted",
- post_run_hook (git commit) still runs unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revenge_bench.agents.codex_agent import (
    CODEX_HOME_PATH,
    SUBMIT_MARKER_PATH,
    CodexInverseStrategyAgent,
)
from revenge_bench.agents.utils import GameContext


def _make_agent(tmp_path: Path) -> CodexInverseStrategyAgent:
    env = MagicMock()
    # Default container exec: success with a stub commit hash so that
    # Player.__init__ -> _get_commit_hash() doesn't choke on empty output.
    # Specific tests override .execute.side_effect to inject responses
    # for the marker check / cat last_message.
    env.execute.return_value = {"output": "deadbeef\n", "returncode": 0}

    log_local = tmp_path / "logs"
    log_local.mkdir()

    config = {
        "name": "learner",
        "agent": "inverse_codex",
        "config": {
            "codex": {
                "command": "codex",
                "model": "gpt-5-mini",
                "sandbox": "workspace-write",
                "max_round_seconds": 300,
                # Disable auth-file copy in unit tests so they don't read
                # the developer's real ~/.codex/auth.json.
                "auth_file": None,
                "config_overrides": {"model_reasoning_effort": "low"},
            },
            "agent": {
                "system_template": "SYS for {{player_id}}",
                "instance_template": "INSTANCE round {{round}}",
            },
        },
    }
    game_context = GameContext(
        id="g",
        log_env=Path("/logs"),
        log_local=log_local,
        name="Test",
        player_id="learner",
        prompts={},
        round=1,
        rounds=2,
        working_dir="/workspace",
        context_mode="reset",
    )
    # Player.__init__ runs `git rev-parse HEAD` via env.execute on first
    # use; the default mock answer above keeps it happy.
    return CodexInverseStrategyAgent(config, environment=env, game_context=game_context)


def _executions(env: MagicMock) -> list[str]:
    """Return the shell strings passed to env.execute across the whole run."""
    out = []
    for call in env.execute.call_args_list:
        if call.args:
            out.append(call.args[0])
        elif "command" in call.kwargs:
            out.append(call.kwargs["command"])
    return out


class TestRequiredConfig:
    def test_missing_codex_block_raises(self, tmp_path):
        env = MagicMock()
        env.execute.return_value = {"output": "", "returncode": 0}
        log_local = tmp_path / "logs"
        log_local.mkdir()
        config = {"name": "learner", "agent": "inverse_codex", "config": {}}
        gc = GameContext(
            id="g",
            log_env=Path("/logs"),
            log_local=log_local,
            name="T",
            player_id="learner",
            prompts={},
            round=1,
            rounds=1,
            working_dir="/workspace",
        )
        with pytest.raises(ValueError, match="config.codex"):
            CodexInverseStrategyAgent(config, environment=env, game_context=gc)


class TestResetModeRun:
    def test_run_invokes_codex_exec_and_writes_trajectory(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path)
        # Pretend the marker file does NOT exist (returncode=1 from `test -f`)
        # and the last_message cat returns nothing.
        # Default mock returncode is 0 — we need to special-case the marker test.
        def execute_router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container") as mock_create, \
             patch("revenge_bench.agents.codex_agent.copy_to_container") as mock_copy:
            agent.run()

        # Prompt was staged in container outside /workspace.
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["dest_path"].startswith("/codex_home/")
        rendered = kwargs["content"]
        assert "SYS for learner" in rendered
        assert "INSTANCE round 1" in rendered

        # `codex exec` was invoked with CODEX_HOME exported.
        execs = _executions(agent.environment)
        codex_calls = [c for c in execs if "codex" in c and "exec" in c]
        assert len(codex_calls) == 1
        cmd_line = codex_calls[0]
        assert "CODEX_HOME=" in cmd_line
        assert "/codex_home" in cmd_line
        assert "--cd /workspace" in cmd_line
        assert "--sandbox workspace-write" in cmd_line
        assert "--model gpt-5-mini" in cmd_line

        # Trajectory file written with Codex schema.
        traj_path = tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json"
        assert traj_path.exists()
        traj = json.loads(traj_path.read_text())
        assert traj["backend"] == "codex"
        assert traj["round"] == 1
        assert traj["resume_mode"] == "fresh"
        assert traj["submission_status"] == "exited_without_submit"
        assert traj["exit_status"] == "ok"
        assert traj["model"] == "gpt-5-mini"

        # agent_stats has explicit nulls for cost / api_calls.
        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["cost"] is None
        assert stats["api_calls"] is None
        assert stats["submission_status"] == "exited_without_submit"
        assert stats["probe_count"] == 0

        # Trajectory was copied back to log_env via copy_to_container.
        mock_copy.assert_called_once()

    def test_submit_marker_present_marks_submitted(self, tmp_path):
        agent = _make_agent(tmp_path)

        def execute_router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 0}  # marker exists
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run()

        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["submission_status"] == "submitted"

    def test_codex_home_outside_workspace(self, tmp_path):
        """Regression: CODEX_HOME must NOT be under /workspace, otherwise
        Player._commit() (`git add -A`) would stage Codex caches."""
        assert not CODEX_HOME_PATH.startswith("/workspace")
        # Submit marker is fine under /workspace/.revenge_bench because
        # tournaments either gitignore it or it's a transient file.
        assert SUBMIT_MARKER_PATH.startswith("/workspace/")
