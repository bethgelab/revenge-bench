"""Harbor execution glue for HuskyBench.

This module adapts the normal HuskyBench arena's container/process layout. The
meaning of traces, probe payloads, and scores stays in shared ``revenge_bench``
parser/evaluator code.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path


WORKSPACE = Path("/workspace")
HB_PORT = 8000
HB_BOT_TIMEOUT = 10
HB_LOG_ENGINE = "engine.log"
HB_OUTPUT_DIRS = [Path("/app/output"), Path("output"), Path("/workspace/output")]
SKIP_PREFIXES = ("test_", "test.", "analyze", "debug", "temp")


def copy_strategy_source(source: Path, dest_root: Path) -> None:
    """Copy a normal-path HuskyBench static strategy into ``dest_root``.

    ``Static._copy_strategy_code`` copies ``player.py`` plus same-extension
    helper files, while skipping test/analyze/debug/temp scripts. This function
    mirrors that behavior but works on Harbor's sealed root-only directories.
    """

    client_dest = dest_root / "client"
    if client_dest.exists():
        shutil.rmtree(client_dest)
    shutil.copytree(WORKSPACE / "client", client_dest, ignore=shutil.ignore_patterns("__pycache__"))

    if source.is_file():
        shutil.copy2(source, client_dest / "player.py")
        return

    main = source / "player.py"
    if not main.exists():
        raise FileNotFoundError(f"missing player.py in {source}")
    shutil.copy2(main, client_dest / "player.py")

    for aux in sorted(source.glob("*.py")):
        if aux.name == "player.py":
            continue
        if aux.stem.lower().startswith(SKIP_PREFIXES):
            continue
        shutil.copy2(aux, client_dest / aux.name)


def clear_husky_outputs() -> None:
    for out_dir in HB_OUTPUT_DIRS:
        path = WORKSPACE / out_dir if not out_dir.is_absolute() else out_dir
        if path.is_dir():
            for child in path.iterdir():
                if child.is_file():
                    child.unlink()


def kill_port(port: int = HB_PORT) -> None:
    proc = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
    )
    for pid_s in proc.stdout.split():
        try:
            os.kill(int(pid_s), signal.SIGKILL)
        except ProcessLookupError:
            pass


def _engine_command(num_players: int, sims: int) -> list[str]:
    # Mirrors HuskyBenchArena.__init__/execute_round for the benchmark config:
    # browser=false, so no --browser flag is added.
    return [
        "python",
        "engine/main.py",
        "--port",
        str(HB_PORT),
        "--players",
        str(num_players),
        "--sim",
        "--sim-rounds",
        str(sims),
    ]


def _collect_output_files(out_dir: Path) -> None:
    for output_root in HB_OUTPUT_DIRS:
        path = WORKSPACE / output_root if not output_root.is_absolute() else output_root
        if not path.is_dir():
            continue
        for child in sorted(path.iterdir()):
            if child.is_file():
                shutil.move(str(child), out_dir / child.name)


def rewrite_player_names(out_dir: Path, player_names: list[str]) -> None:
    """Rewrite ``playerNames`` in game logs from ``playerN`` to agent names."""

    id_to_agent: dict[str, str] = {}
    for name in player_names:
        log_path = out_dir / f"{name}.log"
        if not log_path.exists():
            continue
        for line in log_path.read_text(errors="replace").splitlines():
            if "Connected with player ID: " in line:
                id_to_agent[line.strip().split()[-1]] = name
                break

    if not id_to_agent:
        raise RuntimeError(f"no connected player IDs found in {out_dir}")

    value_to_agent = {f"player{aid}": name for aid, name in id_to_agent.items()}
    for game_log in sorted(out_dir.glob("game_log_*.json")):
        data = json.loads(game_log.read_text())
        player_names_map = data.get("playerNames", {})
        if all(v in value_to_agent for v in player_names_map.values()):
            data["playerNames"] = {
                k: value_to_agent[v] for k, v in player_names_map.items()
            }
            game_log.write_text(json.dumps(data) + "\n")


def run_husky_game(players: list[tuple[str, Path]], sims: int, out_dir: Path) -> list[Path]:
    """Run one HuskyBench engine instance and return generated game logs."""

    out_dir.mkdir(parents=True, exist_ok=True)
    for child in out_dir.iterdir():
        if child.is_file():
            child.unlink()

    clear_husky_outputs()
    kill_port()

    engine_log = (out_dir / HB_LOG_ENGINE).open("w")
    engine = subprocess.Popen(
        _engine_command(len(players), sims),
        cwd=WORKSPACE,
        stdout=engine_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(0.5)

    client_logs = []
    clients: list[subprocess.Popen] = []
    try:
        for name, root in players:
            log_file = (out_dir / f"{name}.log").open("w")
            client_logs.append(log_file)
            clients.append(
                subprocess.Popen(
                    ["python", "client/main.py", "--port", str(HB_PORT)],
                    cwd=root,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            )

        timeout = max(sims * HB_BOT_TIMEOUT, 1)
        rc = engine.wait(timeout=timeout)
        for proc in clients:
            proc.wait(timeout=5)
        if rc != 0:
            tail = (out_dir / HB_LOG_ENGINE).read_text(errors="replace")[-4000:]
            raise RuntimeError(f"HuskyBench engine failed with rc={rc}:\n{tail}")
    finally:
        for proc in clients:
            if proc.poll() is None:
                proc.kill()
        if engine.poll() is None:
            engine.kill()
        for log_file in client_logs:
            log_file.close()
        engine_log.close()

    _collect_output_files(out_dir)
    game_logs = sorted(out_dir.glob("game_log_*.json"))
    if not game_logs:
        raise RuntimeError(f"HuskyBench produced no game_log_*.json files in {out_dir}")
    rewrite_player_names(out_dir, [name for name, _root in players])
    return sorted(out_dir.glob("game_log_*.json"))


def shuffled_two_player_match(
    first: tuple[str, Path], second: tuple[str, Path]
) -> list[tuple[str, Path]]:
    """Mirror CodeArena's round-level random player ordering."""

    players = [first, second]
    random.shuffle(players)
    return players


def count_engine_score_updates(engine_log: Path) -> int:
    pattern = re.compile(r"Player\s(\d+)\sdelta\supdated\:")
    if not engine_log.exists():
        return 0
    return sum(1 for line in engine_log.read_text(errors="replace").splitlines() if pattern.search(line))
