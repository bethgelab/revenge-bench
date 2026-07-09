"""Materialize canonical Harbor task directories from audited pilot templates.

The manually-audited Harbor tasks are kept as one pilot directory per game.
The normal benchmark, however, expands each game config into the top 15 target
instances. This module turns the canonical 75-entry inventory into concrete
Harbor task directories by copying the appropriate pilot template and patching
only the per-instance identity/configuration files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from revenge_bench.harbor import inventory
from revenge_bench.harbor.prompt import generate_instruction, render_task_instruction
from revenge_bench.paths import REPO_ROOT


PILOT_TASKS: dict[str, str] = {
    "battlesnake": "battlesnake-gpt5-9aa3-v0",
    "halite": "halite-gpt5-9aa3-v0",
    "huskybench": "huskybench-gpt5-9aa3-v0",
    "robocode": "robocode-gpt5-9aa3-v0",
    "robotrumble": "robotrumble-gpt5-9aa3-v0",
}

TEMPLATE_GENERATED_DIRS = {"staging", "wheels", "__pycache__", "solution"}


@dataclass(frozen=True)
class MaterializedTask:
    task_name: str
    game: str
    target_index: int
    path: Path
    docker_image: str
    staged: bool


def _copy_ignore(_dir: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in TEMPLATE_GENERATED_DIRS}
    ignored.update(name for name in names if name.endswith(".pyc"))
    return ignored


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _patch_task_toml(text: str, *, task_name: str, docker_image: str) -> str:
    text, name_count = re.subn(
        r'(?m)^name = "revengebench/[^"]+"$',
        f'name = "revengebench/{task_name}"',
        text,
        count=1,
    )
    if name_count != 1:
        raise ValueError("expected exactly one [task] name in task.toml")
    text, image_count = re.subn(
        r'(?m)^docker_image = "revengebench/[^"]+:latest"$',
        f'docker_image = "{docker_image}"',
        text,
        count=1,
    )
    if image_count != 1:
        raise ValueError("expected exactly one environment docker_image in task.toml")
    return text


def _stage_task(task_dir: Path, game: str) -> None:
    module = __import__(f"revenge_bench.harbor.{game}_task", fromlist=["stage_build_context"])
    module.stage_build_context(task_dir)


def _copy_wheels(src: Path, dest: Path) -> bool:
    wheels = sorted(src.glob("*.whl"))
    if not wheels:
        return False
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for wheel in wheels:
        shutil.copy2(wheel, dest / wheel.name)
    return True


def _ensure_wheels(task_dir: Path, template: Path) -> None:
    """Populate environment/wheels so Docker source builds are self-contained."""
    dest = task_dir / "environment" / "wheels"
    if _copy_wheels(template / "environment" / "wheels", dest):
        return

    with tempfile.TemporaryDirectory(prefix="revengebench-wheel-") as tmp:
        tmp_path = Path(tmp)
        subprocess.run(
            ["uv", "build", "--wheel", "-o", str(tmp_path)],
            cwd=REPO_ROOT,
            check=True,
        )
        if not _copy_wheels(tmp_path, dest):
            raise RuntimeError("uv build completed but produced no wheel")


def _materialize_entry(
    entry: dict[str, Any],
    *,
    tasks_root: Path,
    template_root: Path,
    force: bool,
    stage: bool,
    include_wheels: bool,
) -> MaterializedTask:
    game = entry["game"]
    task_name = entry["task_name"]
    template = template_root / PILOT_TASKS[game]
    dest = tasks_root / task_name
    if not template.is_dir():
        raise FileNotFoundError(f"missing pilot template for {game}: {template}")
    if dest.exists():
        if not force:
            raise FileExistsError(f"{dest} already exists; pass --force to replace it")
        shutil.rmtree(dest)

    shutil.copytree(template, dest, ignore=_copy_ignore)

    target_index = int(entry["normal_path_key"]["target_index"])
    _write_json(
        dest / "task_config.json",
        {
            "benchmark_config": entry["normal_path_key"]["benchmark_config"],
            "target_index": target_index,
        },
    )
    _write_json(dest / "resolved_task.json", entry["resolved"])
    (dest / "instruction.md").write_text(render_task_instruction(task_name))

    task_toml = dest / "task.toml"
    task_toml.write_text(
        _patch_task_toml(
            task_toml.read_text(),
            task_name=task_name,
            docker_image=entry["docker_image"],
        )
    )

    if stage:
        _stage_task(dest, game)
    if include_wheels:
        _ensure_wheels(dest, template)

    return MaterializedTask(
        task_name=task_name,
        game=game,
        target_index=target_index,
        path=dest,
        docker_image=entry["docker_image"],
        staged=stage,
    )


def materialize_tasks(
    *,
    tasks_root: Path = REPO_ROOT / "harbor" / "tasks",
    template_root: Path | None = None,
    target_count: int = 15,
    target_indices: Iterable[int] | None = None,
    games: Iterable[str] | None = None,
    force: bool = False,
    stage: bool = False,
    include_wheels: bool | None = None,
) -> list[MaterializedTask]:
    """Create concrete Harbor task directories for the selected inventory."""
    template_root = template_root or tasks_root
    if include_wheels is None:
        include_wheels = stage
    selected_games = list(games) if games is not None else None
    inv = inventory.build_inventory(target_count=target_count, games=selected_games)
    selected_indices = set(target_indices) if target_indices is not None else None
    entries = [
        entry
        for entry in inv["tasks"]
        if selected_indices is None
        or int(entry["normal_path_key"]["target_index"]) in selected_indices
    ]
    tasks_root.mkdir(parents=True, exist_ok=True)
    generated = [
        _materialize_entry(
            entry,
            tasks_root=tasks_root,
            template_root=template_root,
            force=force,
            stage=stage,
            include_wheels=include_wheels,
        )
        for entry in entries
    ]

    if tasks_root == REPO_ROOT / "harbor" / "tasks":
        inventory.write_inventory(tasks_root / "manifest.json", target_count=target_count, games=selected_games)
        for pilot in PILOT_TASKS.values():
            if (tasks_root / pilot).exists():
                generate_instruction(pilot)

    return generated


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tasks-root",
        type=Path,
        default=REPO_ROOT / "harbor" / "tasks",
        help="Destination task root. Defaults to harbor/tasks in this repo.",
    )
    parser.add_argument(
        "--template-root",
        type=Path,
        default=REPO_ROOT / "harbor" / "tasks",
        help="Root containing the five audited pilot task directories.",
    )
    parser.add_argument("--target-count", type=int, default=15)
    parser.add_argument(
        "--target-index",
        action="append",
        type=int,
        help=(
            "Materialize only this normal-path target index. May be repeated. "
            "Defaults to all indices below --target-count."
        ),
    )
    parser.add_argument("--game", action="append", choices=sorted(PILOT_TASKS))
    parser.add_argument("--force", action="store_true", help="Replace existing generated task dirs.")
    parser.add_argument(
        "--stage",
        action="store_true",
        help="Also stage target/opponent files into each generated Docker build context.",
    )
    parser.add_argument(
        "--no-wheels",
        action="store_true",
        help=(
            "Do not populate environment/wheels when staging. By default, staged "
            "tasks include wheels so Harbor --force-build works without running "
            "build_context.sh first."
        ),
    )
    args = parser.parse_args(argv)

    generated = materialize_tasks(
        tasks_root=args.tasks_root,
        template_root=args.template_root,
        target_count=args.target_count,
        target_indices=args.target_index,
        games=args.game,
        force=args.force,
        stage=args.stage,
        include_wheels=False if args.no_wheels else None,
    )
    print(f"materialized {len(generated)} Harbor task(s) under {args.tasks_root}")
    for task in generated:
        suffix = " staged" if task.staged else ""
        print(f"{task.task_name} -> {task.docker_image}{suffix}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
