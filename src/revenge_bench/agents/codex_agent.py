"""
Codex CLI integration for inverse_strategy.

`CodexInverseStrategyAgent` is a parallel `Player` to `InverseStrategyAgent`
that drives OpenAI's Codex CLI (`codex exec`) inside the learner container
instead of mini-swe-agent. The two backends share the tournament-side
contract (Player lifecycle, git tags, changes_r{N}.json, offline eval) but
not the in-agent execution model.

Phase boundaries (matching .cursor/plans/codex-integration_*.plan.md):
- Phase 1 (initial pass): command builder, reset-mode `run()`,
  trajectory writing, agent_stats, set_probe_callback stub.
- Phase 3 (this revision): persistent `init_session()` / `run_round()` /
  `save_round_trajectory()`, CODEX_HOME + `resume --last`,
  transition_summary rendered as plain-text continuation prompt,
  timeout-resets-session rule.
- Phase 4: MCP HTTP control plane wiring (the registered probe callback
  is wired through there; the `set_probe_callback` stub here is what the
  tournament binds to).

The adapter never touches mini-swe-agent imports — keep this module
independent so installations without mini-swe-agent extras can still load
the Codex backend.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from jinja2 import StrictUndefined, Template

from revenge_bench.agents.player import Player
from revenge_bench.agents.utils import GameContext
from revenge_bench.utils.environment import (
    ContainerEnvironment,
    copy_to_container,
    create_file_in_container,
)

# Marker file written by the MCP `submit` tool inside the learner container.
# The image-baked watchdog polls for this path; the host-side adapter also
# inspects it after `codex exec` returns to determine submission status.
SUBMIT_MARKER_PATH = "/workspace/.inverse_strategy/submitted.json"

# CODEX_HOME is intentionally placed *outside* /workspace so that
# Player._commit() (`git add -A` in /workspace) does not stage Codex
# session caches into the round commit. See plan review issue #1.
CODEX_HOME_PATH = "/codex_home"

# Where the rendered round prompt is written inside the container before
# being piped into `codex exec`. Outside /workspace for the same reason.
PROMPT_PATH = "/codex_home/round_prompt.txt"

# Where Codex writes its final assistant message (deterministic per-round
# filename so the host adapter can copy it back into the trajectory).
LAST_MESSAGE_PATH_TEMPLATE = "/codex_home/last_message_r{round}.txt"

# Default host auth path that Codex CLI uses after `codex login`.
DEFAULT_HOST_AUTH_FILE = "~/.codex/auth.json"

# Image-baked watchdog wrapper. See scripts/codex/inverse-codex-exec.sh.
HELPER_SCRIPT_PATH = "/usr/local/bin/inverse-codex-exec"

# Grace defaults for the helper script (overridable per config later).
DEFAULT_GRACE_SECS = 8
DEFAULT_KILL_GRACE_SECS = 5

ResumeMode = Literal["fresh", "resume_last"]


def build_codex_command(
    *,
    codex_config: dict,
    output_path: str,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build the `codex exec` argv list from a YAML `config.codex` block.

    Pure function — no side effects. Tested directly in unit tests so the
    adapter doesn't have to spin up a container to verify flag handling.

    `codex_config` shape (all optional except `command` and `model`):
        command: codex
        model: gpt-5-mini
        sandbox: workspace-write
        profile: <profile-name> | null
        skip_git_repo_check: true
        ephemeral: false
        config_overrides:
            model_reasoning_effort: low
            tool_output_token_limit: 3000

    Pass ``extra_args=["resume", "--last"]`` to drive a resume invocation;
    note Codex expects `resume` to come immediately after `exec`, so the
    caller is responsible for putting them in the right slot — which this
    function does *not* do (extra_args is appended at the end). For resume
    mode the agent invokes Codex via a different argv shape entirely
    (`codex exec resume --last ...`), see `_build_codex_argv`.
    """
    command = codex_config.get("command", "codex")
    model = codex_config.get("model")
    if not model:
        raise ValueError("codex_config.model is required")

    sandbox = codex_config.get("sandbox", "workspace-write")
    profile = codex_config.get("profile")
    skip_git_repo_check = codex_config.get("skip_git_repo_check", True)
    ephemeral = codex_config.get("ephemeral", False)
    config_overrides: dict[str, Any] = codex_config.get("config_overrides") or {}

    cmd: list[str] = [
        command,
        "exec",
        "--cd",
        "/workspace",
        "--json",
        "--color",
        "never",
        "--output-last-message",
        output_path,
        "--sandbox",
        sandbox,
        "--model",
        model,
    ]
    if skip_git_repo_check:
        cmd.append("--skip-git-repo-check")
    if ephemeral:
        cmd.append("--ephemeral")
    if profile:
        cmd.extend(["--profile", profile])
    for key, value in config_overrides.items():
        cmd.extend(["-c", f"{key}={_format_override_value(value)}"])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def _build_codex_resume_command(
    *,
    codex_config: dict,
    output_path: str,
) -> list[str]:
    """Build ``codex exec resume --last ...`` argv.

    Only includes flags that ``codex exec resume`` accepts. Session-state
    flags (``--cd``, ``--sandbox``, ``--color``, ``--profile``) are
    rejected on resume; codex does not propagate them from the original
    session either, so the resumed invocation falls back to its default
    sandbox unless we re-supply it via a different mechanism.

    For ``sandbox: danger-full-access`` (the standard setup when codex
    is itself running inside an arena Docker container), we pass
    ``--dangerously-bypass-approvals-and-sandbox`` on resume — that's
    the only resume-compatible way to skip the bwrap-based sandbox,
    which can't create user namespaces inside an unprivileged
    container.
    """
    command = codex_config.get("command", "codex")
    model = codex_config.get("model")
    if not model:
        raise ValueError("codex_config.model is required")

    sandbox = codex_config.get("sandbox", "workspace-write")
    skip_git_repo_check = codex_config.get("skip_git_repo_check", True)
    ephemeral = codex_config.get("ephemeral", False)
    config_overrides: dict[str, Any] = codex_config.get("config_overrides") or {}

    cmd: list[str] = [
        command,
        "exec",
        "resume",
        "--last",
        "--json",
        "--output-last-message",
        output_path,
        "--model",
        model,
    ]
    if sandbox == "danger-full-access":
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    if skip_git_repo_check:
        cmd.append("--skip-git-repo-check")
    if ephemeral:
        cmd.append("--ephemeral")
    for key, value in config_overrides.items():
        cmd.extend(["-c", f"{key}={_format_override_value(value)}"])
    return cmd


