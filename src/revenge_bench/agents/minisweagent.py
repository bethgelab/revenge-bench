"""
Mini-SWE-Agent integration for inverse_strategy.

This module provides LLM-powered agents that can edit code in Docker environments.
Based on CodeClash's minisweagent.py with adaptations for inverse strategy tasks.
"""

import logging
import os
import re
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from minisweagent import Model
from minisweagent.agents.default import (
    AgentConfig,
    DefaultAgent,
    LimitsExceeded,
    NonTerminatingException,
    TerminatingException,
)
from minisweagent.models import get_model
from minisweagent.models.test_models import DeterministicModel
from minisweagent.run.utils.save import save_traj

from revenge_bench import REPO_DIR
from revenge_bench.agents.player import Player
from revenge_bench.agents.utils import GameContext
from revenge_bench.utils.environment import ContainerEnvironment, copy_to_container

os.environ["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "90"
os.environ["LITELLM_MODEL_REGISTRY_PATH"] = str(
    (REPO_DIR / "configs" / "mini" / "litellm_custom_model_config.yaml").resolve()
)


@dataclass
class ClashAgentConfig(AgentConfig):
    """AgentConfig extended with output-size controls.

    max_output_chars:
        Hard-truncate each command output to this many characters at
        observation-creation time (head + tail, split evenly).
        None means fall back to the template's own limit (default 10 000).

    keep_recent_observations:
        When set to k, compact observations older than the last k turns
        before sending to the model.  The full text is still stored in
        self.messages / trajectory logs.

    max_past_output_chars:
        Applied together with keep_recent_observations: old observations
        are further truncated to this many characters (head only).
        None means no extra truncation beyond compaction.

    max_context_chars:
        Global budget for the total character count of all messages sent
        to the model.  After smart compaction, if the total still exceeds
        this limit, old compactable messages are dropped entirely
        (oldest first) until the budget is met.  System, instance-prompt,
        recent-window, and assistant messages are never dropped.
        None means no global limit (default).
    """

    max_output_chars: int | None = None
    keep_recent_observations: int | None = None
    max_past_output_chars: int | None = None
    max_context_chars: int | None = None


class ClashAgent(DefaultAgent):
    """
    Slightly modified version of `DefaultAgent` from mini-SWE-agent
    (https://github.com/SWE-agent/mini-swe-agent)
    """

    # Observations shorter than this are never compacted (mostly error lines / short outputs).
    COMPACT_THRESHOLD = 500

    def __init__(
        self,
        model: Model,
        env: ContainerEnvironment,
        *,
        logger: logging.Logger,
        config_class: Callable = ClashAgentConfig,
        probe_callback: Callable[[], str] | None = None,
        max_probes: int = 5,
        **kwargs,
    ):
        super().__init__(model, env, config_class=config_class, **kwargs)
        self.logger = logger
        self.probe_callback = probe_callback
        self.max_probes = max_probes
        self.probe_count = 0

    _CHANNEL_TOKEN_RE = re.compile(r"<\|(?:channel|end|endoftext|im_end|im_start)\|>")

    @staticmethod
    def _strip_channel_tokens(content: str) -> str:
        """Strip leaked internal channel tokens (<|end|>, <|channel|>, etc.).

        Some models (e.g. gpt-oss-120b) leak internal framing tokens into
        the API response.  If these end up in conversation history, the API
        rejects subsequent requests.  We keep only text before the first
        such token.
        """
        if "<|" not in content:
            return content
        clean = ClashAgent._CHANNEL_TOKEN_RE.split(content)[0]
        return clean if clean.strip() else content

    def add_message(self, role: str, content: str, **kwargs):
        content = self._strip_channel_tokens(content)
        super().add_message(role, content, **kwargs)
        self.logger.debug(f"[{role}] {content}", extra={"highlighter": None})

    # ------------------------------------------------------------------
    # Output truncation (applied at observation-creation time)
    # ------------------------------------------------------------------

    def get_observation(self, response: dict) -> dict:
        """Execute action, optionally pre-truncate output, then render observation."""
        output = self.execute_action(self.parse_action(response))
        max_chars = self.config.max_output_chars
        if max_chars is not None:
            raw = output.get("output", "")
            if len(raw) > max_chars:
                half = max_chars // 2
                output = {
                    **output,
                    "output": (
                        raw[:half]
                        + f"\n[...{len(raw) - max_chars} chars omitted...]\n"
                        + raw[-half:]
                    ),
                }
        observation = self.render_template(self.config.action_observation_template, output=output)
        self.add_message("user", observation)
        return output

    # ------------------------------------------------------------------
    # History compaction (applied at query time, non-destructive)
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_observation(content: str) -> str:
        """Produce a short summary of an observation message.

        Content types in the pipeline:
        - Probe feedback  → "PROBE RESULT (N/M):" with pairs count and file path
        - Trace file      → JSON with mean_distance, per_simulation, nonzero_distances
        - Probe trace     → JSON with pairs [{turn, probe_action, target_action, distance, target_state}]
        - Code reads      → numbered source code lines (cat main.py)
        - Sim traces      → JSONL with {turn, x, y, action} lines
        - Truncated       → <warning> + <output_head>
        """
        # Probe feedback — short pointer with pairs count
        if "PROBE RESULT" in content:
            probe_id = re.search(r'PROBE RESULT \((\d+/\d+)\)', content)
            pid = probe_id.group(1) if probe_id else "?"
            pairs_match = re.search(r'(\d+) pairs captured', content)
            pairs = pairs_match.group(1) if pairs_match else "?"
            sims_match = re.search(r'(\d+) simulations', content)
            sims = sims_match.group(1) if sims_match else "?"
            return f"[Compacted probe {pid}: {pairs} pairs captured, {sims} sims. Re-probe if needed]"

        # Truncated output with <warning> + <output_head>
        if "<output_head>" in content or ("<warning>" in content and "</output>" not in content):
            # Try to extract key metrics from truncated trace JSON
            dist_match = re.search(r'"mean_distance"\s*:\s*([\d.]+)', content)
            actions_match = re.search(r'"total_actions"\s*:\s*(\d+)', content)
            if dist_match:
                dist = dist_match.group(1)
                actions = actions_match.group(1) if actions_match else "?"
                return f"[Compacted trace: mean_distance={dist}, total_actions={actions}. {len(content)} chars omitted]"
            # Preserve first line (or 3 for JSON/stats) of truncated head
            head_match = re.search(r'<output_head>\s*(.*)', content, re.DOTALL)
            if head_match:
                head_lines = head_match.group(1).strip().splitlines()
                first = head_lines[0].strip() if head_lines else ""
                n_preview = 3 if first[:1] in ('{', '[') or re.match(r'\d', first) else 1
                preview = "\n".join(line[:120] for line in head_lines[:n_preview])
                return f"[Compacted truncated output ({len(content)} chars). Preview:\n{preview}]"
            return f"[Compacted: large truncated output, {len(content)} chars omitted]"

        # Standard observation with <output> tags
        output_match = re.search(r'<output>\s*(.*?)\s*</output>', content, re.DOTALL)
        if output_match:
            body = output_match.group(1)
            n_lines = body.count('\n') + 1
            rc_match = re.search(r'<returncode>(\d+)</returncode>', content)
            rc = rc_match.group(1) if rc_match else "?"

            # Probe trace JSON — has "pairs" with probe_action/target_action
            if '"probe_action"' in body or '"pairs"' in body:
                pairs_match = re.search(r'"total_turns"\s*:\s*(\d+)', body)
                turns = pairs_match.group(1) if pairs_match else "?"
                n_pairs = body.count('"probe_action"')
                return f"[Compacted probe trace: {n_pairs} pairs, {turns} total_turns. {len(body)} chars omitted]"

            # Trace JSON — has mean_distance
            dist_match = re.search(r'"mean_distance"\s*:\s*([\d.]+)', body)
            if dist_match:
                actions_match = re.search(r'"total_actions"\s*:\s*(\d+)', body)
                dist = dist_match.group(1)
                actions = actions_match.group(1) if actions_match else "?"
                return f"[Compacted trace: mean_distance={dist}, total_actions={actions}. {len(body)} chars omitted]"

            # JSON array with distance fields (e.g. jq on nonzero_distances or probe pairs)
            if body.strip().startswith("[") and '"distance"' in body and '"_action"' in body.replace("learner_action", "_action").replace("target_action", "_action").replace("probe_action", "_action"):
                import json as _json
                try:
                    arr = _json.loads(body.strip())
                    if isinstance(arr, list) and arr:
                        dists = [e["distance"] for e in arr if isinstance(e, dict) and "distance" in e]
                        if dists:
                            n_entries = len(arr)
                            mean_d = sum(dists) / len(dists)
                            n_nonzero = sum(1 for d in dists if d > 0)
                            sims = {e.get("sim_file") for e in arr if isinstance(e, dict) and "sim_file" in e}
                            sims.discard(None)
                            parts = f"{n_entries} entries, mean_distance={mean_d:.3f}, {n_nonzero}/{len(dists)} nonzero"
                            if sims:
                                parts += f", {len(sims)} sims"
                            return f"[Compacted distance array: {parts}. {len(body)} chars omitted]"
                except (_json.JSONDecodeError, KeyError, TypeError):
                    pass

            # Code read — numbered source lines
            if body.strip() and re.match(r'\s*\d+\s', body.strip()):
                first_line = body.strip().splitlines()[0][:80]
                return f"[Compacted code listing: {n_lines} lines. First: {first_line!r}. {len(body)} chars omitted]"

            # Generic output — 3-line preview for JSON/stats, 1-line otherwise
            lines = body.strip().splitlines()
            first = lines[0].strip() if lines else ""
            n_preview = 3 if first[:1] in ('{', '[') or re.match(r'\d', first) else 1
            preview = "\n".join(line[:120] for line in lines[:n_preview])
            return (
                f"[Compacted output: {n_lines} lines, returncode={rc}. "
                f"{len(body)} chars omitted. Preview:\n{preview}]"
            )

        # Fallback — 3-line preview for JSON/stats, 1-line otherwise
        lines = content.strip().splitlines()
        first = lines[0].strip() if lines else ""
        n_preview = 3 if first[:1] in ('{', '[') or re.match(r'\d', first) else 1
        preview = "\n".join(line[:120] for line in lines[:n_preview])
        return f"[Compacted: {len(content)} chars omitted. Preview:\n{preview}]"

    def _compact_messages(self) -> list[dict]:
        """Return a compacted copy of self.messages for the model query.

        Three independent stages, each gated by its own config flag:
          S1  keep_recent_observations – summarise old user observations
          S2  max_past_output_chars    – truncate summarised text
          S3  max_context_chars        – global budget, drop oldest turns

        Keeps the system message (index 0) and instance prompt (index 1) intact.
        All assistant messages are always kept intact (they're small).
        self.messages is never mutated; trajectory logs retain the full text.
        """
        obs_indices = [i for i, m in enumerate(self.messages) if m["role"] == "user" and i > 1]

        # ── S1 + S2: smart summarisation & truncation ───────────────
        k = self.config.keep_recent_observations
        if k is not None and len(obs_indices) > k:
            to_compact = {
                i for i in (obs_indices[:-k] if k > 0 else obs_indices)
                if not self.messages[i].get("pinned")
            }
            past_limit = self.config.max_past_output_chars

            compacted = []
            for i, msg in enumerate(self.messages):
                if i in to_compact and len(msg["content"]) > self.COMPACT_THRESHOLD:
                    content = self._summarize_observation(msg["content"])
                    if past_limit is not None and len(content) > past_limit:
                        content = content[:past_limit] + f"\n[...{len(content) - past_limit} chars omitted]"
                    compacted.append({**msg, "content": content})
                else:
                    compacted.append(msg)
        else:
            to_compact = set()
            compacted = list(self.messages)

        # ── S3: global context budget ───────────────────────────────
        # Drop old messages oldest-first, then consolidate all dropped
        # turns into a single placeholder after the system prompt.
        # Only messages OUTSIDE the keep_recent_observations window are
        # eligible for dropping.  Recent-window observations are never
        # touched, even if the budget is still exceeded.
        max_ctx = self.config.max_context_chars
        if max_ctx is not None:
            total = sum(len(m["content"]) for m in compacted)
            if total > max_ctx:
                # Only already-compacted (outside-window) turns are droppable.
                # Pinned messages are already excluded from `to_compact` in S1,
                # so they cannot appear here.
                droppable = sorted(to_compact) if to_compact else []
                dropped_indices: set[int] = set()
                for idx in droppable:
                    if total <= max_ctx:
                        break
                    total -= len(compacted[idx]["content"])
                    # The rebuild phase drops the assistant that follows a
                    # dropped user-obs (its response). Account for that here
                    # so the loop's stop condition matches the actual
                    # post-rebuild size, instead of under-estimating and
                    # over-dropping every droppable turn.
                    if (
                        idx + 1 < len(compacted)
                        and compacted[idx + 1]["role"] == "assistant"
                    ):
                        total -= len(compacted[idx + 1]["content"])
                    dropped_indices.add(idx)

                if total > max_ctx:
                    self.logger.warning(
                        f"[compaction] S3 could not meet max_context_chars={max_ctx} "
                        f"without touching the recent-{k} window. "
                        f"Remaining context: {total:,} chars."
                    )

                if dropped_indices:

                    # Remove dropped messages; prepend a single placeholder
                    # to the first surviving user message (avoids user-user
                    # adjacency that a standalone placeholder would create).
                    n_dropped = len(dropped_indices)
                    placeholder = f"[{n_dropped} earlier turns omitted]\n\n"
                    kept = []
                    placeholder_prepended = False
                    for i, msg in enumerate(compacted):
                        if i in dropped_indices:
                            continue
                        # Drop assistant messages whose preceding user message was dropped
                        if msg["role"] == "assistant" and (i - 1) in dropped_indices:
                            continue
                        if not placeholder_prepended and msg["role"] == "user" and i > 1 and not msg.get("pinned"):
                            msg = {**msg, "content": placeholder + msg["content"]}
                            placeholder_prepended = True
                        kept.append(msg)
                    compacted = kept

        if compacted is self.messages:
            return self.messages
        return compacted

    @staticmethod
    def _assert_alternating_roles(messages: list[dict]) -> None:
        """Defensive: API requests must alternate roles after the system prompt.

        Any user→user or assistant→assistant pair indicates a bug in lifecycle
        or compaction logic; refuse rather than send malformed input to the
        provider (where the failure mode is a 4xx that masks as retry exhaustion).
        Uses `if/raise` rather than `assert` so the guard survives `python -O`.
        """
        for i in range(1, len(messages)):
            if (messages[i]["role"] == messages[i - 1]["role"]
                    and messages[i]["role"] != "system"):
                raise RuntimeError(
                    f"consecutive {messages[i]['role']} at indices {i-1},{i} "
                    f"in messages-for-model (n={len(messages)}): "
                    f"{messages[i-1]['content'][:200]!r} || "
                    f"{messages[i]['content'][:200]!r}"
                )

    # ------------------------------------------------------------------
    # Resumable session lifecycle
    # ------------------------------------------------------------------

    ROUND_TRANSITION_TEMPLATE = (
        "## Round {prev_round} evaluation complete\n"
        "- Distance this round: {distance:.4f}{distance_delta}\n"
        "- New traces: /logs/rounds/{prev_round}/\n"
        "- Mismatches: {mismatches}\n"
        "- Submission status: {submission_status}\n"
        "\n"
        "This is round {round_num} of {total_rounds}. "
        "{step_increment} steps available this round. "
        "Continue your investigation."
    )

    def append_round_transition(self, *, round_num: int, summary: dict) -> None:
        """Append a pinned round-transition marker to the agent's messages.

        If the trailing message is already a `user` message, the transition
        text is appended to that message's content and the message is pinned
        in place. This preserves user/assistant alternation — at the end of
        a round the trailing message is the limit_note observation, and
        adding the transition as a new user message would create user→user
        adjacency in API requests. Pinning ensures S1/S3 compaction don't
        drop or summarise the merged message.

        If the trailing message is not a user message (defensive: e.g., if a
        custom caller appended an assistant message), a new pinned user
        message is added.

        ``summary`` should contain at minimum: distance, previous_distance,
        mismatches, submission_status. May include total_rounds, step_increment.
        """
        prev_round = round_num - 1
        distance = summary.get("distance")
        prev = summary.get("previous_distance")
        delta_str = ""
        if prev is not None and distance is not None:
            delta = distance - prev
            arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "=")
            delta_str = f" ({arrow}{abs(delta):.4f} from {prev:.4f})"
        transition = self.ROUND_TRANSITION_TEMPLATE.format(
            prev_round=prev_round,
            distance=distance if distance is not None else float("nan"),
            distance_delta=delta_str,
            mismatches=summary.get("mismatches", "?"),
            submission_status=summary.get("submission_status", "?"),
            round_num=round_num,
            total_rounds=summary.get("total_rounds", "?"),
            step_increment=summary.get("step_increment", "?"),
        )

        if self.messages and self.messages[-1]["role"] == "user":
            # Merge into trailing user message; pin it so compaction preserves it.
            # Replace the dict (rather than mutate in place) to match the
            # fresh-dict-per-message invariant that DefaultAgent.add_message holds —
            # so any caller that aliased the previous message dict (e.g., a future
            # finalize_session caller that retains references across rounds) sees
            # the unmodified pre-merge value.
            tail = self.messages[-1]
            self.messages[-1] = {
                **tail,
                "content": tail["content"] + "\n\n" + transition,
                "pinned": True,
            }
        else:
            self.add_message("user", transition, pinned=True)

    def finalize_session(self) -> dict:
        """Return a summary of the session for trajectory persistence.

        Caller (Player.post_run_hook or similar) is responsible for writing
        this to disk. We don't write here because trajectory paths depend on
        round and player context the agent doesn't know about.
        """
        return {
            "api_calls": self.model.n_calls,
            "cost": self.model.cost,
            "probe_count": getattr(self, "probe_count", 0),
            "messages": list(self.messages),
        }

    def _step_loop_until_terminator(self) -> tuple[str, str]:
        """Drive self.step() until a TerminatingException, applying the empty-msg guard.

        Returns (exception_class_name, str(exception)).
        ``NonTerminatingException`` feedback is folded into self.messages as a user
        message. ``TerminatingException`` content is appended only when non-empty —
        this is the guard that prevents user→user adjacency at round boundaries
        (LimitsExceeded has empty str(e); without the guard, the next round's
        pinned transition would land adjacent to the empty message).
        """
        while True:
            try:
                self.step()
            except NonTerminatingException as e:
                self.add_message("user", str(e))
            except TerminatingException as e:
                msg = str(e)
                if msg:
                    self.add_message("user", msg)
                return type(e).__name__, msg

    def run(self, task: str, **kwargs) -> tuple[str, str]:
        """Override DefaultAgent.run to apply the empty-terminator guard.

        We override (rather than inherit) because production callers like
        ``MiniSWEAgent.run`` and the PvP tournament path use this one-shot
        API and would otherwise still hit upstream's unconditional
        ``add_message("user", str(e))`` for LimitsExceeded — leaking the
        empty user message that the round-boundary adjacency fix is designed
        to eliminate.

        Keep this method's terminator handling in sync with
        ``run_until_limit``; the shared logic lives in
        ``_step_loop_until_terminator``.
        """
        self.extra_template_vars |= {"task": task, **kwargs}
        self.messages = []
        self.add_message("system", self.render_template(self.config.system_template))
        self.add_message("user", self.render_template(self.config.instance_template))
        return self._step_loop_until_terminator()

    def start_session(self, task: str = "", **kwargs) -> None:
        """Render system + instance prompts and add them to self.messages.

        Idempotent: subsequent calls are no-ops. After this, the conversation
        is initialized but no model query has happened yet — call run_until_limit()
        to drive the step loop.
        """
        if self.messages:
            return
        self.extra_template_vars |= {"task": task, **kwargs}
        self.add_message("system", self.render_template(self.config.system_template))
        self.add_message("user", self.render_template(self.config.instance_template))

    def run_until_limit(self, *, step_increment: int, cost_increment: float) -> str:
        """Run self.step() until the per-round budget is exhausted or task submitted.

        Extends config.step_limit and config.cost_limit by the given increments
        (relative to the model's current cumulative usage), then loops self.step()
        catching exceptions the same way DefaultAgent.run() does. Returns the
        terminating exception's class name ("Submitted" or "LimitsExceeded").

        ``step_increment`` and ``cost_increment`` are *deltas* applied on top of
        the model's current cumulative ``n_calls`` / ``cost``. Pass the per-round
        budget, not an absolute cap. self.messages is preserved across calls —
        this is what makes the agent resumable across rounds.
        """
        if not self.messages:
            raise RuntimeError(
                "run_until_limit called before start_session — no system/instance prompt"
            )
        # Extend per-round budgets relative to current cumulative usage
        self.config.step_limit = self.model.n_calls + step_increment
        self.config.cost_limit = self.model.cost + cost_increment

        exit_status, _ = self._step_loop_until_terminator()
        return exit_status

    def query(self) -> dict:
        """Query the model with (optionally) compacted message history."""
        if 0 < self.config.step_limit <= self.model.n_calls or 0 < self.config.cost_limit <= self.model.cost:
            raise LimitsExceeded()
        messages_for_model = self._compact_messages()
        if messages_for_model is not self.messages:
            orig_chars = sum(len(m["content"]) for m in self.messages)
            compact_chars = sum(len(m["content"]) for m in messages_for_model)
            self.logger.info(
                f"[compaction] {orig_chars} -> {compact_chars} chars "
                f"({100 * (orig_chars - compact_chars) / orig_chars:.0f}% reduction)"
            )
        self._assert_alternating_roles(messages_for_model)
        response = self.model.query(messages_for_model)
        # Strip leaked channel tokens (e.g. <|end|>) from the response
        # before it reaches parse_action.  add_message also strips, so
        # conversation history stays clean regardless.
        content = response.get("content", "")
        clean = self._strip_channel_tokens(content)
        if clean != content:
            response["content"] = clean
            self.logger.warning(
                f"Stripped leaked channel tokens from response "
                f"({len(content)} -> {len(clean)} chars)"
            )
        self.add_message("assistant", **response)
        return response

    def render_template(self, template: str, **kwargs) -> str:
        """Override to inject probe variables into template context."""
        # Add probe variables if probing is enabled
        if self.probe_callback is not None:
            kwargs.setdefault("probe_count", self.probe_count)
            kwargs.setdefault("max_probes", self.max_probes)
            kwargs.setdefault("probing_enabled", True)
        else:
            kwargs.setdefault("probing_enabled", False)
        return super().render_template(template, **kwargs)

    def execute_action(self, action: dict) -> dict:
        """
        Execute action with probe interception.
        
        If the command output starts with PROBE_SUBMIT, we intercept it
        and run a probe simulation instead of normal execution flow.
        """
        import subprocess
        from minisweagent.agents.default import ExecutionTimeoutError
        
        try:
            output = self.env.execute(action["action"])
        except (TimeoutError, subprocess.TimeoutExpired) as e:
            output_str = e.output.decode("utf-8", errors="replace") if getattr(e, "output", None) else ""
            raise ExecutionTimeoutError(
                self.render_template(self.config.timeout_template, action=action, output=output_str)
            )
        
        # Check for probe request
        lines = output.get("output", "").strip().splitlines()
        if lines and lines[0].strip() == "PROBE_SUBMIT":
            if self.probe_callback is None:
                output = {"output": "ERROR: Probing not available in this mode", "returncode": 1}
            elif self.probe_count >= self.max_probes:
                output = {"output": f"ERROR: Probe limit exceeded ({self.max_probes} probes max)", "returncode": 1}
            else:
                try:
                    probe_result = self.probe_callback()
                    self.probe_count += 1
                    output = {"output": f"PROBE RESULT ({self.probe_count}/{self.max_probes}):\n{probe_result}", "returncode": 0}
                except Exception as e:
                    output = {"output": f"ERROR: Probe failed: {e}", "returncode": 1}
            return output | {"action": action["action"]}
        
        self.has_finished(output)
        return output | {"action": action["action"]}


