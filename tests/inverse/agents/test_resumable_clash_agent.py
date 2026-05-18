"""Tests for ClashAgent lifecycle (start_session / run_until_limit / append_round_transition).

Uses DeterministicModel and a stub environment so no Docker is required.
"""

from unittest.mock import MagicMock

import pytest
from minisweagent.models.test_models import DeterministicModel

from revenge_bench.agents.minisweagent import ClashAgent, ClashAgentConfig


def _make_env():
    env = MagicMock()
    env.execute.return_value = {"output": "ok\n", "returncode": 0}
    env.get_template_vars.return_value = {}
    return env


def _agent(model_outputs, **agent_kwargs):
    """Build a minimal ClashAgent for tests."""
    import logging
    return ClashAgent(
        model=DeterministicModel(outputs=model_outputs),
        env=_make_env(),
        logger=logging.getLogger("test"),
        system_template="SYS",
        instance_template="TASK: {{task}}",
        action_observation_template="<output>{{output.output}}</output>",
        format_error_template="bad",
        timeout_template="timeout",
        step_limit=2,
        cost_limit=10.0,
        **agent_kwargs,
    )


class TestOneShotRun:
    """Baseline: existing agent.run() flow still works after refactor."""

    def test_run_terminates_on_step_limit(self):
        # Two model responses that each issue a benign command, then
        # step_limit=2 trips on the third query.
        outputs = [
            "thinking\n```bash\necho hi\n```",
            "more\n```bash\necho hi\n```",
        ]
        agent = _agent(outputs)
        exit_status, _ = agent.run(task="recover strategy")
        assert exit_status == "LimitsExceeded"
        # System + instance + 2*(assistant + user-observation) = 6 messages
        assert len(agent.messages) == 6
        assert agent.messages[0]["role"] == "system"
        assert agent.messages[1]["role"] == "user"
        assert "TASK: recover strategy" in agent.messages[1]["content"]

    def test_run_preserves_submitted_final_output(self):
        """ClashAgent.run() must preserve Submitted's final output content
        — guard against accidentally suppressing non-empty terminators."""
        outputs = ["done\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```"]
        agent = _agent(outputs)
        agent.env.execute.return_value = {
            "output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\nfinal\n",
            "returncode": 0,
        }
        exit_status, msg = agent.run(task="t")
        assert exit_status == "Submitted"
        assert "final" in msg
        last = agent.messages[-1]
        assert last["role"] == "user"
        assert "final" in last["content"]


class TestStartSession:
    """start_session adds system + instance prompts but does not loop."""

    def test_start_session_renders_prompts(self):
        agent = _agent([])  # no model outputs needed; we won't query
        agent.start_session(task="recover")
        assert len(agent.messages) == 2
        assert agent.messages[0]["role"] == "system"
        assert "SYS" in agent.messages[0]["content"]
        assert agent.messages[1]["role"] == "user"
        assert "TASK: recover" in agent.messages[1]["content"]

    def test_start_session_idempotent(self):
        """Calling start_session twice should not re-add the prompts."""
        agent = _agent([])
        agent.start_session(task="recover")
        agent.start_session(task="recover")
        assert len(agent.messages) == 2


