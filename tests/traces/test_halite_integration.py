"""
Integration test for Halite I score consistency.

Runs a real Halite I game and cross-checks several values between the engine's
simulation log (sim_0.log) and the .hlt replay file parsed by HaliteTraceParser.

The two data sources must agree on:
  1. Winner / draw status
  2. Number of turns (last frame index in log == num_frames - 1 in .hlt)
  3. Player names (names in log == player_names in .hlt)
  4. Player count (num_players in .hlt == number of players in log)

Requires: Docker with the revenge_bench/halite image available.
"""

import re
import shutil
import tarfile
import tempfile
from pathlib import Path

import pytest

# "Player #1, BotName, came in rank #1 and was last alive on frame #300!"
_RANK_PATTERN = re.compile(
    r"Player\s#(\d+),\s+(.*?),\s+came\s+in\s+rank\s+#(\d+)\s+and\s+was\s+last\s+alive\s+on\s+frame\s+#(\d+)"
)

# "Map seed was 529723819"
_SEED_PATTERN = re.compile(r"Map\s+seed\s+was\s+(\d+)")

# "Opening a file at ./SEED1-SEED2.hlt"
_HLT_FILE_PATTERN = re.compile(r"Opening\s+a\s+file\s+at\s+\./(\S+\.hlt)")


