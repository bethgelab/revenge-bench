"""Drift/parity test: Harbor ``instruction.md`` is the harbor-route render of the
shared inverse-strategy prompt templates.

The Harbor inverse-strategy task text is generated from the *same* prompt
templates the native ``inverse_codex`` learner uses, via the shared
:func:`revenge_bench.agents.utils.render_prompt_sections`, selecting the
``route="harbor"`` branch. This test guards three things:

1. **Drift** — the committed ``harbor/tasks/<task>/instruction.md``
   equals a fresh :func:`render_task_instruction`. If someone edits the prompt
   YAML (or the instruction) without regenerating, this fails, exactly like the
   ``offline_eval`` byte-identity guard.
2. **Provenance** — the render is produced by the same section-rendering helper
   the native ``_render_round_prompt`` calls, over a real ``GameContext`` built
   from the same ``configs/prompts/codex`` sources, so the Harbor instruction
   cannot silently diverge from the shared prompt content.
3. **Route branch** — the shared templates branch on ``route``: the codex loop
   (multi-round, ``/logs/rounds`` traces, MCP ``run_probe``) for ``codex`` vs the
   single-session Harbor mechanics (``sudo run_probe``, ``/workspace``,
   ``probe_trace_*.json``) for ``harbor``, with the game description + scorer
   core identical across both.
"""

from __future__ import annotations

import yaml

from revenge_bench.agents.utils import GameContext, render_prompt_sections
from revenge_bench.harbor.prompt import (
    CODEX_SYSTEM_PROMPT,
    HARBOR_TASK_GAMES,
    instruction_path,
    render_codex_instruction,
    render_task_instruction,
)
from revenge_bench.paths import CONFIG_DIR


def test_committed_instruction_is_not_stale():
    """The committed instruction.md must equal a fresh render (no drift)."""
    for task in HARBOR_TASK_GAMES:
        path = instruction_path(task)
        assert path.exists(), f"missing {path}"
        assert path.read_text() == render_task_instruction(task), (
            f"{path} is stale — regenerate with "
            f"`python -m revenge_bench.harbor.prompt {task}`"
        )


def test_render_matches_native_section_rendering():
    """The Harbor render equals the shared section rendering on the harbor route.

    Rebuilds the render the way ``_render_round_prompt`` does — the same
    ``render_prompt_sections`` over the same ``config.agent`` templates and a
    real ``GameContext.to_template_vars()`` — but with ``route="harbor"``, and
    asserts equality with the Harbor helper's output. This proves the Harbor
    instruction is produced by the shared renderer over a real ``GameContext``
    (same provenance as the native path), differing only by the ``route`` flag.
    """
    game = HARBOR_TASK_GAMES["battlesnake-gpt5-9aa3-v0"]
    agent_cfg = yaml.safe_load(CODEX_SYSTEM_PROMPT.read_text())
    prompts = yaml.safe_load(
        (CONFIG_DIR / "prompts" / "codex" / "games" / f"{game}.yaml").read_text()
    )
    gc = GameContext(
        id=game,
        log_env="/logs",
        log_local="/logs",
        name="learner",
        player_id="learner",
        prompts=prompts,
        round=1,
        rounds=1,
        working_dir="/workspace",
        context_mode="persistent",
        route="harbor",
    )
    expected = "\n\n".join(render_prompt_sections(agent_cfg, gc.to_template_vars())) + "\n"

    assert render_codex_instruction(game) == expected


def test_render_contains_harbor_route_content():
    """Sanity: the render carries the shared core + the harbor-route mechanics."""
    text = render_task_instruction("battlesnake-gpt5-9aa3-v0")
    assert text.endswith("\n")
    # Shared problem/scorer core (identical across routes).
    assert "recover another agent's strategy from game traces" in text
    assert "## Strategy Recovery Guidelines" in text
    assert "recover another agent's BattleSnake strategy" in text
    # Harbor-route mechanics (single session, sudo run_probe, /workspace paths).
    assert "sudo run_probe" in text
    assert "probe_trace_{N}.json" in text
    assert "/workspace/.probe_budget" in text
    assert "rounds/0/traces.json" in text
    assert "rounds/0/opp_*/sim_*.jsonl" in text
    assert "### traces.json Format" in text
    assert '"mean_distance"' in text
    assert '"nonzero_distances"' in text
    assert '"learner_action"' in text
    assert '"target_action"' in text
    assert "evidence, not final" in text
    assert "fresh hidden target traces" in text
    assert "graded once" in text
    assert "stub" not in text.lower()
    assert "NO\n  `traces.json`" not in text
    # Codex-route loop language must NOT leak into the harbor instruction.
    assert "/logs/rounds/" not in text
    assert "README_agent.md" not in text
    assert "run_probe` MCP tool" not in text
    assert "This is round" not in text