class TestRunUntilLimit:
    """run_until_limit drives self.step() under per-round budget; returns cleanly."""

    def test_runs_until_step_increment_exhausted(self):
        outputs = [
            "thinking\n```bash\necho a\n```",
            "thinking\n```bash\necho b\n```",
            "thinking\n```bash\necho c\n```",
        ]
        agent = _agent(outputs)
        agent.start_session(task="t")
        # Per-round budget of 2 steps
        exit_status = agent.run_until_limit(step_increment=2, cost_increment=10.0)
        assert exit_status == "LimitsExceeded"
        # sys + instance + 2*(assistant + observation) = 6
        assert len(agent.messages) == 6

    def test_resumable_across_two_rounds(self):
        """Calling run_until_limit twice extends the budget and preserves messages."""
        outputs = [
            "r1a\n```bash\necho 1\n```",
            "r1b\n```bash\necho 2\n```",
            "r2a\n```bash\necho 3\n```",
            "r2b\n```bash\necho 4\n```",
        ]
        agent = _agent(outputs)
        agent.start_session(task="t")
        agent.run_until_limit(step_increment=2, cost_increment=10.0)
        n_after_r1 = len(agent.messages)
        agent.run_until_limit(step_increment=2, cost_increment=10.0)
        n_after_r2 = len(agent.messages)
        assert n_after_r2 > n_after_r1
        # Original system + instance prompts are still at index 0/1
        assert agent.messages[0]["role"] == "system"
        assert agent.messages[1]["role"] == "user"

    def test_returns_submitted_on_finish_sentinel(self):
        """If the agent emits the submit sentinel, run_until_limit returns 'Submitted'."""
        # First action submits.
        outputs = ["done\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```"]
        agent = _agent(outputs)
        # Make the env return the sentinel as the first line of output.
        agent.env.execute.return_value = {
            "output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\nfinal\n",
            "returncode": 0,
        }
        agent.start_session(task="t")
        exit_status = agent.run_until_limit(step_increment=5, cost_increment=10.0)
        assert exit_status == "Submitted"

    def test_no_empty_user_appended_on_limits_exceeded(self):
        """Empty-string TerminatingException must not produce an empty user message."""
        outputs = [
            "thinking\n```bash\necho a\n```",
            "thinking\n```bash\necho b\n```",
        ]
        agent = _agent(outputs)
        agent.start_session(task="t")
        exit_status = agent.run_until_limit(step_increment=2, cost_increment=10.0)
        assert exit_status == "LimitsExceeded"
        # Last message must be a non-empty user observation, not an empty terminator.
        last = agent.messages[-1]
        assert last["role"] == "user"
        assert last["content"].strip() != ""
        # Pre-fix had 7 messages (sys + instance + 2*(asst+obs) + empty user); post-fix has 6.
        assert len(agent.messages) == 6

    def test_submitted_still_appends_final_output(self):
        """Submitted carries the final output and must still be added as a user message."""
        outputs = ["done\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```"]
        agent = _agent(outputs)
        agent.env.execute.return_value = {
            "output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\nfinal\n",
            "returncode": 0,
        }
        agent.start_session(task="t")
        exit_status = agent.run_until_limit(step_increment=5, cost_increment=10.0)
        assert exit_status == "Submitted"
        last = agent.messages[-1]
        assert last["role"] == "user"
        assert "final" in last["content"]


class TestAppendRoundTransition:
    def test_merges_into_trailing_user_message(self):
        """When the last message is a user observation, the transition is appended
        to that message and the result is pinned. No new message is added."""
        agent = _agent([])
        agent.start_session(task="t")
        # Simulate end-of-round-1 state: a trailing user observation.
        agent.add_message("user", "<output>obs-end-of-round-1</output>")
        n_before = len(agent.messages)

        agent.append_round_transition(
            round_num=2,
            summary={"distance": 0.23, "previous_distance": 0.31,
                     "mismatches": 47, "submission_status": "ok"},
        )

        # No new message added — merged into the trailing user.
        assert len(agent.messages) == n_before
        last = agent.messages[-1]
        assert last["role"] == "user"
        assert last.get("pinned") is True
        # Original observation content is preserved.
        assert "obs-end-of-round-1" in last["content"]
        # Transition content is appended.
        assert "Round 1 evaluation complete" in last["content"]
        assert "0.2300" in last["content"]

    def test_appends_new_pinned_user_when_trailing_is_assistant(self):
        """If the last message is assistant (defensive: shouldn't happen in normal
        flow but possible if a custom caller is appending), add a fresh pinned user."""
        agent = _agent([])
        agent.start_session(task="t")
        agent.add_message("assistant", "thought\n```bash\necho hi\n```")
        n_before = len(agent.messages)

        agent.append_round_transition(
            round_num=2,
            summary={"distance": 0.1, "previous_distance": 0.2,
                     "mismatches": 0, "submission_status": "ok"},
        )

        assert len(agent.messages) == n_before + 1
        last = agent.messages[-1]
        assert last["role"] == "user"
        assert last.get("pinned") is True
        assert "Round 1 evaluation complete" in last["content"]

    def test_no_consecutive_user_after_full_round_cycle(self):
        """End-to-end: run a round to LimitsExceeded, then call append_round_transition.
        self.messages must contain no user→user adjacency."""
        outputs = [
            "thinking\n```bash\necho a\n```",
            "thinking\n```bash\necho b\n```",
        ]
        agent = _agent(outputs)
        agent.start_session(task="t")
        agent.run_until_limit(step_increment=2, cost_increment=10.0)
        agent.append_round_transition(
            round_num=2,
            summary={"distance": 0.5, "previous_distance": 0.6,
                     "mismatches": 0, "submission_status": "ok"},
        )
        roles = [m["role"] for m in agent.messages]
        for i in range(1, len(roles)):
            assert roles[i] != roles[i - 1] or roles[i] == "system", (
                f"consecutive {roles[i]} at indices {i-1},{i}"
            )


class TestFinalizeSession:
    def test_finalize_returns_summary_dict(self):
        agent = _agent([])
        agent.start_session(task="t")
        summary = agent.finalize_session()
        assert summary["api_calls"] == 0
        assert summary["cost"] == 0
        assert "messages" in summary
        assert summary["messages"] == agent.messages
