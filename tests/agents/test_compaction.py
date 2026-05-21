# tests/agents/test_compaction.py
"""Comprehensive test of all compaction scenarios in _compact_messages().

Pipeline stages:
  S0: keep_recent_observations=None  → no compaction at all
  S1: keep_recent_observations=k     → smart _summarize_observation on old turns
  S2: max_past_output_chars          → safety-net truncation on summarized text
  S3: max_context_chars              → global budget, drop entire old turns
                                       (never touches keep_recent window)

Tests every combination to verify they compose without conflict.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from revenge_bench.agents.minisweagent import ClashAgent, ClashAgentConfig

logger = logging.getLogger("test_compaction")

# ── Trajectory discovery ────────────────────────────────────────────

_PREFERRED = [
    Path("logs/compaction_experiments/gemma_4_26b_a4b_smoketest_low_compact_20260428_234606/"
         "halite/target7b3c5fdd7395/players/learner/learner_r1.traj.json"),
    Path("logs/compaction_experiments/gemma_4_26b_a4b_smoketest_keep10_20260429_035719/"
         "halite/target7b3c5fdd7395/players/learner/learner_r1.traj.json"),
]


def _has_clean_role_alternation(path: Path) -> bool:
    """True iff the trajectory has no consecutive non-system same-role messages."""
    try:
        msgs = json.loads(path.read_text())["messages"]
    except (json.JSONDecodeError, KeyError, OSError):
        return False
    for i in range(1, len(msgs)):
        if msgs[i]["role"] == msgs[i - 1]["role"] and msgs[i]["role"] != "system":
            return False
    return True


def _find_trajectories() -> list[Path]:
    paths = [p for p in _PREFERRED if p.exists()]
    if paths:
        return paths
    # Fallback: scan logs/ for trajectories with clean alternation.
    # Old trajectories from before the consecutive-user fix would trip the
    # _compact_messages assertion and produce spurious test failures.
    candidates = sorted(Path("logs").rglob("*.traj.json"))
    return [p for p in candidates if _has_clean_role_alternation(p)][:2]


TRAJ_PATHS = _find_trajectories()


def _load_messages(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)["messages"]


# ── Helpers ─────────────────────────────────────────────────────────


def _make_agent(messages, *, keep_recent=None, max_past=None, max_ctx=None):
    config = ClashAgentConfig(
        system_template="",
        instance_template="",
        keep_recent_observations=keep_recent,
        max_past_output_chars=max_past,
        max_context_chars=max_ctx,
    )
    agent = ClashAgent.__new__(ClashAgent)
    agent.config = config
    agent.messages = list(messages)
    agent.logger = logger
    agent.COMPACT_THRESHOLD = 500
    return agent


def _validate(messages_orig, result, *, expect_identity=False):
    """Run structural assertions on a compaction result."""
    roles = [m["role"] for m in result]
    n_placeholder = sum(1 for m in result if "earlier turns omitted" in m["content"])

    # System prompt always first
    assert result[0]["role"] == "system"
    assert result[0]["content"] == messages_orig[0]["content"]

    # Instance prompt always second
    assert result[1]["role"] == "user"
    inst_content = result[1]["content"]
    if "earlier turns omitted" in inst_content:
        assert inst_content.endswith(messages_orig[1]["content"])
    else:
        assert inst_content == messages_orig[1]["content"]

    # At most 1 placeholder
    assert n_placeholder <= 1

    # Compaction must not INTRODUCE consecutive same-role via placeholder
    for j in range(1, len(roles)):
        if roles[j] == roles[j - 1] and not expect_identity:
            if ("earlier turns omitted" in result[j]["content"] or
                    "earlier turns omitted" in result[j - 1]["content"]):
                pytest.fail(
                    f"compaction introduced consecutive {roles[j]} at {j-1},{j}"
                )

    orig_chars = sum(len(m["content"]) for m in messages_orig)
    res_chars = sum(len(m["content"]) for m in result)
    assert res_chars <= orig_chars + 200

    if expect_identity:
        assert len(result) == len(messages_orig)
        assert abs(res_chars - orig_chars) < 200

    return res_chars


# ── Skip guard ──────────────────────────────────────────────────────

needs_trajectories = pytest.mark.skipif(
    not TRAJ_PATHS,
    reason="No trajectory files found under logs/",
)


# ── Tests ───────────────────────────────────────────────────────────


@needs_trajectories
class TestS0NoCompaction:
    """S0: All config flags None → identity."""

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_identity(self, traj_idx):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        agent = _make_agent(messages)
        result = agent._compact_messages()
        _validate(messages, result, expect_identity=True)


@needs_trajectories
class TestS1Summarisation:
    """S1: keep_recent_observations only."""

    @pytest.mark.parametrize("k", [0, 1, 3, 5, 99])
    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_keep_recent(self, traj_idx, k):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        agent = _make_agent(messages, keep_recent=k)
        result = agent._compact_messages()
        _validate(messages, result)


@needs_trajectories
class TestS2PastTruncation:
    """S2: summarisation + max_past_output_chars."""

    @pytest.mark.parametrize("k,past", [(3, 2000), (3, 500), (3, 50), (1, 100), (0, 500)])
    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_past_truncation(self, traj_idx, k, past):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        agent = _make_agent(messages, keep_recent=k, max_past=past)
        result = agent._compact_messages()
        _validate(messages, result)


@needs_trajectories
class TestS3GlobalBudget:
    """S3: summarisation + max_context_chars."""

    @pytest.mark.parametrize("k,ctx_pct", [(3, 200), (3, 80), (3, 50), (3, 20), (3, 10), (1, 30)])
    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_global_budget(self, traj_idx, k, ctx_pct):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        total_chars = sum(len(m["content"]) for m in messages)
        budget = int(total_chars * ctx_pct / 100)
        agent = _make_agent(messages, keep_recent=k, max_ctx=budget)
        result = agent._compact_messages()
        _validate(messages, result)


@needs_trajectories
class TestFullPipeline:
    """All three knobs together."""

    @pytest.mark.parametrize("k,past,ctx_pct", [
        (3, 2000, 80), (3, 2000, 50), (3, 500, 30),
        (1, 100, 20), (5, 2000, 80), (0, 500, 40), (3, 50, 10),
    ])
    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_full(self, traj_idx, k, past, ctx_pct):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        total_chars = sum(len(m["content"]) for m in messages)
        budget = int(total_chars * ctx_pct / 100)
        agent = _make_agent(messages, keep_recent=k, max_past=past, max_ctx=budget)
        result = agent._compact_messages()
        _validate(messages, result)


@needs_trajectories
class TestEdgeCases:
    """Edge-case combinations."""

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_k_none_with_max_ctx(self, traj_idx):
        """keep_recent=None + max_ctx set."""
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        total_chars = sum(len(m["content"]) for m in messages)
        agent = _make_agent(messages, max_ctx=int(total_chars * 0.5))
        result = agent._compact_messages()
        _validate(messages, result)

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_k_none_with_max_past(self, traj_idx):
        """keep_recent=None + max_past → identity."""
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        agent = _make_agent(messages, max_past=500)
        result = agent._compact_messages()
        _validate(messages, result, expect_identity=True)

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_s3_respects_recent_window(self, traj_idx):
        """S3 with a tiny budget must NOT drop recent-k observations."""
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        sys_chars = len(messages[0]["content"]) + len(messages[1]["content"])
        tiny_budget = sys_chars + 2000
        agent = _make_agent(messages, keep_recent=3, max_past=500, max_ctx=tiny_budget)
        result = agent._compact_messages()
        _validate(messages, result)

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_window_observations_preserved_verbatim(self, traj_idx):
        """Every observation in the recent-k window must survive intact
        even when S3 budget is violated."""
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        obs_indices = [i for i, m in enumerate(messages) if m["role"] == "user" and i > 1]
        if len(obs_indices) < 3:
            pytest.skip("Not enough observations for k=3 window test")

        k_test = 3
        window_obs = obs_indices[-k_test:]
        sys_chars = len(messages[0]["content"]) + len(messages[1]["content"])
        tiny_budget = sys_chars + 2000

        agent = _make_agent(messages, keep_recent=k_test, max_past=500, max_ctx=tiny_budget)
        result = agent._compact_messages()

        result_contents = {m["content"] for m in result if m["role"] == "user"}
        for wi in window_obs:
            orig_content = messages[wi]["content"]
            assert any(orig_content in rc for rc in result_contents), (
                f"recent-window observation at index {wi} "
                f"({len(orig_content)} chars) was dropped or mutated by S3"
            )


@needs_trajectories
class TestShortTrajectory:
    """Edge cases with only the first 4 messages."""

    @pytest.mark.parametrize("kr,mp,mc_frac", [
        (None, None, None),
        (1, None, None),
        (1, None, 0.5),
        (3, None, None),
        (0, 100, None),
        (1, 500, 0.5),
    ])
    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_short(self, traj_idx, kr, mp, mc_frac):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        if len(messages) < 4:
            pytest.skip("Trajectory too short")
        short_msgs = messages[:4]
        short_chars = sum(len(m["content"]) for m in short_msgs)
        mc = int(short_chars * mc_frac) if mc_frac is not None else None
        agent = _make_agent(short_msgs, keep_recent=kr, max_past=mp, max_ctx=mc)
        result = agent._compact_messages()
        _validate(short_msgs, result)


@needs_trajectories
class TestMonotonicity:
    """Tighter settings must never increase total chars."""

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_k3_chain(self, traj_idx):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        total = sum(len(m["content"]) for m in messages)
        chain = [
            dict(keep_recent=3, max_past=None, max_ctx=None),
            dict(keep_recent=3, max_past=2000, max_ctx=None),
            dict(keep_recent=3, max_past=500, max_ctx=None),
            dict(keep_recent=3, max_past=50, max_ctx=None),
            dict(keep_recent=3, max_past=50, max_ctx=int(total * 0.8)),
            dict(keep_recent=3, max_past=50, max_ctx=int(total * 0.5)),
            dict(keep_recent=3, max_past=50, max_ctx=int(total * 0.2)),
        ]
        self._check_chain(messages, chain)

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_k1_chain(self, traj_idx):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        total = sum(len(m["content"]) for m in messages)
        chain = [
            dict(keep_recent=1, max_past=None, max_ctx=None),
            dict(keep_recent=1, max_past=500, max_ctx=None),
            dict(keep_recent=1, max_past=100, max_ctx=None),
            dict(keep_recent=1, max_past=100, max_ctx=int(total * 0.5)),
            dict(keep_recent=1, max_past=100, max_ctx=int(total * 0.2)),
        ]
        self._check_chain(messages, chain)

    @pytest.mark.parametrize("traj_idx", range(len(TRAJ_PATHS)))
    def test_raw_to_ctx(self, traj_idx):
        messages = _load_messages(TRAJ_PATHS[traj_idx])
        total = sum(len(m["content"]) for m in messages)
        chain = [
            dict(keep_recent=None, max_past=None, max_ctx=None),
            dict(keep_recent=3, max_past=None, max_ctx=None),
            dict(keep_recent=3, max_past=None, max_ctx=int(total * 0.5)),
            dict(keep_recent=3, max_past=None, max_ctx=int(total * 0.2)),
        ]
        self._check_chain(messages, chain)

    @staticmethod
    def _check_chain(messages, chain):
        sizes = []
        for kw in chain:
            agent = _make_agent(messages, **kw)
            result = agent._compact_messages()
            sizes.append(sum(len(m["content"]) for m in result))
        for i in range(1, len(sizes)):
            assert sizes[i] <= sizes[i - 1], (
                f"Step {i} ({sizes[i]:,}) > step {i-1} ({sizes[i-1]:,})"
            )


class TestAlternatingRoleGuard:
    """The structural check that runs before every model query."""

    def test_synthetic_user_user_is_caught(self):
        """Consecutive non-system same-role pairs in messages-for-model must raise."""
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "I"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "obs1"},
            {"role": "user", "content": "obs2"},  # ← bad: consecutive user
        ]
        with pytest.raises(RuntimeError, match="consecutive user"):
            ClashAgent._assert_alternating_roles(messages)

    def test_clean_alternation_passes(self):
        """A well-formed alternating sequence should not raise."""
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "I"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "obs1"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "obs2"},
        ]
        ClashAgent._assert_alternating_roles(messages)  # must not raise

    def test_consecutive_assistant_caught(self):
        """assistant→assistant adjacency is also caught."""
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "I"},
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
        ]
        with pytest.raises(RuntimeError, match="consecutive assistant"):
            ClashAgent._assert_alternating_roles(messages)
