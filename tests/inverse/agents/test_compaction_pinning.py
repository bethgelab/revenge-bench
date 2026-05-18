"""Pinned messages survive _compact_messages (never dropped, never summarized).

Pinning must work in both S1 (summarisation gate) and S3 (global-budget drop).
"""

from unittest.mock import MagicMock
import logging

from minisweagent.models.test_models import DeterministicModel

from revenge_bench.agents.minisweagent import ClashAgent


def _agent(**kwargs):
    env = MagicMock()
    env.execute.return_value = {"output": "ok\n", "returncode": 0}
    env.get_template_vars.return_value = {}
    kwargs.setdefault("keep_recent_observations", 1)
    return ClashAgent(
        model=DeterministicModel(outputs=[]),
        env=env,
        logger=logging.getLogger("t"),
        system_template="SYS",
        instance_template="TASK",
        action_observation_template="<output>{{output.output}}</output>",
        format_error_template="bad",
        timeout_template="timeout",
        step_limit=0,
        cost_limit=10.0,
        **kwargs,
    )


class TestCompactionPinning:
    def test_pinned_message_not_summarized(self):
        agent = _agent()
        agent.add_message("system", "SYS")
        agent.add_message("user", "TASK")
        # Long observation that would normally be compacted
        long_obs = "<output>\n" + ("x" * 5000) + "\n</output>"
        agent.add_message("user", long_obs)
        # Make the pinned message > COMPACT_THRESHOLD so only the pin filter
        # (not the threshold guard) prevents summarization.
        long_pinned = "## Round 1 evaluation complete\n" + "Distance: 0.5\n" * 50
        agent.add_message("user", long_pinned, pinned=True)
        # Add a recent obs to push older ones into the compaction set
        agent.add_message("user", "<output>recent</output>")

        compacted = agent._compact_messages()
        # Pinned message must appear verbatim in compacted output
        pinned_msgs = [m for m in compacted if m["content"].startswith("## Round 1")]
        assert len(pinned_msgs) == 1
        assert pinned_msgs[0]["content"] == long_pinned

    def test_pinned_message_not_dropped_under_context_budget(self):
        agent = _agent(max_context_chars=200)
        agent.add_message("system", "SYS")
        agent.add_message("user", "TASK")
        # Very long old observation that will be dropped
        agent.add_message("user", "<output>" + ("a" * 1000) + "</output>")
        agent.add_message("user", "## Round 1 evaluation complete\nKEEP ME",
                          pinned=True)
        agent.add_message("user", "<output>recent</output>")

        compacted = agent._compact_messages()
        joined = "\n".join(m["content"] for m in compacted)
        assert "KEEP ME" in joined

    def test_pinned_message_not_dropped_when_s3_falls_through_to_recent(self):
        """S3 falls through from to_compact to recent observations under tight budget.

        Pinned messages in the recent-window should still survive that fall-through.
        """
        # Tight budget: forces S3 to drop both summarised and recent obs.
        agent = _agent(max_context_chars=150, keep_recent_observations=1)
        agent.add_message("system", "SYS")
        agent.add_message("user", "TASK")
        # Two old observations that S1 will summarise
        agent.add_message("user", "<output>" + ("a" * 500) + "</output>")
        agent.add_message("user", "<output>" + ("b" * 500) + "</output>")
        # Pinned message in recent-window
        agent.add_message("user", "## Round 2 evaluation complete\nKEEP ME",
                          pinned=True)
        # One more recent observation (so the pinned message isn't the most recent)
        agent.add_message("user", "<output>" + ("c" * 500) + "</output>")

        compacted = agent._compact_messages()
        joined = "\n".join(m["content"] for m in compacted)
        assert "KEEP ME" in joined

    def test_pinned_message_content_not_mutated_by_s3_placeholder(self):
        """When S3 drops messages, the placeholder must not be glued onto a pinned msg."""
        agent = _agent(max_context_chars=200)
        agent.add_message("system", "SYS")
        agent.add_message("user", "TASK")
        # Long old observation that S3 will drop
        agent.add_message("user", "<output>" + ("a" * 1000) + "</output>")
        # Pinned message — would be the first surviving user message after the drop
        pinned_content = "## Round 1 evaluation complete\nDistance: 0.5"
        agent.add_message("user", pinned_content, pinned=True)
        agent.add_message("user", "<output>recent</output>")

        compacted = agent._compact_messages()
        pinned_msgs = [m for m in compacted if m.get("pinned")]
        assert len(pinned_msgs) == 1
        # The pinned message's content must equal exactly what was added — no prefix.
        assert pinned_msgs[0]["content"] == pinned_content