class MiniSWEAgent(Player):
    """Player with agentic code editing capabilities using mini-swe-agent."""

    def __init__(self, config: dict, environment: ContainerEnvironment, game_context: GameContext):
        super().__init__(config, environment=environment, game_context=game_context)

    def run(self):
        # temporary workaround around https://github.com/SWE-agent/mini-swe-agent/issues/477
        if "DeterministicModel" not in self.config["config"]["model"].get("model_class", ""):
            model = get_model(config=self.config["config"]["model"])
        else:
            model = DeterministicModel(outputs=self.config["config"]["model"]["outputs"])
        self.agent = ClashAgent(
            model=model,
            env=self.environment,
            logger=self.logger,
            **self.config["config"]["agent"],
        )
        exit_status = None
        result = None
        exc_message = None
        try:
            exit_status, result = self.agent.run(task="", **self.game_context.to_template_vars())
        except Exception as e:
            exit_status = str(e)
            exc_message = traceback.format_exc()
            result = exc_message
            self.logger.critical(exc_message)
        finally:
            traj_path = (
                self.game_context.log_local
                / "players"
                / self.name
                / f"{self.name}_r{self.game_context.round}.traj.json"
            )
            save_traj(
                self.agent,  # type: ignore
                traj_path,
                exit_status=exit_status,
                result=result,
                print_fct=self.logger.debug,
            )
            copy_to_container(
                self.environment,
                traj_path,
                self.game_context.log_env / "edits" / traj_path.name,
            )
            self._metadata["agent_stats"][self.game_context.round] = {
                "exit_status": exit_status,
                "cost": self.agent.model.cost,
                "api_calls": self.agent.model.n_calls,
            }
        if exit_status.lower().strip() not in ["", "submitted", "limitsexceeded"] and exc_message is not None:
            raise RuntimeError(f"Agent {self.name} failed with exit status: {exit_status} and exception: {exc_message}")