def _format_override_value(value: Any) -> str:
    """Render a YAML value as the `-c key=value` form expected by Codex.

    Booleans become `true`/`false`; strings are passed verbatim (no shell
    quoting — the caller assembles the final argv list, not a shell line).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _classify_submission(exit_status: str, marker_present: bool) -> str:
    """Translate a low-level process outcome into a round-outcome string.

    See ``_run_codex_exec`` for the value ladder. Marker presence wins
    over everything else — even if the process timed out, if the marker
    is on disk we know the model deliberately submitted before the
    helper got around to killing it.
    """
    if marker_present:
        return "submitted"
    if exit_status == "timeout":
        return "timeout"
    if exit_status == "ok":
        return "exited_without_submit"
    return "error"


def _parse_codex_events(stdout: str) -> list[dict]:
    """Parse codex's JSONL output stream into structured events.

    Codex emits ``--json`` mode as one JSON object per line, with
    occasional plain-text lines mixed in (e.g. ``Reading prompt from
    stdin...``). We preserve order and represent non-JSON lines as
    ``{"_kind": "raw_line", "text": "<line>"}`` so callers see a single
    homogeneous list.
    """
    events: list[dict] = []
    if not stdout:
        return events
    for line in stdout.splitlines():
        line = line.rstrip()
        if not line:
            continue
        stripped = line.lstrip()
        if stripped.startswith("{"):
            try:
                events.append(json.loads(stripped))
                continue
            except json.JSONDecodeError:
                pass
        events.append({"_kind": "raw_line", "text": line})
    return events


def _aggregate_usage(events: list[dict]) -> dict:
    """Sum token usage across ``turn.completed`` events.

    A round can have multiple turns; we aggregate so the trajectory
    carries a single per-round tally. ``turns_completed=0`` distinguishes
    "round really used 0 tokens" from "round was cut short before usage
    could be tallied" (e.g. helper SIGTERM mid-turn on timeout).
    """
    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "turns_completed": 0,
    }
    for ev in events:
        if ev.get("type") != "turn.completed":
            continue
        usage = ev.get("usage") or {}
        totals["turns_completed"] += 1
        for k in ("input_tokens", "cached_input_tokens",
                  "output_tokens", "reasoning_output_tokens"):
            totals[k] += int(usage.get(k, 0) or 0)
    return totals


def _parse_codex_usage(stdout: str) -> dict:
    """Convenience wrapper: parse stdout to events then aggregate."""
    return _aggregate_usage(_parse_codex_events(stdout))


def render_transition_summary(round_num: int, summary: dict) -> str:
    """Render `build_round_transition_summary`'s dict as plain text.

    Intentionally simple — no Jinja, no pinned-message semantics. This
    text becomes the continuation prompt for `codex exec resume --last`,
    so it should read naturally as the user's next message rather than a
    structured payload.
    """
    distance = summary.get("distance")
    prev_distance = summary.get("previous_distance")
    mismatches = summary.get("mismatches")
    submission_status = summary.get("submission_status", "?")
    total_rounds = summary.get("total_rounds")

    lines = [f"Round {round_num - 1} evaluation complete."]
    if distance is not None:
        if prev_distance is not None:
            delta = distance - prev_distance
            direction = (
                "improved" if delta < -0.01
                else "degraded" if delta > 0.01
                else "unchanged"
            )
            lines.append(
                f"  Distance: {distance:.4f} "
                f"({delta:+.4f} from {prev_distance:.4f}, {direction})"
            )
        else:
            lines.append(f"  Distance: {distance:.4f}")
    else:
        lines.append("  Distance: evaluation failed (no metric).")
    if mismatches is not None:
        lines.append(f"  Mismatches: {mismatches}")
    lines.append(f"  Previous-round submission status: {submission_status}")
    if total_rounds is not None:
        lines.append(f"Now starting round {round_num} of {total_rounds}.")
    else:
        lines.append(f"Now starting round {round_num}.")
    lines.append(
        "New traces are at /logs/rounds/{}/traces.json. "
        "Continue editing /workspace based on this round's evaluation.".format(round_num - 1)
    )
    return "\n".join(lines) + "\n"


class CodexInverseStrategyAgent(Player):
    """Codex-CLI-backed inverse strategy learner.

    Reset-mode mirrors `MiniSWEAgent.run()`: one `codex exec` invocation
    per round, full prompt rendered fresh, no cross-round session state.

    Persistent-mode pins a per-tournament `CODEX_HOME` so `codex exec
    resume --last` picks up the previous round's session. On wall-clock
    timeout the agent records `submission_status="timeout"` and forces
    the next round to start fresh (skip resume once) — otherwise
    `resume --last` would pick up a half-finished turn.
    """

    # Duck-typed sentinel read by `InverseStrategyTournament.run_edit_phase`
    # to choose backend-specific kwargs (no `step_limit` / `cost_limit` for
    # Codex, no `transition_summary` rendered as ClashAgent pinned message).
    edit_phase_backend = "codex"

    def __init__(self, config: dict, environment: ContainerEnvironment, game_context: GameContext):
        # Validate before super().__init__() — Player's constructor runs
        # `git rev-parse HEAD` in the container, which we want to skip if
        # the YAML config is malformed.
        codex_cfg = config.get("config", {}).get("codex")
        if not codex_cfg:
            raise ValueError(
                f"agent {config.get('name')!r}: `config.codex` block is required for inverse_codex"
            )
        self._codex_cfg: dict = codex_cfg

        super().__init__(config, environment=environment, game_context=game_context)

        # Probe wiring (set by InverseStrategyInterventionistTournament via
        # the duck-typed `set_probe_callback`).
        self._probe_callback: Callable[[], str] | None = None
        self._max_probes: int = 5

        # Per-round counters / captured state. `_pending_*` fields are
        # populated by run() / run_round() and consumed by
        # save_round_trajectory().
        self._probe_count: int = 0
        self._pending_round_state: dict | None = None

        # Persistent-mode session state.
        self._session_initialised: bool = False
        # When True, the next round must skip `resume --last` and start a
        # fresh Codex session (set by run_round() after a wall-clock
        # timeout, since resume on a half-finished turn is unsafe).
        self._needs_fresh_session: bool = False

        # MCP server reference; set by the tournament after init via
        # `set_mcp_server`. When None, agent runs without MCP wiring (no
        # config.toml, no helper env vars beyond CODEX_HOME) — useful
        # for unit tests and configs that explicitly disable MCP.
        self._mcp_server: Any = None

        self._metadata["inverse_strategy"] = {
            "backend": "codex",
            "evaluation_history": [],
        }

        # Defense-in-depth credential redaction: read the host auth.json
        # once, extract its top-level key names (audit trail) and any
        # token-shaped string values (redaction list applied to
        # captured stdout / last-message before they hit disk).
        # See `_load_auth_secrets` for the heuristics.
        self._auth_key_names, self._auth_redactable = self._load_auth_secrets()
        if self._auth_key_names:
            self.logger.info(
                f"Codex auth credentials loaded with keys: "
                f"{self._auth_key_names} (values redacted from trajectories)"
            )
            self._metadata["inverse_strategy"]["auth_keys_observed"] = (
                self._auth_key_names
            )

    # ------------------------------------------------------------------ #
    # Probe protocol (mirrors InverseStrategyAgent.set_probe_callback so
    # the tournament can register either backend uniformly).
    #
    # NOTE: For the Codex backend this stub just records the callback;
    # actual probe execution flows through the MCP `run_probe` tool.
    # The interventionist tournament still calls this method (via the
    # `hasattr(set_probe_callback)` duck-type check) so we accept it
    # gracefully and stash the args for future debugging.
    # ------------------------------------------------------------------ #

    def set_probe_callback(self, callback: Callable[[], str], max_probes: int = 5) -> None:
        self._probe_callback = callback
        self._max_probes = max_probes

    def set_mcp_server(self, server: Any) -> None:
        """Receive a reference to the tournament's MCP server.

        Called once per tournament after agent construction. The agent
        uses the server's URL/token to register an MCP entry in
        ``$CODEX_HOME/config.toml`` and to propagate ``MCP_URL``/
        ``MCP_TOKEN`` into the helper environment so codex (and codex's
        own MCP client) can reach it.
        """
        self._mcp_server = server

    # ------------------------------------------------------------------ #
    # Player contract: reset-mode entry point.
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Reset-mode: one `codex exec` per round.

        Always starts a fresh Codex session — no `--last` resume. The
        tournament chooses between `run()` (reset) and `init_session()
        + run_round()` (persistent) based on `tournament.context_mode`.
        """
        self._prepare_session()
        round_num = self.game_context.round
        self._probe_count = 0

        prompt = self._render_round_prompt()
        outcome = self._run_codex_exec(round_num=round_num, prompt=prompt, resume_mode="fresh")

        # Reset mode writes the trajectory immediately — there's no
        # separate save_round_trajectory call from the tournament's
        # reset branch.
        self._save_round_artifacts(round_num=round_num, outcome=outcome)

        if outcome["fatal_error"] and outcome["submission_status"] != "submitted":
            raise RuntimeError(
                f"Codex agent {self.name} failed: "
                f"submission_status={outcome['submission_status']} "
                f"exit_status={outcome['exit_status']}\n{outcome['fatal_error']}"
            )

    # ------------------------------------------------------------------ #
    # Player contract: persistent-mode entry points.
    # ------------------------------------------------------------------ #

    def init_session(self) -> None:
        """Prepare CODEX_HOME (and copy host auth) for the tournament.

        Idempotent. The actual `codex exec` runs in `run_round()` — round 1
        starts a fresh session under CODEX_HOME, round N>1 resumes it.
        """
        if self._session_initialised:
            return
        self._prepare_session()
        self._session_initialised = True

    def run_round(
        self,
        *,
        round_num: int,
        transition_summary: dict | None,
        # Mini-swe specific; ignored by the Codex backend (we set them to
        # 0 / 0.0 in the tournament for codex agents).
        step_increment: int = 0,
        cost_increment: float = 0.0,
    ) -> str:
        """Drive one persistent-mode round.

        Round 1: fresh Codex session under the pinned CODEX_HOME, full
        prompt rendered from GameContext.

        Round ≥ 2: `codex exec resume --last` with the rendered
        `transition_summary` as the user-facing continuation prompt —
        unless the previous round timed out, in which case we deliberately
        start fresh again so resume doesn't pick up a half-finished turn.
        """
        if not self._session_initialised:
            raise RuntimeError("run_round called before init_session")
        self._probe_count = 0

        if round_num == 1:
            prompt = self._render_round_prompt()
            resume_mode: ResumeMode = "fresh"
        elif self._needs_fresh_session:
            # Last round timed out — restart cleanly. The transition
            # summary still goes in (so Codex sees what just happened),
            # but as part of the fresh round prompt rather than tacked
            # onto a stale conversation.
            prompt = self._render_round_prompt(
                round_recovery_note=transition_summary,
            )
            resume_mode = "fresh"
            self._needs_fresh_session = False
        else:
            if transition_summary is None:
                raise ValueError("transition_summary required for round_num > 1 in persistent mode")
            prompt = render_transition_summary(round_num, transition_summary)
            resume_mode = "resume_last"

        outcome = self._run_codex_exec(
            round_num=round_num, prompt=prompt, resume_mode=resume_mode
        )
        self._pending_round_state = {"round_num": round_num, "outcome": outcome}

        # On wall-clock timeout, force the next round to start fresh —
        # resume on a half-finished turn is unsafe.
        if outcome["submission_status"] == "timeout":
            self._needs_fresh_session = True
        return outcome["submission_status"]

    def save_round_trajectory(self, *, round_num: int, exit_status: str) -> None:
        """Persist the trajectory + agent_stats for the round.

        ``exit_status`` is the value the tournament saw from
        ``run_round()`` — for codex that's the round-outcome string;
        the keyword name is shared with the mini-swe agent's interface.
        Used to override ``submission_status`` when the tournament's
        outer try/except caught an error we didn't see directly.

        Reads state captured by ``run_round()``. Reset mode writes
        artifacts inline in ``run()`` and does not call this.
        """
        if (
            self._pending_round_state is None
            or self._pending_round_state["round_num"] != round_num
        ):
            raise RuntimeError(
                f"save_round_trajectory(round={round_num}) called without a matching "
                f"run_round() — pending state was {self._pending_round_state}"
            )
        outcome = self._pending_round_state["outcome"]
        # Honour tournament-level overrides (e.g. an exception caught
        # in post_run_hook that we didn't see).
        if exit_status and exit_status != outcome["submission_status"]:
            outcome["submission_status"] = exit_status
        self._save_round_artifacts(round_num=round_num, outcome=outcome)
        self._pending_round_state = None

    # ------------------------------------------------------------------ #
    # Codex invocation.
    # ------------------------------------------------------------------ #

    def _run_codex_exec(
        self,
        *,
        round_num: int,
        prompt: str,
        resume_mode: ResumeMode,
    ) -> dict:
        """Run one `codex exec` invocation and return captured outcome.

        Outcome dict fields:
            exit_status: raw process termination —
                "ok" | "timeout" | "error(returncode=N)" | <ExceptionName>
                (just what subprocess.execute reported).
            submission_status: round outcome (the answer to "what
                happened to this round?") —
                "submitted"           — model called the MCP submit() tool
                                         (the canonical "I'm done" signal).
                "exited_without_submit" — process returned 0 but the model
                                         never invoked submit. The round
                                         is still evaluated against
                                         /workspace as it stands.
                "timeout"             — wall-clock fired before the
                                         model could submit; helper SIGTERM'd.
                "error"               — non-zero exit or Python-level
                                         exception during the run.
            wall_clock_seconds, last_message, stdout, usage, resume_mode,
            fatal_error: as before.
        """
        last_message_path = LAST_MESSAGE_PATH_TEMPLATE.format(round=round_num)
        # Always start each round with no stale submit marker.
        self.environment.execute(f"rm -f {shlex.quote(SUBMIT_MARKER_PATH)}")
        # Stage the prompt as a file so we don't have to shell-escape it.
        create_file_in_container(self.environment, content=prompt, dest_path=PROMPT_PATH)

        argv = self._build_codex_argv(
            output_path=last_message_path, resume_mode=resume_mode
        )
        shell_cmd = self._wrap_in_shell(argv)

        exit_status = "ok"
        fatal_error: str | None = None
        stdout_capture: str | None = None
        wall_start = time.monotonic()
        try:
            result = self.environment.execute(shell_cmd, timeout=self._max_round_seconds())
            stdout_capture = result.get("output", "")
            rc = result.get("returncode", 0)
            if rc != 0:
                exit_status = f"error(returncode={rc})"
        except subprocess.TimeoutExpired as e:
            exit_status = "timeout"
            stdout_capture = (
                e.output.decode("utf-8", errors="replace")
                if getattr(e, "output", None)
                else ""
            )
            self.logger.warning(
                f"codex exec exceeded max_round_seconds={self._max_round_seconds()}; "
                f"round {round_num} marked as timeout"
            )
        except Exception as e:
            exit_status = type(e).__name__
            fatal_error = traceback.format_exc()
            self.logger.critical(fatal_error)
        wall_clock_seconds = time.monotonic() - wall_start

        marker_present = self._check_submitted_marker() is not None
        last_message = self._read_container_file(last_message_path)
        submission_status = _classify_submission(exit_status, marker_present)
        events = _parse_codex_events(stdout_capture or "")

        return {
            "exit_status": exit_status,
            "submission_status": submission_status,
            "wall_clock_seconds": wall_clock_seconds,
            "last_message": last_message,
            "events": events,
            "usage": _aggregate_usage(events),
            "resume_mode": resume_mode,
            "fatal_error": fatal_error,
        }

    def _build_codex_argv(self, *, output_path: str, resume_mode: ResumeMode) -> list[str]:
        """Return the `codex` argv for the requested mode.

        ``codex exec`` and ``codex exec resume`` share some flags but
        differ on session-state flags: `resume` inherits `--cd` /
        `--sandbox` / `--color` / `--profile` from the original session
        and refuses them as args. We build the argv fresh for each mode
        rather than splicing.
        """
        if resume_mode == "fresh":
            return build_codex_command(
                codex_config=self._codex_cfg, output_path=output_path
            )
        return _build_codex_resume_command(
            codex_config=self._codex_cfg, output_path=output_path
        )

    def _wrap_in_shell(self, argv: list[str]) -> str:
        """Wrap the codex argv in a shell line with CODEX_HOME exported.

        Prompt is fed via stdin redirection so its content never has to
        be shell-escaped — only the file path does.

        When the tournament has wired up an MCP server, swap the direct
        ``codex`` invocation for the image-baked
        ``/usr/local/bin/inverse-codex-exec`` watchdog (handles submit
        marker → SIGTERM and wall-clock → 124). Without MCP, the simpler
        direct path keeps unit tests / non-MCP smoke runs working.
        """
        env_exports = [f"CODEX_HOME={shlex.quote(CODEX_HOME_PATH)}"]

        if self._mcp_server is not None:
            # Helper-driven invocation. The helper takes the codex argv
            # *minus* the codex binary itself (it adds that), so we drop
            # argv[0] and prepend the helper path. The wall-clock cap is
            # passed via env so the helper enforces it directly; the
            # outer Python timeout becomes a backstop.
            max_secs = self._max_round_seconds() or 0
            env_exports.extend(
                [
                    f"INVERSE_CODEX_MARKER={shlex.quote(SUBMIT_MARKER_PATH)}",
                    f"INVERSE_CODEX_GRACE_SECS={DEFAULT_GRACE_SECS}",
                    f"INVERSE_CODEX_KILL_GRACE_SECS={DEFAULT_KILL_GRACE_SECS}",
                    f"INVERSE_CODEX_MAX_SECS={int(max_secs)}",
                    # MCP_URL/MCP_TOKEN are read by Codex's MCP client
                    # via the config.toml entry written in
                    # `_register_mcp_with_codex`; we still export them so
                    # debug tooling / preflight curl can use them.
                    f"INVERSE_CODEX_MCP_URL={shlex.quote(self._mcp_server.container_base_url + self._mcp_server.mcp_path)}",
                    f"INVERSE_CODEX_MCP_TOKEN={shlex.quote(self._mcp_server.token)}",
                ]
            )
            cmd_argv = [HELPER_SCRIPT_PATH, *argv[1:]]
        else:
            cmd_argv = argv

        argv_str = " ".join(shlex.quote(part) for part in cmd_argv)
        env_str = " ".join(env_exports)
        return (
            f"export {env_str} && "
            f"{argv_str} < {shlex.quote(PROMPT_PATH)}"
        )

    # ------------------------------------------------------------------ #
    # Container setup helpers.
    # ------------------------------------------------------------------ #

    def _prepare_session(self) -> None:
        """Idempotent CODEX_HOME setup + auth file copy + MCP wiring.

        Runs at the start of every reset-mode round and once before
        round 1 in persistent mode. Cheap enough to repeat (mkdir -p +
        a small file copy) — keeps the implementation simple.
        """
        # Both CODEX_HOME (outside /workspace) and the marker dir
        # (inside /workspace) need to exist before codex exec runs.
        self.environment.execute(
            f"mkdir -p {shlex.quote(CODEX_HOME_PATH)} "
            f"{shlex.quote(str(Path(SUBMIT_MARKER_PATH).parent))}"
        )
        self._copy_host_auth_file()
        if self._mcp_server is not None:
            self._register_mcp_with_codex()
            self._mcp_health_check_from_container()

    def _register_mcp_with_codex(self) -> None:
        """Write an MCP server entry into ``$CODEX_HOME/config.toml``.

        Codex CLI reads streamable-HTTP MCP server definitions from
        ``[mcp_servers.<name>]`` blocks. For bearer auth it does NOT
        accept the token inline; instead it expects
        ``bearer_token_env_var = "<NAME>"`` and reads the actual secret
        from that environment variable at runtime. The env var is
        exported by ``_wrap_in_shell`` (``INVERSE_CODEX_MCP_TOKEN``) so
        codex inherits it when the helper launches it.

        Verified schema with `codex mcp add --url ... --bearer-token-env-var ...`
        on codex-cli 0.128.0; bump this comment if a future version
        changes the keys.
        """
        url = self._mcp_server.container_base_url + self._mcp_server.mcp_path
        config_toml = (
            "# Auto-generated by CodexInverseStrategyAgent. Do not edit by hand.\n"
            "[mcp_servers.inverse-codex]\n"
            f'url = "{url}"\n'
            'bearer_token_env_var = "INVERSE_CODEX_MCP_TOKEN"\n'
        )
        create_file_in_container(
            self.environment,
            content=config_toml,
            dest_path=f"{CODEX_HOME_PATH}/config.toml",
        )
        self.logger.info(f"Registered MCP server with codex CLI at {url}")

    def _mcp_health_check_from_container(self) -> None:
        """Ping ``/healthz`` from inside the learner container.

        Catches misconfigured networking (e.g., missing
        ``host.docker.internal`` host-gateway on Linux) before the agent
        spends a real round on a Codex run that can't reach MCP. Uses
        ``curl`` if present, falls back to ``wget``; if neither is
        available we skip the check rather than fail the whole round.
        """
        url = self._mcp_server.container_base_url + "/healthz"
        # Retry-on-transient-failure: under parallel=N pool runs the host
        # gateway can be briefly congested when containers come up in
        # bursts. 15 attempts × 3s delay × 10s max-time → ~3 min worst-case.
        cmd = (
            f"if command -v curl >/dev/null 2>&1; then "
            f"  curl -fsS --retry 15 --retry-delay 3 --retry-connrefused --max-time 10 {shlex.quote(url)}; "
            f"elif command -v wget >/dev/null 2>&1; then "
            f"  for i in $(seq 1 15); do wget -q --tries=1 --timeout=10 -O - {shlex.quote(url)} && break || sleep 3; done; "
            f"else "
            f"  echo 'no http client; skipping MCP health check' >&2; exit 0; "
            f"fi"
        )
        result = self.environment.execute(cmd)
        if result.get("returncode", 0) != 0:
            raise RuntimeError(
                f"MCP health check failed from learner container: cannot reach "
                f"{url}. Output: {result.get('output', '').strip()[:500]}"
            )
        self.logger.info(
            f"MCP health check OK from container ({self._mcp_server.container_base_url})"
        )

    def _resolve_auth_path(self) -> Path | None:
        """Return the host path to auth.json, or None if disabled/missing.

        Honours the same `auth_file: null` opt-out and explicit-path
        rules as `_copy_host_auth_file` (the source-of-truth there);
        this is a read-only resolver used by both auth-copy and
        credential-redaction setup.
        """
        auth_cfg_present = "auth_file" in self._codex_cfg
        configured_path = self._codex_cfg.get("auth_file", DEFAULT_HOST_AUTH_FILE)
        if auth_cfg_present and configured_path is None:
            return None
        host_path = Path(os.path.expanduser(os.path.expandvars(configured_path)))
        return host_path if host_path.exists() else None

    def _load_auth_secrets(self) -> tuple[list[str], list[str]]:
        """Read the host auth.json and return (key_names, redactable_values).

        - ``key_names``: top-level dict keys, for audit logging /
          metadata. Lets us record "the agent had access to credentials
          named X, Y, Z" without writing the secret values themselves.
        - ``redactable_values``: every string value (recursively) that
          is plausibly a secret — long enough that an accidental match
          on a short identifier like ``"openai"`` is unlikely. Applied
          to ``stdout_tail`` and ``last_message`` before persisting to
          disk, as a last-line defence against codex's own shell tool
          accidentally cat-ing or echoing the file.

        Returns ``([], [])`` when auth is disabled, the file is missing,
        or the file isn't valid JSON. We never fail agent init over a
        bad auth file here — `_copy_host_auth_file` handles the harder
        error cases (missing explicit path raises there).
        """
        auth_path = self._resolve_auth_path()
        if auth_path is None:
            return [], []
        try:
            data = json.loads(auth_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            self.logger.warning(
                f"Could not parse {auth_path} for credential redaction: {e}; "
                f"trajectories will not be scrubbed for known token values."
            )
            return [], []

        keys: list[str] = list(data.keys()) if isinstance(data, dict) else []
        values: list[str] = []

        def collect(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    collect(v)
            elif isinstance(obj, list):
                for item in obj:
                    collect(item)
            elif isinstance(obj, str) and len(obj) >= 12:
                # 12-char threshold filters out short identifiers like
                # "openai", "gpt-5-mini" while keeping API keys, JWTs,
                # session tokens, refresh tokens, etc.
                values.append(obj)

        collect(data)
        # Longest-first so we redact the full secret before any prefix
        # of it (e.g. an access_token that happens to start with the
        # same chars as a shorter identifier).
        values.sort(key=len, reverse=True)
        return keys, values

    def _redact(self, value):
        """Recursively replace any known auth secret in strings with '[REDACTED]'.

        Walks dicts and lists; leaves non-string scalars alone. Used as
        the last-line defence applied to ``last_message`` and ``events``
        before they hit the trajectory file. No-op when the redaction
        list is empty.
        """
        if not self._auth_redactable:
            return value
        if isinstance(value, str):
            for secret in self._auth_redactable:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {k: self._redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        return value

    def _copy_host_auth_file(self) -> None:
        """Copy host Codex auth.json into CODEX_HOME (if configured).

        Authentication flow: user runs `codex login` on the host once,
        which writes credentials to `~/.codex/auth.json`. We copy that
        file into the container so unattended `codex exec` can use it.

        Behavior:
        - `auth_file` unset: use ``~/.codex/auth.json`` if present,
          warn-and-skip if not.
        - `auth_file` set to a path: copy it; raise if the file is missing.
        - `auth_file: null`: skip auth setup entirely (assume API-key env
          var is propagated into the container some other way).
        """
        # `null` in YAML becomes Python None; "unset" keeps the default.
        auth_cfg_present = "auth_file" in self._codex_cfg
        configured_path = self._codex_cfg.get("auth_file", DEFAULT_HOST_AUTH_FILE)
        if auth_cfg_present and configured_path is None:
            return

        host_path = Path(os.path.expanduser(os.path.expandvars(configured_path)))
        if not host_path.exists():
            if auth_cfg_present:
                raise FileNotFoundError(
                    f"agent {self.name!r}: codex auth_file {host_path} not found. "
                    "Run `codex login` on the host or set `config.codex.auth_file: null` "
                    "and propagate OPENAI_API_KEY into the container instead."
                )
            self.logger.warning(
                f"Codex auth file {host_path} not found; skipping auth copy. "
                "If the container does not have an API key in its env, "
                "`codex exec` will fail at request time."
            )
            return

        dest_path = f"{CODEX_HOME_PATH}/auth.json"
        copy_to_container(self.environment, host_path, dest_path)
        # Defense-in-depth: restrict to the codex CLI's user. Same-user
        # tool subprocesses can still read it (see CODEX_AUTH discussion
        # in the plan), but world/group reads are gone.
        self.environment.execute(f"chmod 600 {shlex.quote(dest_path)}")
        self.logger.info(f"Copied codex auth from {host_path} into container CODEX_HOME (mode 600)")

    def _check_submitted_marker(self) -> str | None:
        """Return 'submitted' if the marker file exists, else None.

        The MCP `submit()` tool writes this marker. ``_classify_submission``
        is the canonical place that consumes this — callers should
        usually compare ``self._check_submitted_marker() is not None``.
        """
        result = self.environment.execute(f"test -f {shlex.quote(SUBMIT_MARKER_PATH)}")
        return "submitted" if result.get("returncode") == 0 else None

    def _max_round_seconds(self) -> int | None:
        """Per-round wall-clock budget enforced via container exec timeout."""
        value = self._codex_cfg.get("max_round_seconds")
        return int(value) if value is not None else None

    def _read_container_file(self, path: str) -> str | None:
        """Best-effort cat of a file inside the learner container."""
        result = self.environment.execute(f"cat {shlex.quote(path)} 2>/dev/null")
        if result.get("returncode") != 0:
            return None
        return result.get("output")

    # ------------------------------------------------------------------ #
    # Prompt rendering.
    # ------------------------------------------------------------------ #

    def _render_round_prompt(self, *, round_recovery_note: dict | None = None) -> str:
        """Render the round prompt by combining the agent-config templates
        with GameContext template vars.

        Mirrors mini-swe-agent's pattern: `system_template` /
        `instance_template` come from the agent config slot
        (`players[].config.agent`), `game_description` comes from
        `game_context.prompts`. Both sources are merged into the Jinja
        render context so the templates can reference either.

        `round_recovery_note` is an optional dict from
        `build_round_transition_summary` — when set, it's prepended to
        signal that we're recovering from a timed-out round.
        """
        tpl = self.game_context.to_template_vars()
        agent_cfg = self.config.get("config", {}).get("agent", {})
        ctx = {**agent_cfg, **tpl}

        sections: list[str] = []
        if round_recovery_note is not None:
            sections.append(
                "[Note: the previous round's session timed out. We are "
                "restarting this round with a fresh Codex session.]\n"
                + render_transition_summary(self.game_context.round, round_recovery_note)
            )
        for key in ("system_template", "instance_template"):
            raw = agent_cfg.get(key)
            if raw:
                rendered = Template(str(raw), undefined=StrictUndefined).render(**ctx)
                sections.append(rendered.rstrip())
        if not sections:
            raise RuntimeError(
                f"agent {self.name!r}: no system_template / instance_template "
                "found under config.agent — check Codex prompt YAML."
            )
        return "\n\n".join(sections) + "\n"

    # ------------------------------------------------------------------ #
    # Trajectory + metadata persistence.
    # ------------------------------------------------------------------ #

    def _round_probe_count(self) -> int:
        """Authoritative probe count for the just-finished round.

        For codex, ``run_probe()`` invocations live on the MCP server's
        per-round state, not on the agent. We snapshot the count from
        ``mcp_server.end_round()``; falling back to ``self._probe_count``
        keeps unit tests that don't set up an MCP server working.
        """
        if self._mcp_server is None:
            return self._probe_count
        summary = self._mcp_server.end_round() or {}
        return int(summary.get("probes_used", 0))

    def _save_round_artifacts(self, *, round_num: int, outcome: dict) -> None:
        """Write the round trajectory JSON and update agent_stats.

        Schema is intentionally Codex-shaped (not mini-swe `messages[]`).
        Downstream readers must check `backend == "codex"` before
        attempting to parse it like a mini-swe trajectory.
        """
        traj_path = (
            self.game_context.log_local
            / "players"
            / self.name
            / f"{self.name}_r{round_num}.traj.json"
        )
        traj_path.parent.mkdir(parents=True, exist_ok=True)

        probe_count = self._round_probe_count()

        traj = {
            "backend": "codex",
            "round": round_num,
            "exit_status": outcome["exit_status"],
            "submission_status": outcome["submission_status"],
            "wall_clock_seconds": outcome["wall_clock_seconds"],
            "probe_count": probe_count,
            "codex_home": CODEX_HOME_PATH,
            "resume_mode": outcome["resume_mode"],
            "model": self._codex_cfg.get("model"),
            "sandbox": self._codex_cfg.get("sandbox", "workspace-write"),
            # Token tallies parsed from the JSONL stream. `turns_completed=0`
            # means the round was cut short (timeout / fatal error) before
            # codex could emit a `turn.completed` event — real usage is
            # almost certainly non-zero in that case but unrecorded.
            "usage": outcome["usage"],
            # Codex's `--json` event stream, parsed into structured
            # objects so analysis tooling and human readers don't have
            # to dig through escaped JSONL inside a JSON string.
            # Non-JSON lines (rare, e.g. "Reading prompt from stdin...")
            # appear as ``{"_kind": "raw_line", "text": ...}``.
            # Credential redaction (see `_load_auth_secrets`) walks
            # the structure recursively before it lands on disk.
            "last_message": self._redact(outcome["last_message"]),
            "events": self._redact(outcome["events"]),
        }
        # ensure_ascii=False so Unicode (typographic apostrophes,
        # accented characters, etc. that codex commonly emits) lands as
        # UTF-8 in the file rather than `\uXXXX` escape sequences.
        traj_path.write_text(json.dumps(traj, indent=2, ensure_ascii=False))

        copy_to_container(
            self.environment,
            traj_path,
            self.game_context.log_env / "edits" / traj_path.name,
        )

        # `cost: null` / `api_calls: null` are explicit so downstream
        # scripts that key on field presence stay stable across backends.
        self._metadata.setdefault("agent_stats", {})[round_num] = {
            "exit_status": outcome["exit_status"],
            "submission_status": outcome["submission_status"],
            "wall_clock_seconds": outcome["wall_clock_seconds"],
            "probe_count": probe_count,
            "resume_mode": outcome["resume_mode"],
            "usage": outcome["usage"],
            "cost": None,
            "api_calls": None,
        }
        self._metadata["inverse_strategy"]["evaluation_history"].append(
            {
                "round": round_num,
                "exit_status": outcome["exit_status"],
                "probe_count": probe_count,
            }
        )
