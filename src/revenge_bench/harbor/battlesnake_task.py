"""BattleSnake Harbor task helpers shared with the native benchmark path.

The native full-pool benchmark expands one YAML config into many target
tournaments. A Harbor task is one fixed target instance, so this module resolves
``config + target_index`` to the exact target and opponent set that the normal
path would use.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from revenge_bench.paths import CONFIG_DIR, REPO_ROOT
from revenge_bench.strategy_pool import StrategyPool
from revenge_bench.utils.yaml_utils import resolve_includes


@dataclass(frozen=True)
class BattleSnakeHarborInstance:
    """A single Harbor task instance resolved from a normal benchmark config."""

    benchmark_config: str
    target_index: int
    target_name: str
    target_path: str
    opponents: list[str]
    opponents_per_round: int
    sims_per_round: int
    width: int
    height: int
    seed: int | None
    top_elo_targets: int | None


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_config(config_path: Path) -> dict[str, Any]:
    text = config_path.read_text()
    data = yaml.safe_load(resolve_includes(text, base_dir=CONFIG_DIR))
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping config at {config_path}")
    return data


def _resolve_repo_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def resolve_instance(config_path: Path, target_index: int) -> BattleSnakeHarborInstance:
    """Resolve one Harbor BattleSnake instance using normal-path pool rules."""

    config_path = _resolve_repo_path(config_path)
    config = _load_config(config_path)
    pool_config = config.get("strategy_pool")
    if not isinstance(pool_config, dict):
        raise ValueError(f"No strategy_pool section in {config_path}")

    game_name = config["game"]["name"]
    if game_name != "BattleSnake":
        raise ValueError(f"expected BattleSnake config, got {game_name!r}")

    target_pool_dir = _resolve_repo_path(pool_config["pool_dir"])
    opponent_pool_dir = _resolve_repo_path(
        pool_config.get("opponent_pool_dir", pool_config["pool_dir"])
    )
    target_filter = pool_config.get("target_filter", {})
    opponent_filter = pool_config.get("opponent_filter", {})

    target_pool = StrategyPool(target_pool_dir, game_name, filters=target_filter)
    if opponent_pool_dir == target_pool_dir and opponent_filter == target_filter:
        opponent_pool = target_pool
    else:
        opponent_pool = StrategyPool(
            opponent_pool_dir, game_name, filters=opponent_filter
        )

    if pool_config.get("target_names") is not None:
        name_set = set(pool_config["target_names"])
        targets = [s for s in target_pool.strategies if s.name in name_set]
    elif pool_config.get("top_elo_targets") is not None:
        targets = target_pool.top_by_elo(int(pool_config["top_elo_targets"]))
    elif pool_config.get("num_targets") is not None:
        targets = target_pool.sample(
            int(pool_config["num_targets"]), seed=pool_config.get("seed")
        )
    else:
        targets = target_pool.strategies

    if target_index < 0 or target_index >= len(targets):
        raise IndexError(
            f"target_index {target_index} outside selected target range 0..{len(targets) - 1}"
        )
    target = targets[target_index]

    tournament_config = config.get("tournament", {})
    opponents_per_round = int(tournament_config.get("opponents_per_round", 1))
    sampling_seed = pool_config.get("seed")
    available = [
        s for s in opponent_pool.strategies if s.resolve() != target.resolve()
    ]
    if not available:
        raise RuntimeError(
            f"Opponent pool contains only target {target.name!r}; add another strategy."
        )
    rng_seed = sampling_seed + target_index if sampling_seed is not None else None
    opponents = random.Random(rng_seed).sample(
        available, min(opponents_per_round, len(available))
    )

    game_config = config.get("game", {})
    game_args = game_config.get("args", {})

    return BattleSnakeHarborInstance(
        benchmark_config=_repo_relative(config_path),
        target_index=target_index,
        target_name=target.name,
        target_path=_repo_relative(target),
        opponents=[_repo_relative(p) for p in opponents],
        opponents_per_round=opponents_per_round,
        sims_per_round=int(game_config.get("sims_per_round", 20)),
        width=int(game_args.get("width", 11)),
        height=int(game_args.get("height", 11)),
        seed=sampling_seed,
        top_elo_targets=pool_config.get("top_elo_targets"),
    )


def read_task_config(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "task_config.json"
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def resolve_task_instance(task_dir: Path) -> BattleSnakeHarborInstance:
    data = read_task_config(task_dir)
    return resolve_instance(
        Path(data["benchmark_config"]), int(data.get("target_index", 0))
    )


def write_resolved_metadata(task_dir: Path) -> BattleSnakeHarborInstance:
    instance = resolve_task_instance(task_dir)
    path = task_dir / "resolved_task.json"
    path.write_text(json.dumps(asdict(instance), indent=2) + "\n")
    return instance


def stage_build_context(task_dir: Path) -> BattleSnakeHarborInstance:
    """Stage the selected target/opponents and task metadata.

    The target goes into the Docker build context because the agent must be able
    to probe a sealed target during its work session. The sampled opponent pool
    also goes into the build context, but it is sealed root-only after trace
    generation. The learner sees only the generated target-vs-opponent traces,
    matching the normal task setup.
    """

    instance = write_resolved_metadata(task_dir)
    staging = task_dir / "environment" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task_dir / "instruction.md", staging / "instruction.md")
    (staging / "resolved_task.json").write_text(
        json.dumps(asdict(instance), indent=2) + "\n"
    )

    target_dir = staging / "target"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(REPO_ROOT / instance.target_path, target_dir)

    opponents_dir = staging / "opponents"
    if opponents_dir.exists():
        shutil.rmtree(opponents_dir)
    opponents_dir.mkdir(parents=True)
    for opponent in instance.opponents:
        src = REPO_ROOT / opponent
        dest = opponents_dir / Path(opponent).name
        shutil.copytree(src, dest)
    return instance


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    resolve_p = sub.add_parser("resolve")
    resolve_p.add_argument("config", type=Path)
    resolve_p.add_argument("--target-index", type=int, default=0)

    task_p = sub.add_parser("resolve-task")
    task_p.add_argument("task_dir", type=Path)

    stage_p = sub.add_parser("stage")
    stage_p.add_argument("task_dir", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "resolve":
        instance = resolve_instance(args.config, args.target_index)
    elif args.cmd == "resolve-task":
        instance = write_resolved_metadata(args.task_dir)
    else:
        instance = stage_build_context(args.task_dir)
    print(json.dumps(asdict(instance), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
