"""
Integration test for Halite3 score consistency.

Runs a real Halite3 game and cross-checks several values between the engine's
simulation log (sim_0.log) and the .hlt replay file parsed by HaliteTraceParser.

The two data sources must agree on:
  1. Winner / draw status
  2. Final halite per player ("with K halite" in log == last frame energy in .hlt)
  3. Number of turns ("[N] Game has ended" in log == len(trace.turns))
  4. Player names ("[PN] Initialized player X" in log == players[N].name in .hlt)

Requires: Docker with the revenge_bench/halite3 image available.
"""

import re
import shutil
import tarfile
import tempfile
from pathlib import Path

import pytest

# "Player 0, 'BotName', was rank 1 with 853 halite"
_RANK_PATTERN = re.compile(
    r"Player\s+(\d+),\s+'(\S+)',\s+was\s+rank\s+(\d+)\s+with\s+(\d+)\s+halite"
)

# "[500] Game has ended"
_TURN_PATTERN = re.compile(r"\[(\d+)\]\s+Game has ended")

# "[P0] Initialized player MyRustBot"
_NAME_PATTERN = re.compile(r"\[P(\d+)\]\s+Initialized player\s+(\S+)")


def _parse_log(text: str) -> tuple[dict[int, dict], int | None, dict[int, str]]:
    """
    Parse a Halite3 simulation log.

    Returns:
        players:    {player_id: {"rank": int, "halite": int}}
        turn_count: final turn number from "Game has ended" line, or None
        names:      {player_id: bot_name} from initialization lines
    """
    players: dict[int, dict] = {}
    for m in _RANK_PATTERN.finditer(text):
        pid = int(m.group(1))
        players[pid] = {"rank": int(m.group(3)), "halite": int(m.group(4))}

    turn_match = _TURN_PATTERN.search(text)
    turn_count = int(turn_match.group(1)) if turn_match else None

    names: dict[int, str] = {}
    for m in _NAME_PATTERN.finditer(text):
        names[int(m.group(1))] = m.group(2)

    return players, turn_count, names


