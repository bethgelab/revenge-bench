"""Harbor task inventory and provenance helpers.

The normal benchmark path expands one full-pool config into the top-N target
instances. Harbor task directories are one fixed target each, so this module
builds the explicit mapping from normal-path config/target index to a stable
Harbor task name and resolved opponent set.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from revenge_bench.harbor.battlesnake_task import resolve_instance as resolve_battlesnake
from revenge_bench.harbor.halite_task import resolve_instance as resolve_halite
from revenge_bench.harbor.huskybench_task import resolve_instance as resolve_huskybench
from revenge_bench.harbor.robocode_task import resolve_instance as resolve_robocode
from revenge_bench.harbor.robotrumble_task import resolve_instance as resolve_robotrumble
from revenge_bench.paths import REPO_ROOT


ResolveFn = Callable[[Path, int], Any]


GAME_CONFIGS: dict[str, tuple[str, ResolveFn]] = {
    "battlesnake": ("configs/benchmark/gpt5/gpt5_battlesnake.yaml", resolve_battlesnake),
    "halite": ("configs/benchmark/gpt5/gpt5_halite.yaml", resolve_halite),
    "huskybench": ("configs/benchmark/gpt5/gpt5_huskybench.yaml", resolve_huskybench),
    "robocode": ("configs/benchmark/gpt5/gpt5_robocode.yaml", resolve_robocode),
    "robotrumble": ("configs/benchmark/gpt5/gpt5_robotrumble.yaml", resolve_robotrumble),
}


def _slug(value: str, *, max_len: int = 40) -> str:
    text = value.lower().replace("_", "-")
    text = re.sub(r"[^a-z0-9.-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len].strip("-") or "unknown"


def _benchmark_slug(config_path: str) -> str:
    # configs/benchmark/gpt5/gpt5_battlesnake.yaml -> gpt5
    parts = Path(config_path).parts
    try:
        return _slug(parts[parts.index("benchmark") + 1], max_len=24)
    except (ValueError, IndexError):
        return _slug(Path(config_path).stem, max_len=24)


def canonical_task_name(game: str, benchmark_config: str, target_index: int, target_name: str) -> str:
    """Return the canonical Harbor task directory/image stem for an instance."""
    if "__" in target_name:
        target_model, target_hash = target_name.rsplit("__", 1)
    else:
        target_model, target_hash = target_name, "unknown"
    return (
        f"{_slug(game, max_len=24)}-"
        f"{_benchmark_slug(benchmark_config)}-"
        f"t{target_index:02d}-"
        f"{_slug(target_model, max_len=30)}-"
        f"{_slug(target_hash, max_len=12)}-"
        "v0"
    )


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _strategy_entry(path_str: str) -> dict[str, Any]:
    path = REPO_ROOT / path_str
    return {
        "name": path.name,
        "path": path_str,
        "provenance": _read_json_if_present(path / "provenance.json"),
    }


def build_entry(game: str, config_path: str, target_index: int, resolve: ResolveFn) -> dict[str, Any]:
    """Build one manifest entry from the normal-path resolver."""
    instance = resolve(Path(config_path), target_index)
    data = asdict(instance)
    task_name = canonical_task_name(
        game,
        data["benchmark_config"],
        data["target_index"],
        data["target_name"],
    )
    return {
        "task_name": task_name,
        "docker_image": f"revengebench/{task_name}:latest",
        "normal_path_key": {
            "benchmark_config": data["benchmark_config"],
            "target_index": data["target_index"],
        },
        "game": game,
        "benchmark": _benchmark_slug(data["benchmark_config"]),
        "resolved": data,
        "target": _strategy_entry(data["target_path"]),
        "opponents": [_strategy_entry(path) for path in data["opponents"]],
    }


def build_inventory(*, target_count: int = 15, games: list[str] | None = None) -> dict[str, Any]:
    """Build the canonical Harbor inventory for the top-N normal-path targets."""
    selected_games = games or list(GAME_CONFIGS)
    entries: list[dict[str, Any]] = []
    for game in selected_games:
        config_path, resolve = GAME_CONFIGS[game]
        for target_index in range(target_count):
            entries.append(build_entry(game, config_path, target_index, resolve))
    return {
        "schema_version": 1,
        "description": "Canonical mapping from normal full-pool benchmark targets to Harbor task instances.",
        "target_count_per_game": target_count,
        "games": selected_games,
        "tasks": entries,
    }


def write_inventory(path: Path, *, target_count: int = 15, games: list[str] | None = None) -> dict[str, Any]:
    inventory = build_inventory(target_count=target_count, games=games)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory, indent=2) + "\n")
    return inventory


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "harbor" / "tasks" / "manifest.json",
    )
    parser.add_argument("--target-count", type=int, default=15)
    parser.add_argument("--game", action="append", choices=sorted(GAME_CONFIGS))
    args = parser.parse_args(argv)
    inventory = write_inventory(args.output, target_count=args.target_count, games=args.game)
    print(f"wrote {args.output} with {len(inventory['tasks'])} task entries")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
