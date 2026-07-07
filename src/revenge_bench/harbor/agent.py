"""Harbor-compatible agent bridge for RevengeBench (Tier I, interactive).

``HarborRevengeAgent`` runs **outside** the task container and drives the sealed
interactive task through Harbor's :meth:`BaseEnvironment.exec`. It adapts the
async Harbor environment to the *synchronous* environment interface expected by
mini-swe-agent's :class:`DefaultAgent`, then runs the standard think→command
edit loop.

Security model (matches the task's single-container Unix-user sealing):
- Agent commands run as the non-root ``agent`` user (UID 1000).
- The target lives at ``/target`` (root:root 0700) and is queried only through
  ``sudo run_probe`` (a normal bash command the agent may issue); scoring is
  performed separately by the task verifier (``tests/test.sh``).

This module imports the Harbor framework at import time, so it is **not** pulled
in by ``import revenge_bench.harbor`` (that package stays dependency-light; see
``revenge_bench/harbor/__init__.py``'s lazy ``__getattr__``).

Load it with Harbor, e.g.::

    harbor run -p harbor/tasks/battlesnake-gpt5-9aa3-v0 \\
        --agent-import-path "harbor_agent:HarborRevengeAgent" \\
        -m openai/gpt-5
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
from harbor.agents.base import BaseAgent

load_dotenv()

if TYPE_CHECKING:  # pragma: no cover - typing only
    from harbor.environments.base import BaseEnvironment
    from harbor.models.agent.context import AgentContext


# ---------------------------------------------------------------------------
# Async Harbor env -> sync mini-swe-agent env adapter (Harbor-generic).
# ---------------------------------------------------------------------------


@dataclass
class _AdapterConfig:
    """Minimal config satisfying mini-swe-agent's ``Environment.config`` protocol."""

    cwd: str = "/workspace"
    timeout: int = 300
    image: str = "harbor-managed"
    env: dict = field(default_factory=dict)
    forward_env: list = field(default_factory=list)


