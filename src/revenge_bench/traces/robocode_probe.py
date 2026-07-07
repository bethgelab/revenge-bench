"""Shared RoboCode probe helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from revenge_bench.traces.parsers.robocode import build_probe_trace_payload


RC_FILE = Path("MyTank.java")
PROBE_PACKAGE = "p0"
TARGET_PACKAGE = "p1"


def _battle_config_lines() -> list[str]:
    return [
        "#Battle Properties",
        "robocode.battle.numRounds=1",
        "robocode.battle.gunCoolingRate=0.1",
        "robocode.battle.rules.inactivityTime=450",
        "robocode.battle.rules.hideEnemyNames=True",
        "robocode.battleField.width=800",
        "robocode.battleField.height=600",
    ]


def robocode_round_battle_content(
    packages: list[str] | tuple[str, ...],
    *,
    robot_class: str = "MyTank",
    battle_config: str | None = None,
) -> str:
    """Return the normal RoboCodeArena round battle file content."""
    selected_robots = ",".join(f"{pkg}.{robot_class}*" for pkg in packages)
    config_text = battle_config if battle_config is not None else "\n".join(_battle_config_lines())
    return "\n".join(
        [
            "#Battle Properties",
            config_text,
            f"robocode.battle.selectedRobots={selected_robots}",
            "",
        ]
    )


def rewrite_robot_package(bot_dir: Path, package: str) -> None:
    for path in sorted(bot_dir.glob("*.java")):
        text = path.read_text()
        path.write_text(text.replace("package custom;", f"package {package};").replace("custom", package))


def compile_robot_package(
    workspace: Path,
    package: str,
    *,
    javac: str = "javac",
    timeout: int = 60,
) -> None:
    bot_dir = workspace / "robots" / package
    java_files = sorted(bot_dir.glob("*.java"))
    if not java_files:
        raise FileNotFoundError(f"no Java files found in {bot_dir}")

    proc = subprocess.run(
        [javac, "-cp", "libs/robocode.jar", *[str(p) for p in java_files]],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"compile failed for {package}:\n{proc.stdout}\n{proc.stderr}")


def probe_battle_content(
    *,
    probe_package: str = PROBE_PACKAGE,
    target_package: str = TARGET_PACKAGE,
    robot_class: str = "MyTank",
) -> str:
    return "\n".join(
        [
            *_battle_config_lines(),
            f"robocode.battle.selectedRobots={probe_package}.{robot_class}*,{target_package}.{robot_class}*",
            "",
        ]
    )


def write_probe_battle(workspace: Path, relative_path: str = "battles/probe.battle") -> Path:
    battle = workspace / relative_path
    battle.parent.mkdir(parents=True, exist_ok=True)
    battle.write_text(probe_battle_content())
    return battle


def reset_robot_database(workspace: Path) -> None:
    (workspace / "robots" / "robot.database").unlink(missing_ok=True)


def run_probe_simulations(
    workspace: Path,
    log_dir: Path,
    *,
    sims: int,
    battle: Path,
    timeout: int = 120,
) -> list[tuple[str, Path]]:
    simulations: list[tuple[str, Path]] = []
    for idx in range(sims):
        record = log_dir / f"record_{idx}.xml"
        results = log_dir / f"results_{idx}.txt"
        proc = subprocess.run(
            [
                "./robocode.sh",
                "-nodisplay",
                "-nosound",
                "-battle",
                str(battle),
                "-results",
                str(results),
                "-recordXML",
                str(record),
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            tail = (proc.stdout + "\n" + proc.stderr)[-4000:]
            raise RuntimeError(f"probe sim {idx} failed:\n{tail}")
        if not record.exists() or record.stat().st_size == 0:
            raise RuntimeError(f"probe sim {idx} produced no XML")
        if not results.exists() or results.stat().st_size == 0:
            raise RuntimeError(f"probe sim {idx} produced no results")
        simulations.append((record.name, record))
    return simulations


def build_checked_probe_payload(
    simulations: list[tuple[str, Path]],
    probe_id: int,
    *,
    min_turns: int = 1,
) -> dict[str, Any]:
    payload = build_probe_trace_payload(simulations, probe_id)
    if payload.get("total_turns", 0) < min_turns:
        raise RuntimeError("probe traces produced zero aligned RoboCode turns")
    return payload