def _parse_log(text: str) -> tuple[dict[int, dict], dict[int, str]]:
    """
    Parse a Halite I simulation log.

    Returns:
        players:  {player_num: {"rank": int, "name": str, "last_frame": int}}
        names:    {player_num: bot_name}
    """
    players: dict[int, dict] = {}
    names: dict[int, str] = {}

    for m in _RANK_PATTERN.finditer(text):
        player_num = int(m.group(1))
        name = m.group(2).strip()
        rank = int(m.group(3))
        last_frame = int(m.group(4))
        players[player_num] = {"rank": rank, "name": name, "last_frame": last_frame}
        names[player_num] = name

    return players, names


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
        (20, 20, 1),
        (20, 20, 42),
        (30, 30, 1),
    ],
)
def test_halite1_hlt_matches_engine_log(width, height, seed):
    """
    Full pipeline test: run a Halite I game with given map dimensions and seed,
    then cross-check the .hlt replay file against the engine's simulation log
    across four dimensions: winner, turn count, player names, and player count.
    """

    from revenge_bench.tournaments.pvp import PvpTournament
    from revenge_bench.traces.parsers.halite import HaliteTraceParser, load_hlt_file

    config = {
        "tournament": {"rounds": 0},  # rounds=0: one game only, no edit phase
        "game": {
            "name": "Halite",
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
    output_dir = Path("/tmp/revenge-bench") / f"halite1_test_w{width}_h{height}_s{seed}"
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

        # Halite I .hlt files are named <seed1>-<seed2>.hlt (NOT replay-*.hlt)
        hlt_keys = [
            k
            for k in archived
            if k.endswith(".hlt") and not Path(k).name.startswith("replay-")
        ]
        assert (
            hlt_keys
        ), f"No Halite I .hlt file found in archive. Contents: {list(archived)}"

        # --- Parse engine simulation log ---
        log_text = archived[sim_log_key].decode("utf-8", errors="replace")
        log_players, log_names = _parse_log(log_text)
        assert log_players, "No rank lines found in sim_0.log"

        # --- Load raw .hlt data (write to temp file so load_hlt_file can read it) ---
        hlt_bytes = archived[hlt_keys[0]]
        with tempfile.NamedTemporaryFile(
            suffix=".hlt", delete=False, mode="wb"
        ) as tmp_hlt:
            tmp_hlt.write(hlt_bytes)
            tmp_hlt_path = Path(tmp_hlt.name)

        raw = load_hlt_file(tmp_hlt_path)

        # --- Parse with HaliteTraceParser ---
        trace = HaliteTraceParser().parse_file(tmp_hlt_path)
        tmp_hlt_path.unlink()

        # =================================================================
        # Check 1: winner / draw status
        # Engine log rank 1 == winner; .hlt final frame most cells == winner
        # =================================================================
        log_ranks = {pnum: info["rank"] for pnum, info in log_players.items()}
        engine_winners = [pnum for pnum, r in log_ranks.items() if r == 1]
        engine_is_draw = len(engine_winners) > 1

        # Determine winner from .hlt final frame cell counts (by player tag)
        final_frame = raw["frames"][-1]
        h = raw.get("height", len(final_frame))
        w = raw.get("width", len(final_frame[0]) if final_frame else 0)

        strength_by_tag: dict[int, int] = {}
        for r in range(h):
            for c in range(w):
                owner, strength = final_frame[r][c]
                if owner != 0:
                    strength_by_tag[owner] = strength_by_tag.get(owner, 0) + strength

        if strength_by_tag:
            max_strength = max(strength_by_tag.values())
            hlt_winner_tags = [
                tag for tag, s in strength_by_tag.items() if s == max_strength
            ]
            hlt_is_draw = len(hlt_winner_tags) > 1
        else:
            hlt_is_draw = True

        assert engine_is_draw == hlt_is_draw, (
            f"Draw status mismatch:\n"
            f"  engine log ranks: {log_ranks}\n"
            f"  .hlt final frame strength_by_tag: {strength_by_tag}"
        )
        assert (
            trace.is_draw == hlt_is_draw
        ), f"HaliteTraceParser.is_draw={trace.is_draw}, expected {hlt_is_draw}"

        if not engine_is_draw:
            # Log player numbers are 1-based and match player tag in .hlt
            engine_winner_num = engine_winners[0]
            hlt_winner_tag = hlt_winner_tags[0]
            assert engine_winner_num == hlt_winner_tag, (
                f"Winner tag mismatch:\n"
                f"  engine log: player #{engine_winner_num} (ranks: {log_ranks})\n"
                f"  .hlt strength: tag {hlt_winner_tag} (strength: {strength_by_tag})"
            )

            player_names_list = raw.get("player_names", [])
            hlt_winner_name = player_names_list[hlt_winner_tag - 1]
            assert trace.winner == hlt_winner_name, (
                f"HaliteTraceParser.winner='{trace.winner}', "
                f"expected '{hlt_winner_name}'"
            )

        # =================================================================
        # Check 2: frame count
        # .hlt num_frames must equal len(raw["frames"])
        # =================================================================
        assert raw.get("num_frames") == len(raw["frames"]), (
            f"num_frames field ({raw.get('num_frames')}) != "
            f"actual frame count ({len(raw['frames'])})"
        )
        assert len(trace.turns) == len(raw["frames"]), (
            f"Turn count mismatch:\n"
            f"  HaliteTraceParser produced {len(trace.turns)} turns\n"
            f"  raw .hlt has {len(raw['frames'])} frames"
        )

        # =================================================================
        # Check 3: player names
        # Names in log must match player_names in .hlt
        # =================================================================
        hlt_player_names = raw.get("player_names", [])
        for player_num, log_name in log_names.items():
            # player_num is 1-based tag; player_names is 0-indexed
            tag_idx = player_num - 1
            assert tag_idx < len(hlt_player_names), (
                f"Player #{player_num} found in log but .hlt only has "
                f"{len(hlt_player_names)} players"
            )
            hlt_name = hlt_player_names[tag_idx]
            assert log_name == hlt_name, (
                f"Player #{player_num} name mismatch:\n"
                f"  engine log: '{log_name}'\n"
                f"  .hlt player_names[{tag_idx}]: '{hlt_name}'"
            )

        # =================================================================
        # Check 4: player count
        # =================================================================
        assert raw.get("num_players") == len(log_players), (
            f"Player count mismatch:\n"
            f"  .hlt num_players: {raw.get('num_players')}\n"
            f"  log player entries: {len(log_players)}"
        )
        assert raw.get("num_players") == len(raw.get("player_names", [])), (
            f"num_players ({raw.get('num_players')}) != "
            f"len(player_names) ({len(raw.get('player_names', []))})"
        )

    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