def test_route_flag_branches_between_codex_and_harbor():
    """The shared templates branch on ``route``: codex loop vs harbor session.

    Guards the single-source parameterization — the same YAML renders the native
    multi-round Codex loop for ``route="codex"`` and the single-session Harbor
    mechanics for ``route="harbor"``, with the game description + scorer core
    identical in both.
    """
    game = HARBOR_TASK_GAMES["battlesnake-gpt5-9aa3-v0"]
    codex = render_codex_instruction(game, route="codex")
    harbor = render_codex_instruction(game, route="harbor")

    assert codex != harbor

    # Codex-only loop/tool/path language.
    assert "/logs/rounds/" in codex
    assert "run_probe` MCP tool" in codex
    assert "traces.json" in codex
    assert "/logs/rounds/" not in harbor
    assert "rounds/0/traces.json" in harbor
    assert "### traces.json Format" in harbor
    assert "README_agent.md" not in harbor
    assert "run_probe` MCP tool" not in harbor

    # README_agent.md is a codex reset-mode feature; absent on the harbor route.
    codex_reset = render_codex_instruction(game, route="codex", context_mode="reset")
    assert "README_agent.md" in codex_reset

    # Harbor-only single-session mechanics.
    assert "sudo run_probe" in harbor
    assert "rounds/0/opp_*/sim_*.jsonl" in harbor
    assert "graded once" in harbor
    assert "sudo run_probe" not in codex

    # Shared core present in both, byte-for-byte.
    for shared in (
        "## The Game: BattleSnake",
        "## Strategy Recovery Guidelines",
        "recover another agent's BattleSnake strategy",
    ):
        assert shared in codex
        assert shared in harbor


def test_halite_render_contains_harbor_route_content():
    """Halite Harbor render uses Halite file surfaces and route mechanics."""
    text = render_task_instruction("halite-gpt5-9aa3-v0")
    assert text.endswith("\n")
    assert "recover another agent's Halite strategy" in text
    assert "## The Game: Halite" in text
    assert "sudo run_probe" in text
    assert "probe_trace_{N}.json" in text
    assert "/workspace/.probe_budget" in text
    assert "submission/" in text
    assert "probe/" in text
    assert "rounds/0/traces.json" in text
    assert "rounds/0/opp_*/sim_*.hlt" in text
    assert "[[2, 3, 0], [4, 5, 1]]" in text
    assert "fresh hidden target traces" in text
    assert "graded once" in text
    assert "/logs/rounds/" not in text
    assert "run_probe` MCP tool" not in text
    assert "main.py" not in text
    assert "probe.py" not in text
    assert "sim_*.jsonl" not in text


def test_robotrumble_render_contains_harbor_route_content():
    """RobotRumble Harbor render uses RobotRumble file surfaces and route mechanics."""
    text = render_task_instruction("robotrumble-gpt5-9aa3-v0")
    assert text.endswith("\n")
    assert "recover another agent's RobotRumble strategy" in text
    assert "## The Game: RobotRumble" in text
    assert "sudo run_probe" in text
    assert "probe_trace_{N}.json" in text
    assert "/workspace/.probe_budget" in text
    assert "robot.js" in text
    assert "probe.js" in text
    assert "rounds/0/traces.json" in text
    assert "rounds/0/opp_*/sim_*.json" in text
    assert "fresh hidden target traces" in text
    assert "graded once" in text
    assert "/logs/rounds/" not in text
    assert "run_probe` MCP tool" not in text
    assert "stub" not in text.lower()


def test_robocode_render_contains_harbor_route_content():
    """RoboCode Harbor render uses RoboCode file surfaces and route mechanics."""
    text = render_task_instruction("robocode-gpt5-9aa3-v0")
    assert text.endswith("\n")
    assert "recover another agent's RoboCode strategy" in text
    assert "## The Game: RoboCode" in text
    assert "sudo run_probe" in text
    assert "probe_trace_{N}.json" in text
    assert "/workspace/.probe_budget" in text
    assert "main.py" in text
    assert "move(state)" in text
    assert "robots/custom" in text
    assert "probe/" in text
    assert "rounds/0/traces.json" in text
    assert "rounds/0/opp_*/record_*.xml" in text
    assert "fresh hidden target traces" in text
    assert "graded once" in text
    assert "/logs/rounds/" not in text
    assert "run_probe` MCP tool" not in text
    assert "stub" not in text.lower()


def test_huskybench_render_contains_harbor_route_content():
    """HuskyBench Harbor render uses poker file surfaces and route mechanics."""
    text = render_task_instruction("huskybench-gpt5-9aa3-v0")
    assert text.endswith("\n")
    assert "recover another agent's poker strategy" in text
    assert "## The Game: HuskyBench (Poker)" in text
    assert "sudo run_probe" in text
    assert "probe_trace_{N}.json" in text
    assert "client/player.py" in text
    assert "probe/client/player.py" in text
    assert "rounds/0/traces.json" in text
    assert "rounds/0/opp_*/game_log_*.json" in text
    assert '"CALL"' in text
    assert '"RAISE:0.2500"' in text
    assert "fresh hidden target traces" in text
    assert "graded once" in text
    assert "/logs/rounds/" not in text
    assert "run_probe` MCP tool" not in text
    assert "sim_*.jsonl" not in text
    assert "main.py" not in text
    assert "chase food" not in text
    assert "stub" not in text.lower()
