"""Integration test for the Harbor agent bridge (``HarborRevengeAgent``).

Exercises ``HarborRevengeAgent.run()`` end to end against a *fake* async Harbor
environment and a deterministic model — no container and no LLM. Verifies:

- the bridge does not manage the task-owned probe budget,
- agent-issued commands run as the unprivileged ``agent`` user,
- submission is detected and a trajectory is saved,
- cost stats are captured for ``populate_context_post_run``.

Skipped unless both ``harbor`` and ``minisweagent`` are importable (Harbor
requires Python >=3.12, so this is skipped in the 3.11 dev venv).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import pytest

# NB: guard on a real framework submodule, not bare "harbor" — the repo's
# top-level harbor/ directory is an implicit namespace package that would
# otherwise satisfy importorskip("harbor") and give a false positive.
pytest.importorskip("harbor.agents.base")
pytest.importorskip("minisweagent")


@dataclass
class _ExecResult:
    stdout: str | None
    stderr: str | None
    return_code: int


class _FakeEnv:
    """Minimal async stand-in for ``harbor.environments.base.BaseEnvironment``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        self.calls.append((command, user))
        return _ExecResult(stdout=f"[user={user}] {command}", stderr="", return_code=0)


def test_harbor_revenge_agent_run(tmp_path, monkeypatch):
    import minisweagent.models as mmodels
    from minisweagent.models.test_models import DeterministicModel

    from harbor.models.agent.context import AgentContext
    from revenge_bench.harbor.agent import HarborRevengeAgent

    outputs = [
        "THOUGHT: look around.\n\n```bash\nls /workspace\n```",
        'THOUGHT: done.\n\n```bash\necho "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"\n```',
    ]
    monkeypatch.setattr(
        mmodels, "get_model", lambda *a, **k: DeterministicModel(outputs=outputs)
    )

    agent = HarborRevengeAgent(
        logs_dir=tmp_path,
        model_name="deterministic/test",
        max_probes=7,  # deprecated compatibility kwarg; task image owns budget.
        step_limit=5,
    )
    env = _FakeEnv()
    ctx = AgentContext()

    asyncio.run(agent.run("Solve the BattleSnake inverse task.", env, ctx))

    # Probe budget belongs to the task image/run_probe, not this bridge.
    budget_calls = [(c, u) for c, u in env.calls if ".probe_budget" in c]
    assert budget_calls == []

    # Agent-issued commands ran as the unprivileged 'agent' user.
    agent_cmds = [
        (c, u) for c, u in env.calls if "ls /workspace" in c or "COMPLETE_TASK" in c
    ]
    assert agent_cmds
    assert all(u == "agent" for _, u in agent_cmds)

    # Cost stats captured; trajectory saved.
    assert "cost_usd" in agent._last_stats
    agent.populate_context_post_run(ctx)
    assert (tmp_path / "revenge_bench.traj.json").exists()


def test_harbor_revenge_agent_passes_bounded_model_config(tmp_path, monkeypatch):
    import minisweagent.models as mmodels
    from minisweagent.models.test_models import DeterministicModel

    from harbor.models.agent.context import AgentContext
    from revenge_bench.harbor.agent import HarborRevengeAgent

    captured = {}

    def fake_get_model(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DeterministicModel(
            outputs=[
                'THOUGHT: done.\n\n```bash\necho "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"\n```'
            ]
        )

    monkeypatch.setattr(mmodels, "get_model", fake_get_model)
    monkeypatch.setenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", "9")

    agent = HarborRevengeAgent(
        logs_dir=tmp_path,
        model_name="deterministic/test",
        step_limit=5,
        model_timeout_sec=42,
        model_retry_attempts=2,
        reasoning_effort="low",
    )

    asyncio.run(agent.run("Solve the task.", _FakeEnv(), AgentContext()))

    model_kwargs = captured["kwargs"]["config"]["model_kwargs"]
    assert model_kwargs["timeout"] == 42
    assert model_kwargs["request_timeout"] == 42
    assert model_kwargs["reasoning_effort"] == "low"
    assert captured["args"] == ("deterministic/test",)
    assert os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] == "9"


def test_harbor_revenge_agent_is_baseagent_subclass():
    from harbor.agents.base import BaseAgent

    from revenge_bench.harbor.agent import HarborRevengeAgent

    assert issubclass(HarborRevengeAgent, BaseAgent)
    assert HarborRevengeAgent.name() == "revenge-bench"
