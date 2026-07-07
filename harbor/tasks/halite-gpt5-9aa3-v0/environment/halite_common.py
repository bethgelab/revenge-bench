#!/usr/bin/env python3
"""Trusted helpers for the Harbor Halite task."""

from __future__ import annotations

import ast
import importlib.util
import shutil
import subprocess
from pathlib import Path


HALITE = Path("/workspace/environment/halite")
HLT_HEADER = Path("/opt/halite/hlt.h")


def _load_halite_arena_constant(name: str) -> dict[str, str]:
    """Read Halite arena constants without importing arena runner dependencies."""
    spec = importlib.util.find_spec("revenge_bench")
    if spec is None or spec.origin is None:
        raise RuntimeError("Could not locate installed revenge_bench package")
    arena_file = Path(spec.origin).parent / "arenas" / "halite" / "halite.py"
    tree = ast.parse(arena_file.read_text(), filename=str(arena_file))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, dict):
                        raise RuntimeError(f"{name} in {arena_file} is not a dict")
                    return value
    raise RuntimeError(f"Could not find {name} in {arena_file}")


MAP_FILE_TYPE_TO_COMPILE = _load_halite_arena_constant("MAP_FILE_TYPE_TO_COMPILE")
MAP_FILE_TYPE_TO_RUN = _load_halite_arena_constant("MAP_FILE_TYPE_TO_RUN")


def prepare_submission(src: Path, dest: Path) -> None:
    """Copy a strategy directory into ``dest/submission`` with ``hlt.h``."""
    if dest.exists():
        shutil.rmtree(dest)
    sub = dest / "submission"
    sub.mkdir(parents=True)
    if src.is_file():
        shutil.copy2(src, sub / src.name)
    else:
        for item in src.iterdir():
            target = sub / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    if HLT_HEADER.exists() and not (sub / "hlt.h").exists():
        shutil.copy2(HLT_HEADER, sub / "hlt.h")


def copy_workspace_submission(src: Path, dest: Path) -> None:
    """Copy an agent-facing submission directory into ``dest/submission``."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest / "submission")
    if HLT_HEADER.exists() and not (dest / "submission" / "hlt.h").exists():
        shutil.copy2(HLT_HEADER, dest / "submission" / "hlt.h")


def compile_submission(submission: Path, *, timeout: int = 30) -> str:
    """Compile a Halite submission and return the executable path string."""
    main_files = [
        f.name
        for f in submission.iterdir()
        if f.name.startswith("main.") and f.suffix in MAP_FILE_TYPE_TO_RUN
    ]
    if not main_files and (submission / "src" / "main.rs").exists():
        main_files = ["src/main.rs"]
    if not main_files:
        supported = "|".join(MAP_FILE_TYPE_TO_RUN)
        raise RuntimeError(f"No supported main.[{supported}] file in {submission}")

    main = main_files[0]
    main_ext = Path(main).suffix
    if main_ext in MAP_FILE_TYPE_TO_COMPILE:
        compile_cmd = MAP_FILE_TYPE_TO_COMPILE[main_ext].format(name="main")
        result = subprocess.run(
            compile_cmd,
            shell=True,
            cwd=submission,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[:2000] or result.stdout.strip()[:2000])

    return MAP_FILE_TYPE_TO_RUN[main_ext].format(path=str(submission), name="main")


def run_halite(replay_dir: Path, *executables: str, timeout: int = 120) -> list[Path]:
    """Run the Halite engine and return newly produced replay files."""
    replay_dir.mkdir(parents=True, exist_ok=True)
    before = set(replay_dir.glob("*.hlt"))
    cmd = [str(HALITE), "--replaydirectory", str(replay_dir), *executables]
    result = subprocess.run(
        cmd,
        cwd="/workspace",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Halite engine exited with {result.returncode}")
    return sorted(set(replay_dir.glob("*.hlt")) - before)