def _read_round_from_archive(archive_path: Path) -> dict[str, bytes]:
    """
    Read all files from a round_N.tar.gz archive.
    Returns {relative_path: file_bytes}, excluding macOS AppleDouble sidecars.
    """
    files = {}
    with tarfile.open(archive_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.isfile() and not Path(member.name).name.startswith("._"):
                f = tf.extractfile(member)
                if f is not None:
                    files[member.name] = f.read()
    return files


@pytest.mark.slow
@pytest.mark.parametrize(
    ("width", "height", "seed"),
    [
        (32, 32, 1),
        (32, 32, 42),
        (64, 64, 1),
    ],
)
def test_halite3_hlt_matches_engine_log(width, height, seed):
    """
    Full pipeline test: run a Halite3 game with given map dimensions and seed,
    then cross-check the .hlt replay file against the engine's simulation log
    across four dimensions: winner, per-player halite totals, turn count, and
    player names.
    """
    from revenge_bench.tournaments.pvp import PvpTournament
    from revenge_bench.traces.parsers.halite3 import (
        Halite3TraceParser as HaliteTraceParser,
    )
    from revenge_bench.traces.parsers.halite3 import (
        load_hlt_file,
    )

    config = {
        "tournament": {"rounds": 0},  # rounds=0: one game only, no edit phase
        "game": {
            "name": "Halite3",
            "sims_per_round": 1,
            "args": {"width": width, "height": height, "seed": seed},
        },
        "players": [
            {"agent": "dummy", "name": "p1"},
            {"agent": "dummy", "name": "p2"},
        ],
        "prompts": {"game_description": "test"},
    }

    # Under pytest, AbstractTournament.local_output_dir redirects to
    # /tmp/revenge_bench/{output_dir.name}. Encode params in the name so parallel
    # runs don't collide.
    output_dir = Path("/tmp/revenge-bench") / f"halite3_test_w{width}_h{height}_s{seed}"
    if output_dir.exists():
        shutil.rmtree(output_dir)

    try:
        tournament = PvpTournament(config, output_dir=output_dir)
        tournament.run()

        rounds_dir = output_dir / "rounds"
        archive = rounds_dir / "round_0.tar.gz"
        assert archive.exists(), f"Round archive not found: {archive}"

        archived = _read_round_from_archive(archive)

        # --- Locate sim log and .hlt inside the archive ---
        sim_log_key = next((k for k in archived if k.endswith("sim_0.log")), None)
        assert (
            sim_log_key
        ), f"sim_0.log not found in archive. Contents: {list(archived)}"

        hlt_keys = [k for k in archived if k.endswith(".hlt")]
        assert hlt_keys, f"No .hlt file found in archive. Contents: {list(archived)}"

        # --- Parse engine simulation log ---
        log_text = archived[sim_log_key].decode("utf-8", errors="replace")
        log_players, log_turn_count, log_names = _parse_log(log_text)
        assert log_players, "No rank lines found in sim_0.log"

        # --- Load raw .hlt data (write to temp file so load_hlt_file can read it) ---
        hlt_bytes = archived[hlt_keys[0]]
        with tempfile.NamedTemporaryFile(suffix=".hlt", delete=False) as tmp_hlt:
            tmp_hlt.write(hlt_bytes)
            tmp_hlt_path = Path(tmp_hlt.name)

        raw = load_hlt_file(tmp_hlt_path)
        final_energy = raw["full_frames"][-1]["energy"]  # {"0": K, "1": M, ...}
        assert final_energy, "No energy data in final frame"

        # --- Parse with HaliteTraceParser ---
        trace = HaliteTraceParser().parse_file(tmp_hlt_path)
        tmp_hlt_path.unlink()

        # =================================================================
        # Check 1: winner / draw status
        # =================================================================
        log_ranks = {pid: info["rank"] for pid, info in log_players.items()}
        engine_is_draw = len(set(log_ranks.values())) == 1
        hlt_is_draw = len(set(final_energy.values())) == 1

        assert engine_is_draw == hlt_is_draw, (
            f"Draw status mismatch:\n"
            f"  engine log ranks: {log_ranks}\n"
            f"  .hlt final energy: {final_energy}"
        )
        assert (
            trace.is_draw == hlt_is_draw
        ), f"HaliteTraceParser.is_draw={trace.is_draw}, expected {hlt_is_draw}"

        if not engine_is_draw:
            engine_winner_id = min(log_ranks, key=log_ranks.get)
            hlt_winner_id_str = max(final_energy, key=final_energy.get)
            assert str(engine_winner_id) == hlt_winner_id_str, (
                f"Winner mismatch:\n"
                f"  engine log: player {engine_winner_id} (ranks: {log_ranks})\n"
                f"  .hlt energy: player {hlt_winner_id_str} (energy: {final_energy})"
            )

            winner_player = next(
                p for p in raw["players"] if str(p["player_id"]) == hlt_winner_id_str
            )
            assert trace.winner == winner_player["name"], (
                f"HaliteTraceParser.winner='{trace.winner}', "
                f"expected '{winner_player['name']}'"
            )

        # =================================================================
        # Check 2: final halite per player
        # Engine log "with K halite" must equal .hlt last frame energy[N]
        # =================================================================
        for pid, info in log_players.items():
            log_halite = info["halite"]
            hlt_halite = final_energy.get(str(pid))
            assert (
                hlt_halite is not None
            ), f"Player {pid} present in log but missing from .hlt energy dict"
            assert log_halite == hlt_halite, (
                f"Final halite mismatch for player {pid}:\n"
                f"  engine log: {log_halite}\n"
                f"  .hlt last frame energy: {hlt_halite}"
            )

        # =================================================================
        # Check 3: turn count
        # Number of frames in the trace must match number of raw full_frames
        # =================================================================
        assert len(trace.turns) == len(raw["full_frames"]), (
            f"Turn count mismatch:\n"
            f"  HaliteTraceParser produced {len(trace.turns)} turns\n"
            f"  raw .hlt has {len(raw['full_frames'])} full_frames"
        )

        if log_turn_count is not None:
            # "[N] Game has ended" → N turns completed → N+2 frames
            # (one initial state frame + N turn-result frames + one final frame)
            assert len(raw["full_frames"]) == log_turn_count + 2, (
                f"Frame count vs log turn number mismatch:\n"
                f"  log says game ended at turn {log_turn_count}\n"
                f"  expected {log_turn_count + 2} frames, got {len(raw['full_frames'])}"
            )

        # =================================================================
        # Check 4: player names
        # Initialization lines in the log must match player names in .hlt
        # =================================================================
        hlt_names = {p["player_id"]: p["name"] for p in raw["players"]}
        for pid, log_name in log_names.items():
            hlt_name = hlt_names.get(pid)
            assert (
                hlt_name is not None
            ), f"Player {pid} found in log but missing from .hlt players"
            assert log_name == hlt_name, (
                f"Player {pid} name mismatch:\n"
                f"  engine log: '{log_name}'\n"
                f"  .hlt: '{hlt_name}'"
            )

    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
