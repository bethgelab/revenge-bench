#!/usr/bin/env python3
"""Generate normal-path BattleSnake round traces inside the Harbor image.

By default this runs before the learner starts and writes visible evidence under
``/workspace/rounds/0/opp_<idx>/sim_<n>.jsonl``. The verifier reuses the same
trusted generator with ``BATTLESNAKE_TRACE_OUT`` pointing at a root-only hidden
round directory.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


SERVER = Path("/opt/battlesnake/server.py")
BATTLE = Path("/opt/battlesnake/battlesnake")
TARGET = Path("/target")
OPPONENTS = Path("/opt/revengebench/opponents")
OUT = Path(os.environ.get("BATTLESNAKE_TRACE_OUT", "/workspace/rounds/0"))
ARENA = Path(os.environ.get("BATTLESNAKE_TRACE_ARENA", "/run/label_arena"))
RESOLVED_TASK = Path(os.environ.get("BATTLESNAKE_RESOLVED_TASK", "/target/resolved_task.json"))
TRACE_SOURCE = os.environ.get("BATTLESNAKE_TRACE_SOURCE", "harbor-image-build")


def _copy_bot(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    shutil.copy2(SERVER, dest / "server.py")


def _start_bot(bot_dir: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = {
        "HOME": "/root",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PORT": str(port),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("wb")
    return subprocess.Popen(
        ["python3", str(bot_dir / "main.py")],
        cwd=str(bot_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _ready(port: int) -> bool:
    return (
        subprocess.run(
            ["wget", "-q", "--spider", "--timeout=1", f"http://localhost:{port}/"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def _free_port() -> int:
    """Ask the OS for an available loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_tail(path: Path, max_chars: int = 4000) -> str:
    try:
        text = path.read_text(errors="replace")
    except OSError as exc:
        return f"<could not read {path}: {exc}>"
    return text[-max_chars:]


def _wait_for_ports(ports: tuple[int, ...], logs: list[Path]) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        if all(_ready(port) for port in ports):
            return
        time.sleep(0.25)
    tails = "\n\n".join(f"== {path} ==\n{_read_tail(path)}" for path in logs)
    raise RuntimeError(f"BattleSnake servers did not start: {ports}\n{tails}")


def _stop(*procs: subprocess.Popen) -> None:
    for proc in procs:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)


def _run_one_opponent(opponent: Path, opp_idx: int, sims: int, width: int, height: int) -> None:
    opp_dir = OUT / f"opp_{opp_idx}"
    opp_dir.mkdir(parents=True, exist_ok=True)
    print(f"generating traces for opponent {opp_idx}: {opponent.name} ({sims} sims)", flush=True)

    target_work = ARENA / "target"
    opponent_work = ARENA / "opponent"
    _copy_bot(TARGET, target_work)
    _copy_bot(opponent, opponent_work)

    target_port = _free_port()
    opponent_port = _free_port()
    while opponent_port == target_port:
        opponent_port = _free_port()
    target_log = opp_dir / "_target_server.log"
    opponent_log = opp_dir / "_opponent_server.log"
    target_proc = _start_bot(target_work, target_port, target_log)
    opponent_proc = _start_bot(opponent_work, opponent_port, opponent_log)
    try:
        _wait_for_ports((target_port, opponent_port), [target_log, opponent_log])
        for sim_idx in range(sims):
            subprocess.run(
                [
                    str(BATTLE),
                    "play",
                    "--url",
                    f"http://localhost:{target_port}",
                    "-n",
                    "target",
                    "--url",
                    f"http://localhost:{opponent_port}",
                    "-n",
                    "opponent",
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                    "-o",
                    str(opp_dir / f"sim_{sim_idx}.jsonl"),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    finally:
        _stop(target_proc, opponent_proc)


def main() -> int:
    instance = json.loads(RESOLVED_TASK.read_text())
    opponents = instance["opponents"]
    total_sims = int(instance["sims_per_round"])
    width = int(instance["width"])
    height = int(instance["height"])

    if OUT.exists():
        shutil.rmtree(OUT)
    if ARENA.exists():
        shutil.rmtree(ARENA)
    ARENA.mkdir(parents=True)

    per_opp = total_sims // len(opponents)
    remainder = total_sims % len(opponents)
    for opp_idx, rel in enumerate(opponents):
        sims = per_opp + (1 if opp_idx < remainder else 0)
        if sims <= 0:
            continue
        opponent = OPPONENTS / Path(rel).name
        if not (opponent / "main.py").exists():
            raise FileNotFoundError(f"missing opponent main.py: {opponent}")
        _run_one_opponent(opponent, opp_idx, sims, width, height)

    manifest = {
        "source": TRACE_SOURCE,
        "task": instance,
        "label_files": [
            p.relative_to(OUT).as_posix() for p in sorted(OUT.rglob("sim_*.jsonl"))
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.rmtree(ARENA, ignore_errors=True)
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    raise SystemExit(main())
