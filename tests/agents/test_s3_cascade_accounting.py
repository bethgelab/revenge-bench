"""Regression test for the S3 cascade-accounting bug.

When S3 drops a user observation, the rebuild also drops the assistant
that responded to it. The drop loop must account for the cascaded
assistant size in its budget arithmetic — otherwise it under-estimates
how much each drop frees and over-drops every droppable turn.
"""

import logging
from unittest.mock import MagicMock

from minisweagent.models.test_models import DeterministicModel

from revenge_bench.agents.minisweagent import ClashAgent


def _make_agent(**kwargs):
    env = MagicMock()
    env.execute.return_value = {"output": "ok\n", "returncode": 0}
    env.get_template_vars.return_value = {}
    return ClashAgent(
        model=DeterministicModel(outputs=[]),
        env=env,
        logger=logging.getLogger("t"),
        system_template="x",
        instance_template="x",
        action_observation_template="x",
        format_error_template="x",
        timeout_template="x",
        step_limit=0,
        cost_limit=10.0,
        **kwargs,
    )


class TestS3CascadeAccounting:
    """S3's drop loop must count the cascaded assistant size, not just user-obs."""

    def test_drops_minimum_needed_when_cascade_is_large(self):
        """Setup: one drop+cascade should free enough chars; the loop must stop there.

        Pre-fix behaviour: loop only subtracts user-obs (~104 chars) per drop,
        so it never sees `total <= max_ctx` until ALL outside-window user-obs
        are dropped. Post-fix: subtracts user-obs + cascaded assistant
        (~104 + 700 = ~804) per drop, stops at the right moment.

        We verify the fix by counting how many outside-window user-obs
        (the ones with the "obs" prefix) survive — pre-fix all are dropped,
        post-fix at least 2 survive.
        """
        agent = _make_agent(
            keep_recent_observations=2,
            max_context_chars=4000,
            # COMPACT_THRESHOLD is 500; keep user-obs below it so S1
            # doesn't summarise (we want S3 alone to be exercised).
        )
        # Build messages totalling > max_ctx so S3 fires.
        # Sizes:
        #   system     100
        #   instance   100
        #   4 outside-window pairs:
        #     user-obs  104 each ("obs<i>" + "x"*100, length 104)
        #     assistant 700 each ("thought" * 100)
        #   2 recent pairs (k=2):
        #     user-obs  ~108 each ("recent<i>" + "x"*100)
        #     assistant 700 each ("recent_thought" * 50, length 700)
        # Total: 100 + 100 + 4*(104+700) + 2*(108+700) = 5032 chars.
        # Loop must free at least 5032 - 4000 = 1032 chars. With the
        # post-fix cascade accounting, ONE drop+cascade frees ~804 chars,
        # TWO frees ~1608. So the loop should drop exactly 2 outside-window
        # pairs, leaving 2 intact.
        agent.add_message("system", "S" * 100)
        agent.add_message("user", "I" * 100)  # instance prompt
        for i in range(4):
            agent.add_message("user", f"obs{i}" + "x" * 100)
            agent.add_message("assistant", "thought" * 100)
        for i in range(2):
            # NOTE: recent-window assistant content uses underscore, NOT
            # hyphen, so a substring filter on "obs" cleanly distinguishes
            # outside-window from recent. Don't change to "recent-thought"
            # — the dash interacts badly with content-prefix scanning.
            agent.add_message("user", f"recent{i}" + "x" * 100)
            agent.add_message("assistant", "recent_thought" * 50)

        original_total = sum(len(m["content"]) for m in agent.messages)
        assert original_total > 4000, "test setup must exceed budget"

        compacted = agent._compact_messages()
        compacted_total = sum(len(m["content"]) for m in compacted)

        # 1) Budget respected (modulo placeholder slack ~30 chars).
        assert compacted_total <= 4100, (
            f"S3 ignored max_context_chars=4000: got {compacted_total}"
        )
        # 1b) Lower-bound: must NOT collapse to bone-set. Post-fix expected
        # ~3450 chars; pre-fix would have been ~1850. The 3000 boundary
        # cleanly distinguishes them.
        assert compacted_total >= 3000, (
            f"S3 over-dropped: got {compacted_total} chars; expected >= 3000 "
            f"(at least two outside-window pairs surviving)."
        )
        # 1c) Drop count via the placeholder's "[N earlier turns omitted]" prefix.
        import re
        placeholder_match = re.search(
            r"\[(\d+) earlier turns omitted\]",
            "\n".join(m["content"] for m in compacted),
        )
        assert placeholder_match is not None, "expected drop-placeholder in compacted output"
        n_dropped = int(placeholder_match.group(1))
        assert n_dropped == 2, (
            f"Loop dropped {n_dropped} turns; expected exactly 2 "
            f"(off-by-one in cascade arithmetic suspected)."
        )
        # 2) Outside-window survivors: post-fix ≥ 2, pre-fix == 0.
        # NOTE: use substring `in`, not `.startswith("obs")` — the rebuild
        # phase prepends "[N earlier turns omitted]\n\n" to the first
        # surviving non-system non-instance user message, so the earliest
        # surviving "obs<i>" message will not start with "obs".
        outside_window_survivors = sum(
            1 for m in compacted
            if m["role"] == "user" and "obs" in m["content"]
        )
        assert outside_window_survivors >= 2, (
            f"S3 over-dropped: only {outside_window_survivors} outside-window "
            f"user-obs survived (expected ≥ 2)."
        )

    def test_loop_does_not_overshoot(self):
        """Even when many drops are needed, the loop should stop the moment
        post-rebuild total falls under the budget — not strip-mine every
        droppable turn."""
        agent = _make_agent(
            keep_recent_observations=1,
            max_context_chars=2000,
        )
        # Sizes:
        #   system   100, instance 100
        #   6 outside-window pairs: user 50 + assistant 550 = 600 each
        #   1 recent: user 50 + assistant 550 = 600
        # Total: 100 + 100 + 6*600 + 600 = 4400.
        # Need to free 4400 - 2000 = 2400 chars.
        # Cascade-aware loop drops 4 pairs (4 * 600 = 2400) to fit.
        # Pre-fix loop would drop all 6 outside-window pairs (over-drop).
        agent.add_message("system", "S" * 100)
        agent.add_message("user", "I" * 100)
        for i in range(6):
            agent.add_message("user", f"obs{i}" + "x" * (50 - len(f"obs{i}")))
            agent.add_message("assistant", "a" * 550)
        agent.add_message("user", "recent" + "x" * 44)
        agent.add_message("assistant", "ra" * 275)

        compacted = agent._compact_messages()

        # Budget respected (placeholder slack ~30 chars).
        compacted_total = sum(len(m["content"]) for m in compacted)
        assert compacted_total <= 2100, (
            f"Budget exceeded: got {compacted_total}"
        )
        # At least 2 outside-window pairs should survive (pre-fix: 0).
        outside_window_survivors = sum(
            1 for m in compacted
            if m["role"] == "user" and "obs" in m["content"]
        )
        assert outside_window_survivors >= 2, (
            f"S3 over-dropped: {outside_window_survivors} outside-window "
            f"user-obs survived (expected ≥ 2)."
        )
