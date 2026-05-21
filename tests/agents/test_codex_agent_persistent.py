"""Persistent-mode lifecycle tests for CodexInverseStrategyAgent.

Covers:
- `init_session` idempotency + auth-file copy gating,
- round 1 starts fresh, round 2+ uses `codex exec resume --last`,
- wall-clock timeout flips the next round back to fresh (don't resume a
  half-finished turn),
- `run_round` -> `save_round_trajectory` handoff via captured state,
- `transition_summary` rendering for the resume continuation prompt.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revenge_bench.agents.codex_agent import (
    CODEX_HOME_PATH,
    CodexInverseStrategyAgent,
    render_transition_summary,
)
from revenge_bench.agents.utils import GameContext


def _make_agent(tmp_path: Path, **codex_overrides) -> CodexInverseStrategyAgent:
    env = MagicMock()
    env.execute.return_value = {"output": "deadbeef\n", "returncode": 0}

    log_local = tmp_path / "logs"
    log_local.mkdir()

    codex_block = {
        "command": "codex",
        "model": "gpt-5-mini",
        "sandbox": "workspace-write",
        "max_round_seconds": 60,
        "auth_file": None,  # hermetic: skip host auth.json
    }
    codex_block.update(codex_overrides)

    config = {
        "name": "learner",
        "agent": "inverse_codex",
        "config": {
            "codex": codex_block,
            "agent": {
                "system_template": "SYS round {{round}}",
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
        rounds=3,
        working_dir="/workspace",
        context_mode="persistent",
    )
    return CodexInverseStrategyAgent(config, environment=env, game_context=game_context)


def _executions(env: MagicMock) -> list[str]:
    return [c.args[0] for c in env.execute.call_args_list if c.args]


def _codex_calls(env: MagicMock) -> list[str]:
    return [c for c in _executions(env) if "codex" in c and "exec" in c]


class TestInitSession:
    def test_idempotent(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()
        first_call_count = agent.environment.execute.call_count
        agent.init_session()
        # second call must not re-issue mkdir / cat / etc.
        assert agent.environment.execute.call_count == first_call_count

    def test_session_init_required_before_run_round(self, tmp_path):
        agent = _make_agent(tmp_path)
        with pytest.raises(RuntimeError, match="init_session"):
            agent.run_round(round_num=1, transition_summary=None)

    def test_auth_file_explicit_path_copied(self, tmp_path):
        host_auth = tmp_path / "host_auth.json"
        host_auth.write_text('{"token": "test"}')
        agent = _make_agent(tmp_path, auth_file=str(host_auth))
        with patch("revenge_bench.agents.codex_agent.copy_to_container") as mock_copy:
            agent.init_session()
        # Only the auth copy should land here (no trajectory yet).
        mock_copy.assert_called_once()
        args = mock_copy.call_args.args
        assert args[1] == host_auth
        assert args[2] == f"{CODEX_HOME_PATH}/auth.json"

    def test_auth_file_missing_explicit_raises(self, tmp_path):
        missing = tmp_path / "definitely_does_not_exist.json"
        agent = _make_agent(tmp_path, auth_file=str(missing))
        with pytest.raises(FileNotFoundError, match="auth_file"):
            agent.init_session()

    def test_auth_file_null_skips_copy(self, tmp_path):
        agent = _make_agent(tmp_path, auth_file=None)
        with patch("revenge_bench.agents.codex_agent.copy_to_container") as mock_copy:
            agent.init_session()
        mock_copy.assert_not_called()


class TestRoundProgression:
    def test_round_1_uses_fresh_invocation(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()
        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run_round(round_num=1, transition_summary=None)
            agent.save_round_trajectory(round_num=1, exit_status="submitted")

        codex_calls = _codex_calls(agent.environment)
        assert len(codex_calls) == 1
        # Fresh codex exec — no `resume --last`
        assert "resume --last" not in codex_calls[0]

    def test_round_2_uses_resume_last(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()
        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            # Round 1
            agent.run_round(round_num=1, transition_summary=None)
            agent.save_round_trajectory(round_num=1, exit_status="submitted")
            # Round 2 with a transition summary
            agent.game_context.round = 2
            transition = {
                "distance": 0.4,
                "previous_distance": 0.6,
                "mismatches": 25,
                "submission_status": "submitted",
                "total_rounds": 3,
                "step_increment": 0,
            }
            agent.run_round(round_num=2, transition_summary=transition)
            agent.save_round_trajectory(round_num=2, exit_status="submitted")

        codex_calls = _codex_calls(agent.environment)
        assert len(codex_calls) == 2
        assert "resume --last" not in codex_calls[0]
        assert "resume --last" in codex_calls[1]

    def test_round_2_requires_transition_summary(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()
        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run_round(round_num=1, transition_summary=None)
            agent.save_round_trajectory(round_num=1, exit_status="submitted")
            with pytest.raises(ValueError, match="transition_summary"):
                agent.run_round(round_num=2, transition_summary=None)

    def test_save_round_trajectory_requires_matching_run_round(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()
        with pytest.raises(RuntimeError, match="save_round_trajectory"):
            agent.save_round_trajectory(round_num=1, exit_status="submitted")


class TestTimeoutResetsSession:
    def test_round_1_timeout_flips_round_2_to_fresh(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.init_session()

        # Make the codex exec call raise TimeoutExpired exactly once.
        execute_calls = {"i": 0}

        def execute_router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            if "codex" in cmd and "exec" in cmd:
                execute_calls["i"] += 1
                if execute_calls["i"] == 1:
                    raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
                return {"output": "", "returncode": 0}
            return {"output": "deadbeef\n", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            # Round 1 timed out
            exit1 = agent.run_round(round_num=1, transition_summary=None)
            assert exit1 == "timeout"
            agent.save_round_trajectory(round_num=1, exit_status=exit1)
            stats1 = agent.get_metadata()["agent_stats"][1]
            assert stats1["exit_status"] == "timeout"

            # Round 2 must NOT use resume --last because round 1 timed out
            agent.game_context.round = 2
            transition = {
                "distance": None, "previous_distance": None,
                "mismatches": 0, "submission_status": "timeout",
                "total_rounds": 3, "step_increment": 0,
            }
            agent.run_round(round_num=2, transition_summary=transition)
            agent.save_round_trajectory(round_num=2, exit_status="submitted")

        codex_calls = _codex_calls(agent.environment)
        assert len(codex_calls) == 2
        # Both invocations should be fresh (no resume) because of timeout reset
        assert "resume --last" not in codex_calls[0]
        assert "resume --last" not in codex_calls[1]

        traj_path = tmp_path / "logs" / "players" / "learner" / "learner_r2.traj.json"
        traj = json.loads(traj_path.read_text())
        assert traj["resume_mode"] == "fresh"


class TestTransitionSummaryRendering:
    def test_renders_distance_and_delta(self):
        text = render_transition_summary(
            round_num=2,
            summary={
                "distance": 0.4,
                "previous_distance": 0.6,
                "mismatches": 25,
                "submission_status": "submitted",
                "total_rounds": 3,
            },
        )
        assert "Round 1 evaluation complete" in text
        assert "0.4000" in text
        assert "improved" in text  # distance went down
        assert "Mismatches: 25" in text
        assert "Now starting round 2 of 3" in text

    def test_handles_failed_evaluation(self):
        text = render_transition_summary(
            round_num=2,
            summary={
                "distance": None,
                "previous_distance": 0.6,
                "mismatches": None,
                "submission_status": "error",
                "total_rounds": 3,
            },
        )
        assert "evaluation failed" in text
        assert "Mismatches" not in text  # None mismatches dropped