class _HarborEnvAdapter:
    """Wrap Harbor's async ``BaseEnvironment`` as a sync mini-swe-agent env.

    ``DefaultAgent.execute_action`` calls ``self.env.execute(command)`` and
    expects ``{"output": str, "returncode": int}``. Agent commands run as the
    unprivileged ``agent`` user; ``execute_privileged`` runs as root and is used
    only by the bridge itself, never by agent-generated commands.
    """

    def __init__(
        self,
        harbor_env: "BaseEnvironment",
        loop: asyncio.AbstractEventLoop,
        *,
        cwd: str = "/workspace",
        timeout: int = 300,
        max_output_chars: int = 120_000,
    ):
        self.harbor_env = harbor_env
        self._loop = loop
        self.cwd = cwd
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.config = _AdapterConfig(cwd=cwd, timeout=timeout)

    def get_template_vars(self) -> dict[str, Any]:
        """Template variables expected by ``DefaultAgent.render_template``."""
        return asdict(self.config)

    def _exec_env(self, user: str) -> dict[str, str]:
        if user == "root":
            return {"HOME": "/root"}
        return {
            "HOME": "/home/agent",
            "MPLCONFIGDIR": "/tmp/matplotlib-agent",
            "XDG_CACHE_HOME": "/tmp/agent-cache",
        }

    def _run(self, command: str, cwd: str, timeout: int, user: str) -> dict[str, Any]:
        future = asyncio.run_coroutine_threadsafe(
            self.harbor_env.exec(
                command=command,
                cwd=cwd,
                env=self._exec_env(user),
                timeout_sec=timeout,
                user=user,
            ),
            self._loop,
        )
        result = future.result(timeout=timeout + 30)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if stderr:
            combined = f"{stdout}\n{stderr}" if stdout else stderr
        else:
            combined = stdout
        combined = self._truncate_output(combined)
        return {"output": combined, "returncode": result.return_code}

    def _truncate_output(self, output: str) -> str:
        """Keep command output below provider message limits while preserving context."""
        limit = self.max_output_chars
        if limit <= 0 or len(output) <= limit:
            return output
        head_len = limit // 2
        tail_len = limit - head_len
        omitted = len(output) - limit
        return (
            output[:head_len]
            + f"\n\n[harbor adapter truncated {omitted} characters of command output; "
            "use head/tail/rg/python summaries instead of printing whole large files]\n\n"
            + output[-tail_len:]
        )

    def execute(self, command: str, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute *command* as the non-root ``agent`` user."""
        return self._run(command, cwd or self.cwd, timeout or self.timeout, "agent")

    def execute_privileged(self, command: str, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute *command* as root — bridge-only (never agent-generated)."""
        return self._run(command, cwd or "/", timeout or self.timeout, "root")


# ---------------------------------------------------------------------------
# Prompt templates (generic single-command bash loop).
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
You are a skilled software engineer working in a Linux terminal environment.

<important>
This is an interactive process where you think and issue ONE command, see its \
result, then think and issue your next command.
</important>

Your response must contain exactly ONE bash code block with ONE command (or \
commands joined with && or ||). Include a THOUGHT section before your command.

<format_example>
Your reasoning and analysis here.

```bash
your_command_here
```
</format_example>

## Step Budget
You have at most {{ step_limit }} steps and a budget of ${{ cost_limit }}.

## Submission
When your policy is ready, finish with:
```bash
echo "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
```
"""

_INSTANCE_TEMPLATE = """\
## Task

{{ task }}

## Working Directory
Start by exploring `/workspace`. Follow the task instructions for which files
to edit and how to use `sudo run_probe` to query the sealed target.
"""


# ---------------------------------------------------------------------------
# Agent.
# ---------------------------------------------------------------------------


class HarborRevengeAgent(BaseAgent):
    """RevengeBench inverse-strategy agent as a Harbor-compatible agent."""

    SUPPORTS_ATIF: bool = False  # we save our own mini-swe trajectory format

    def __init__(
        self,
        step_limit: int | None = None,
        cost_limit: float | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        reasoning_effort: str | None = "medium",
        model_timeout_sec: int | float | None = 90,
        model_retry_attempts: int | None = 2,
        *args,
        **kwargs,
    ):
        # Historical HarborRevengeAgent commands accepted max_probes and used
        # the bridge to seed /workspace/.probe_budget. Probe budgets are now a
        # task-image contract enforced by sudo run_probe, so keep this kwarg
        # backward-compatible but deliberately ignore it.
        kwargs.pop("max_probes", None)
        super().__init__(*args, **kwargs)
        # Defaults sized to the native multi-round path's total budget: ~5 rounds
        # of interactive work. Override per run via Harbor `--agent-kwarg`.
        self._step_limit = int(step_limit) if step_limit is not None else 150
        self._cost_limit = float(cost_limit) if cost_limit is not None else 5.0
        self._api_base = api_base
        self._api_key = api_key
        self._reasoning_effort = (
            str(reasoning_effort).strip() if reasoning_effort is not None else ""
        )
        self._model_timeout_sec = (
            float(model_timeout_sec) if model_timeout_sec is not None else None
        )
        self._model_retry_attempts = (
            int(model_retry_attempts) if model_retry_attempts is not None else None
        )
        self._last_stats: dict[str, Any] = {}

    @staticmethod
    def name() -> str:
        return "revenge-bench"

    def version(self) -> str | None:
        try:
            from importlib.metadata import version as _pkg_version

            return _pkg_version("revenge-bench")
        except Exception:  # noqa: BLE001 - version is best-effort metadata
            return None

    async def setup(self, environment: "BaseEnvironment") -> None:
        """Nothing to do — the agent runs outside the container."""
        return None

    async def run(
        self,
        instruction: str,
        environment: "BaseEnvironment",
        context: "AgentContext",
    ) -> None:
        loop = asyncio.get_running_loop()
        env_adapter = _HarborEnvAdapter(environment, loop)

        exit_status, result = await asyncio.to_thread(
            self._run_agent_sync, instruction, env_adapter
        )

        logging.getLogger("revenge_bench.harbor").info(
            "HarborRevengeAgent finished: status=%s", exit_status
        )

    def _run_agent_sync(self, instruction: str, env_adapter: _HarborEnvAdapter):
        """Run the synchronous mini-swe-agent loop (in a worker thread)."""
        old_retry_attempts = os.environ.get("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT")
        if self._model_retry_attempts is not None:
            os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = str(
                max(1, self._model_retry_attempts)
            )

        from minisweagent.agents.default import DefaultAgent
        from minisweagent.models import get_model
        from minisweagent.run.utils.save import save_traj

        model_kwargs: dict[str, Any] = {}
        if self._api_base:
            model_kwargs["api_base"] = self._api_base
        if self._api_key:
            model_kwargs["api_key"] = self._api_key
        if self._reasoning_effort:
            model_kwargs["reasoning_effort"] = self._reasoning_effort
        if self._model_timeout_sec is not None and self._model_timeout_sec > 0:
            # LiteLLM's completion() accepts `timeout`; some provider shims also
            # look for `request_timeout`, so pass both with the same bounded value.
            model_kwargs["timeout"] = self._model_timeout_sec
            model_kwargs["request_timeout"] = self._model_timeout_sec

        model = get_model(
            self.model_name,
            config={"model_kwargs": model_kwargs} if model_kwargs else None,
        )

        agent = DefaultAgent(
            model,
            env_adapter,
            system_template=_SYSTEM_TEMPLATE,
            instance_template=_INSTANCE_TEMPLATE,
            step_limit=self._step_limit,
            cost_limit=self._cost_limit,
        )

        exit_status: str = "error"
        result: str = ""
        try:
            exit_status, result = agent.run(task=instruction)
        except Exception as exc:  # noqa: BLE001 - record and surface via traj
            import traceback

            exit_status = str(exc)
            result = traceback.format_exc()
            logging.getLogger("revenge_bench.harbor").critical(result)
        finally:
            self._last_stats = {
                "cost_usd": float(getattr(model, "cost", 0.0) or 0.0),
                "n_calls": int(getattr(model, "n_calls", 0) or 0),
            }
            try:
                traj_path = Path(self.logs_dir) / "revenge_bench.traj.json"
                Path(self.logs_dir).mkdir(parents=True, exist_ok=True)
                save_traj(agent, traj_path, exit_status=exit_status, result=result)
            except Exception:  # noqa: BLE001 - trajectory saving is best-effort
                logging.getLogger("revenge_bench.harbor").exception(
                    "Failed to save trajectory"
                )
            if old_retry_attempts is None:
                os.environ.pop("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", None)
            else:
                os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = old_retry_attempts
        return exit_status, result

    def populate_context_post_run(self, context: "AgentContext") -> None:
        """Report cost back to Harbor's trial bookkeeping."""
        if not self._last_stats:
            return
        try:
            context.cost_usd = self._last_stats.get("cost_usd", context.cost_usd)
        except Exception:  # noqa: BLE001 - context is best-effort telemetry
            pass
