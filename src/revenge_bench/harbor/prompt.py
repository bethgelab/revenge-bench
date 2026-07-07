"""Single-source prompt rendering for the Harbor route.

The Harbor inverse-strategy task text (``instruction.md``) is rendered from the
**same** Codex prompt templates the native ``inverse_codex`` learner uses:

- ``configs/prompts/codex/system.yaml`` — ``system_template`` + ``instance_template``
- ``configs/prompts/codex/games/<game>.yaml`` — ``game_description``

Both routes share :func:`revenge_bench.agents.utils.render_prompt_sections` and
the real :class:`~revenge_bench.agents.utils.GameContext`, so the Harbor
instruction cannot drift from the native Codex round prompt. A drift test
(``tests/harbor/test_prompt_parity.py``) asserts the committed ``instruction.md``
equals a fresh render, mirroring the ``offline_eval`` parity approach.

Route-specific *mechanical* differences (single container vs. multi-round
sessions, ``sudo run_probe`` vs. the MCP ``run_probe`` tool, ``/workspace``
paths vs. ``/logs/rounds``) are handled by the shared templates' ``route``
branch: the Harbor generator renders with ``route="harbor"`` while the native
learner renders with ``route="codex"``. The game description and scorer
semantics stay identical across both routes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from revenge_bench.agents.utils import GameContext, render_prompt_sections
from revenge_bench.paths import CONFIG_DIR, REPO_ROOT

# Codex prompt sources (the single source of truth shared with the native path).
CODEX_SYSTEM_PROMPT = CONFIG_DIR / "prompts" / "codex" / "system.yaml"
CODEX_GAME_PROMPT_DIR = CONFIG_DIR / "prompts" / "codex" / "games"

# Harbor task directory name -> Codex game-prompt stem.
HARBOR_TASK_GAMES: dict[str, str] = {
    "battlesnake-gpt5-9aa3-v0": "battlesnake",
    "halite-gpt5-9aa3-v0": "halite",
    "robotrumble-gpt5-9aa3-v0": "robotrumble",
    "robocode-gpt5-9aa3-v0": "robocode",
    "huskybench-gpt5-9aa3-v0": "huskybench",
}

# Harbor is a single continuous container session (the agent's conversation
# history persists), so we render the Codex prompt's "persistent" branch for a
# single round, on the "harbor" route. The route flag flips the shared templates
# from the multi-round Codex loop (traces.json feedback, /logs/rounds, MCP
# run_probe) to the single-session Harbor mechanics (sudo run_probe, /workspace,
# probe_trace_*.json) while keeping the game description + scorer core identical.
DEFAULT_PLAYER_ID = "learner"
DEFAULT_WORKING_DIR = "/workspace"
DEFAULT_CONTEXT_MODE = "persistent"
DEFAULT_ROUTE = "harbor"
DEFAULT_ROUND = 1
DEFAULT_ROUNDS = 1


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"expected a mapping at {path}, got {type(data).__name__}")
    return data


def render_codex_instruction(
    game: str,
    *,
    player_id: str = DEFAULT_PLAYER_ID,
    working_dir: str = DEFAULT_WORKING_DIR,
    context_mode: str = DEFAULT_CONTEXT_MODE,
    route: str = DEFAULT_ROUTE,
    round: int = DEFAULT_ROUND,
    rounds: int = DEFAULT_ROUNDS,
    config_dir: Path = CONFIG_DIR,
) -> str:
    """Render the inverse-strategy learner prompt for *game* as plain text.

    Reuses the real :class:`GameContext` (variable computation) and
    :func:`render_prompt_sections` (template rendering), reading the same Codex
    ``system.yaml`` / ``games/<game>.yaml`` the native path consumes, then joins
    the sections exactly as ``CodexInverseStrategyAgent._render_round_prompt``.

    ``route`` selects which branch of the shared templates renders: ``"codex"``
    (native multi-round loop) or ``"harbor"`` (single-session container). Only
    the loop/tool/path sentences differ; the game description and scorer
    semantics are identical across routes.
    """
    system_prompt_path = config_dir / "prompts" / "codex" / "system.yaml"
    game_prompt_path = config_dir / "prompts" / "codex" / "games" / f"{game}.yaml"

    agent_cfg = _load_yaml(system_prompt_path)
    prompts = _load_yaml(game_prompt_path)

    game_context = GameContext(
        id=game,
        log_env=Path("/logs"),
        log_local=Path("/logs"),
        name=player_id,
        player_id=player_id,
        prompts=prompts,
        round=round,
        rounds=rounds,
        working_dir=working_dir,
        context_mode=context_mode,
        route=route,
    )

    sections = render_prompt_sections(agent_cfg, game_context.to_template_vars())
    if not sections:
        raise RuntimeError(
            f"no system_template / instance_template found in {system_prompt_path}"
        )
    return "\n\n".join(sections) + "\n"


def instruction_path(task: str, *, harbor_root: Path = REPO_ROOT / "harbor") -> Path:
    """Return the ``instruction.md`` path for a Harbor *task* directory."""
    return harbor_root / "tasks" / task / "instruction.md"


def render_task_instruction(task: str, *, config_dir: Path = CONFIG_DIR, **kwargs) -> str:
    """Render the Codex-identical instruction for a Harbor *task* directory."""
    try:
        game = HARBOR_TASK_GAMES[task]
    except KeyError:
        raise KeyError(
            f"unknown Harbor task {task!r}; known tasks: "
            f"{sorted(HARBOR_TASK_GAMES)}"
        ) from None
    return render_codex_instruction(game, config_dir=config_dir, **kwargs)


def generate_instruction(
    task: str = "battlesnake-gpt5-9aa3-v0",
    *,
    harbor_root: Path = REPO_ROOT / "harbor",
    config_dir: Path = CONFIG_DIR,
    write: bool = True,
) -> str:
    """Render (and optionally write) a task's ``instruction.md``.

    Returns the rendered text. When ``write`` is true the text is written to
    ``harbor/tasks/<task>/instruction.md``.
    """
    text = render_task_instruction(task, config_dir=config_dir)
    if write:
        dest = instruction_path(task, harbor_root=harbor_root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    return text


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task",
        nargs="?",
        default="battlesnake-gpt5-9aa3-v0",
        choices=sorted(HARBOR_TASK_GAMES),
        help="Harbor task directory to (re)generate instruction.md for.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if instruction.md is stale.",
    )
    args = parser.parse_args(argv)

    rendered = render_task_instruction(args.task)
    dest = instruction_path(args.task)
    if args.check:
        current = dest.read_text() if dest.exists() else None
        if current != rendered:
            print(f"STALE: {dest} is out of date; run `python -m "
                  f"revenge_bench.harbor.prompt {args.task}` to regenerate.")
            return 1
        print(f"OK: {dest} is up to date.")
        return 0

    generate_instruction(args.task, write=True)
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(_main())
