"""Harbor-only prompt rendering.

The native benchmark prompt files stay untouched. Harbor keeps its own prompt
snapshots under ``revenge_bench/harbor/prompts`` and renders them with a small
local Jinja helper. This intentionally duplicates the native renderer shape so
Harbor task text can evolve without changing the main Codex pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from jinja2 import StrictUndefined, Template

from revenge_bench.agents.utils import GameContext
from revenge_bench.paths import REPO_ROOT

# Harbor prompt sources. They intentionally live under the Harbor package rather
# than configs/prompts/codex so native prompt files remain main-pipeline-owned.
HARBOR_PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "codex"
HARBOR_SYSTEM_PROMPT = HARBOR_PROMPT_DIR / "system.yaml"
HARBOR_GAME_PROMPT_DIR = HARBOR_PROMPT_DIR / "games"

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


def render_prompt_sections(agent_cfg: dict, template_vars: dict) -> list[str]:
    """Render Harbor ``system_template`` / ``instance_template`` sections."""
    ctx = {**agent_cfg, **template_vars}
    sections: list[str] = []
    for key in ("system_template", "instance_template"):
        raw = agent_cfg.get(key)
        if raw:
            rendered = Template(str(raw), undefined=StrictUndefined).render(**ctx)
            sections.append(rendered.rstrip())
    return sections


def render_codex_instruction(
    game: str,
    *,
    player_id: str = DEFAULT_PLAYER_ID,
    working_dir: str = DEFAULT_WORKING_DIR,
    context_mode: str = DEFAULT_CONTEXT_MODE,
    route: str = DEFAULT_ROUTE,
    round: int = DEFAULT_ROUND,
    rounds: int = DEFAULT_ROUNDS,
    prompt_dir: Path = HARBOR_PROMPT_DIR,
) -> str:
    """Render the inverse-strategy learner prompt for *game* as plain text.

    ``route`` selects which branch of the Harbor-owned templates renders:
    ``"codex"`` is kept only for drift tests; production task generation uses
    ``"harbor"``.
    """
    system_prompt_path = prompt_dir / "system.yaml"
    game_prompt_path = prompt_dir / "games" / f"{game}.yaml"

    agent_cfg = _load_yaml(system_prompt_path)
    prompts = _load_yaml(game_prompt_path)

    game_context = GameContext(
        id=game,
        log_env=Path("/logs"),
        log_local=Path("/logs"),
        name=player_id,
        player_id=player_id,
        prompts={},
        round=round,
        rounds=rounds,
        working_dir=working_dir,
        context_mode=context_mode,
    )

    template_vars = game_context.to_template_vars()
    template_vars["route"] = route
    for key, raw in prompts.items():
        template_vars[key] = Template(str(raw), undefined=StrictUndefined).render(
            **template_vars
        )
    sections = render_prompt_sections(agent_cfg, template_vars)
    if not sections:
        raise RuntimeError(
            f"no system_template / instance_template found in {system_prompt_path}"
        )
    return "\n\n".join(sections) + "\n"


def instruction_path(task: str, *, harbor_root: Path = REPO_ROOT / "harbor") -> Path:
    """Return the ``instruction.md`` path for a Harbor *task* directory."""
    return harbor_root / "tasks" / task / "instruction.md"


def game_for_task(task: str) -> str:
    """Return the Codex game-prompt stem for a pilot or materialized task name."""
    if task in HARBOR_TASK_GAMES:
        return HARBOR_TASK_GAMES[task]
    game = task.split("-", 1)[0]
    if game in set(HARBOR_TASK_GAMES.values()):
        return game
    raise KeyError(
        f"unknown Harbor task {task!r}; expected a pilot task or a canonical "
        f"task name starting with one of {sorted(set(HARBOR_TASK_GAMES.values()))}"
    )


def render_task_instruction(
    task: str, *, prompt_dir: Path = HARBOR_PROMPT_DIR, **kwargs
) -> str:
    """Render the Codex-identical instruction for a Harbor *task* directory."""
    game = game_for_task(task)
    return render_codex_instruction(game, prompt_dir=prompt_dir, **kwargs)


def generate_instruction(
    task: str = "battlesnake-gpt5-9aa3-v0",
    *,
    harbor_root: Path = REPO_ROOT / "harbor",
    prompt_dir: Path = HARBOR_PROMPT_DIR,
    write: bool = True,
) -> str:
    """Render (and optionally write) a task's ``instruction.md``.

    Returns the rendered text. When ``write`` is true the text is written to
    ``harbor/tasks/<task>/instruction.md``.
    """
    text = render_task_instruction(task, prompt_dir=prompt_dir)
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