class InverseStrategyAgent(MiniSWEAgent):
    """
    Agent for inverse strategy extraction.
    
    Extends MiniSWEAgent to handle the inverse strategy task:
    - Receives game traces (state-action pairs) as context
    - Analyzes traces to understand the strategy
    - Writes code that reproduces the observed behavior
    
    The key difference from regular CodeClash:
    - CodeClash: Agent competes by writing better code each round
    - InverseStrategy: Agent analyzes traces and writes code that matches observed behavior
    
    Additional context passed via game_context.prompts:
    - traces_summary: Summary of available traces
    - evaluation_results: Results from previous round's code evaluation
    """

    def __init__(self, config: dict, environment: ContainerEnvironment, game_context: GameContext):
        super().__init__(config, environment=environment, game_context=game_context)
        # Track inverse strategy specific metadata
        self._metadata["inverse_strategy"] = {
            "traces_provided": False,
            "evaluation_history": [],
        }
        # Probe callback - set by tournament if probing is enabled
        self._probe_callback: Callable[[], str] | None = None
        self._max_probes: int = 5

    def set_probe_callback(self, callback: Callable[[], str], max_probes: int = 5):
        """Set the probe callback for inline probing."""
        self._probe_callback = callback
        self._max_probes = max_probes

    def init_session(self) -> None:
        """Construct the inner ClashAgent (once) and start the conversation.

        Idempotent. Must be called before run_round().
        """
        if getattr(self, "agent", None) is not None:
            return
        if "DeterministicModel" not in self.config["config"]["model"].get("model_class", ""):
            model = get_model(config=self.config["config"]["model"])
        else:
            model = DeterministicModel(outputs=self.config["config"]["model"]["outputs"])
        self.agent = ClashAgent(
            model=model,
            env=self.environment,
            logger=self.logger,
            probe_callback=self._probe_callback,
            max_probes=self._max_probes,
            **self.config["config"]["agent"],
        )
        self.agent.start_session(task="", **self.game_context.to_template_vars())

    def run_round(
        self,
        *,
        round_num: int,
        transition_summary: dict | None,
        step_increment: int,
        cost_increment: float,
    ) -> str:
        """Drive one round of the resumable loop.

        On round 2+, transition_summary is required and is appended as a pinned
        round-transition user message before run_until_limit.
        """
        if getattr(self, "agent", None) is None:
            raise RuntimeError("run_round called before init_session")
        # Reset per-round probe counter (Issue 1: probe_count would otherwise
        # accumulate across rounds since the inner ClashAgent persists).
        self.agent.probe_count = 0
        self.agent.max_probes = self._max_probes
        if round_num > 1:
            if transition_summary is None:
                raise ValueError("transition_summary required for round_num > 1")
            self.agent.append_round_transition(
                round_num=round_num, summary=transition_summary
            )
        return self.agent.run_until_limit(
            step_increment=step_increment, cost_increment=cost_increment
        )

    def save_round_trajectory(self, *, round_num: int, exit_status: str) -> None:
        """Save a cumulative trajectory snapshot after each round.

        Replicates the existing learner_r{N}.traj.json convention so
        post-processing tools keep working unchanged.
        """
        from minisweagent.run.utils.save import save_traj
        from revenge_bench.utils.environment import copy_to_container

        traj_path = (
            self.game_context.log_local
            / "players"
            / self.name
            / f"{self.name}_r{round_num}.traj.json"
        )
        save_traj(
            self.agent,
            traj_path,
            exit_status=exit_status,
            result=exit_status,
            print_fct=self.logger.debug,
        )
        copy_to_container(
            self.environment,
            traj_path,
            self.game_context.log_env / "edits" / traj_path.name,
        )
        self._metadata.setdefault("agent_stats", {})[round_num] = {
            "exit_status": exit_status,
            "cost": self.agent.model.cost,
            "api_calls": self.agent.model.n_calls,
            "probe_count": self.agent.probe_count,
        }

    def run(self):
        """
        Run the inverse strategy agent.

        Before calling the base run(), we can prepare additional context
        specific to inverse strategy (e.g., copy trace files to container).
        """
        # Mark that we're running inverse strategy
        self._metadata["inverse_strategy"]["traces_provided"] = True
        
        # Build agent with probe callback if available
        if "DeterministicModel" not in self.config["config"]["model"].get("model_class", ""):
            model = get_model(config=self.config["config"]["model"])
        else:
            model = DeterministicModel(outputs=self.config["config"]["model"]["outputs"])
        
        self.agent = ClashAgent(
            model=model,
            env=self.environment,
            logger=self.logger,
            probe_callback=self._probe_callback,
            max_probes=self._max_probes,
            **self.config["config"]["agent"],
        )
        
        exit_status = None
        result = None
        exc_message = None
        try:
            exit_status, result = self.agent.run(task="", **self.game_context.to_template_vars())
        except Exception as e:
            exit_status = str(e)
            exc_message = traceback.format_exc()
            result = exc_message
            self.logger.critical(exc_message)
        finally:
            traj_path = (
                self.game_context.log_local
                / "players"
                / self.name
                / f"{self.name}_r{self.game_context.round}.traj.json"
            )
            save_traj(
                self.agent,
                traj_path,
                exit_status=exit_status,
                result=result,
                print_fct=self.logger.debug,
            )
            copy_to_container(
                self.environment,
                traj_path,
                self.game_context.log_env / "edits" / traj_path.name,
            )
            self._metadata["agent_stats"][self.game_context.round] = {
                "exit_status": exit_status,
                "cost": self.agent.model.cost,
                "api_calls": self.agent.model.n_calls,
                "probe_count": self.agent.probe_count,
            }
        
        if exit_status.lower().strip() not in ["", "submitted", "limitsexceeded"] and exc_message is not None:
            raise RuntimeError(f"Agent {self.name} failed with exit status: {exit_status} and exception: {exc_message}")
        
        # Record evaluation results
        self._metadata["inverse_strategy"]["evaluation_history"].append({
            "round": self.game_context.round,
            "cost": self.agent.model.cost,
            "api_calls": self.agent.model.n_calls,
            "probe_count": self.agent.probe_count,
        })
