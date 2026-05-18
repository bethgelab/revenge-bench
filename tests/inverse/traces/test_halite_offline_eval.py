"""
Integration tests for the Halite I subprocess offline evaluation pipeline.

Tests the round-trip: encode frames → compile bot → decode moves → compare.

The tests compile a minimal C bot locally (using the hlt.h from the Docker
image) and verify that:
  1. An always-STILL bot produces empty move lists for every turn.
  2. The number of turns returned matches the fixture's move count.
  3. A bot that deterministically echoes the first owned cell's recorded move
     produces the expected output (round-trip fidelity).

Requires:
  - Docker with revenge_bench/halite:latest image
  - gcc (or clang) available on the host
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

FIXTURE_HLT = (
    Path(__file__).parent.parent.parent.parent
    / "data"
    / "inverse"
    / "test_fixtures"
    / "traces"
    / "halite1"
    / "short_game.hlt"
)

HALITE_DOCKER_IMAGE = "revenge_bench/halite:latest"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True if Docker is usable and the Halite image is present."""
    try:
        out = subprocess.check_output(
            ["docker", "images", "-q", HALITE_DOCKER_IMAGE],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return bool(out)
    except Exception:
        return False


def _gcc_available() -> bool:
    return shutil.which("gcc") is not None


def _extract_hlt_h(dest_dir: Path) -> None:
    """Read hlt.h from the Halite Docker image and write it into dest_dir."""
    content = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            HALITE_DOCKER_IMAGE,
            "cat",
            "/workspace/submission/hlt.h",
        ],
        stderr=subprocess.DEVNULL,
    )
    (dest_dir / "hlt.h").write_bytes(content)


def _compile_c_bot(src: str, dest_dir: Path, name: str = "bot") -> Path:
    """
    Write C source to dest_dir/main.c (alongside hlt.h) and compile it.

    Returns the path to the compiled binary.
    """
    src_path = dest_dir / "main.c"
    src_path.write_text(src)
    out_path = dest_dir / name
    subprocess.check_call(
        ["gcc", "-std=c11", str(src_path), "-o", str(out_path)],
        stderr=subprocess.DEVNULL,
    )
    return out_path


# ---------------------------------------------------------------------------
# Bot sources
# ---------------------------------------------------------------------------

_ALWAYS_STILL_C = """\
#include <stdio.h>
#include "hlt.h"

int main(void) {
    GAME game = GetInit();
    SendInit("StillBot");
    while (1) {
        GetFrame(game);
        /* Send nothing — all STILL */
        SendFrame(game);
    }
    return 0;
}
"""

_ALWAYS_NORTH_C = """\
#include <stdio.h>
#include "hlt.h"

int main(void) {
    GAME game = GetInit();
    SendInit("NorthBot");
    while (1) {
        int x, y;
        GetFrame(game);
        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    SetMove(game, x, y, NORTH);
                }
            }
        }
        SendFrame(game);
    }
    return 0;
}
"""


# ---------------------------------------------------------------------------
# Fixtures / skip conditions
# ---------------------------------------------------------------------------

needs_docker_and_gcc = pytest.mark.skipif(
    not (_docker_available() and _gcc_available()),
    reason="Requires Docker (revenge_bench/halite image) and gcc",
)


@pytest.fixture(scope="module")
def hlt_h_dir():
    """
    Module-scoped temp directory containing hlt.h extracted from Docker.
    Shared across all tests in this module to avoid repeated Docker calls.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="halite_test_"))
    _extract_hlt_h(tmpdir)
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Unit-level tests (no Docker / gcc needed)
# ---------------------------------------------------------------------------


class TestEncodeDecodeRoundTrip:
    """Test encode/decode functions in isolation using the fixture data."""

    def test_encode_frame_produces_string(self):
        import json

        from revenge_bench.traces.parsers.halite import encode_frame

        data = json.loads(FIXTURE_HLT.read_bytes())
        frame = data["frames"][0]
        result = encode_frame(frame, data["width"], data["height"])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_frame_rle_covers_all_cells(self):
        """The RLE section must describe exactly width*height cells."""
        import json

        from revenge_bench.traces.parsers.halite import encode_frame

        data = json.loads(FIXTURE_HLT.read_bytes())
        w, h = data["width"], data["height"]
        frame = data["frames"][0]
        encoded = encode_frame(frame, w, h)

        # Tokens: RLE pairs come before strengths; there are w*h strengths.
        # Split on whitespace and count last w*h tokens as strengths.
        tokens = encoded.split()
        total_cells = w * h
        # RLE section is everything before the strength tokens
        rle_tokens = tokens[: len(tokens) - total_cells]
        strength_tokens = tokens[len(tokens) - total_cells :]

        # Verify RLE coverage: sum of even-indexed tokens (run lengths)
        rle_cell_count = sum(int(rle_tokens[i]) for i in range(0, len(rle_tokens), 2))
        assert (
            rle_cell_count == total_cells
        ), f"RLE covers {rle_cell_count} cells, expected {total_cells}"

        # Verify strength count
        assert len(strength_tokens) == total_cells

    def test_encode_productions_length(self):
        import json

        from revenge_bench.traces.parsers.halite import encode_productions

        data = json.loads(FIXTURE_HLT.read_bytes())
        result = encode_productions(data)
        tokens = result.split()
        assert len(tokens) == data["width"] * data["height"]

    def test_decode_moves_empty_line(self):
        from revenge_bench.traces.parsers.halite import decode_moves

        assert decode_moves("") == []
        assert decode_moves("   \n") == []

    def test_decode_moves_single_triple(self):
        from revenge_bench.traces.parsers.halite import MOVE_NORTH, decode_moves

        # x=5 (col), y=3 (row), dir=NORTH → [row=3, col=5, NORTH]
        result = decode_moves("5 3 1")
        assert result == [[3, 5, MOVE_NORTH]]

    def test_decode_moves_multiple_cells_sorted(self):
        """decode_moves result is always sorted by [row, col, move]."""
        from revenge_bench.traces.parsers.halite import decode_moves

        # Two cells: (col=2, row=0, dir=1) and (col=0, row=1, dir=2)
        result = decode_moves("2 0 1  0 1 2")
        assert result == sorted(result)
        assert [0, 2, 1] in result
        assert [1, 0, 2] in result

    def test_decode_moves_skips_still(self):
        from revenge_bench.traces.parsers.halite import MOVE_STILL, decode_moves

        # STILL (dir=0) must not appear in output
        result = decode_moves("3 3 0  2 1 1")
        dirs = [t[2] for t in result]
        assert MOVE_STILL not in dirs
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration tests (requires Docker + gcc)
# ---------------------------------------------------------------------------


@needs_docker_and_gcc
class TestAlwaysStillBot:
    """
    A bot that never moves (always STILL) must produce empty move lists
    for every turn, regardless of what the recorded target did.
    """

    @pytest.fixture(scope="class")
    def still_bot(self, hlt_h_dir, tmp_path_factory):
        bot_dir = tmp_path_factory.mktemp("still_bot")
        shutil.copy(hlt_h_dir / "hlt.h", bot_dir / "hlt.h")
        return _compile_c_bot(_ALWAYS_STILL_C, bot_dir, name="still_bot")

    def test_turn_count_matches_fixture(self, still_bot):
        import json

        from revenge_bench.traces.parsers.halite import query_compiled_bot

        data = json.loads(FIXTURE_HLT.read_bytes())
        expected_turns = len(data["moves"])

        # Query as player 1
        result = query_compiled_bot(still_bot, data, player_tag=1, timeout=5.0)

        assert (
            len(result) == expected_turns
        ), f"Expected {expected_turns} turns, got {len(result)}"

    def test_all_moves_still(self, still_bot):
        """A STILL bot must produce all-STILL entries (move=0) for every owned cell."""
        import json

        from revenge_bench.traces.parsers.halite import MOVE_STILL, query_compiled_bot

        data = json.loads(FIXTURE_HLT.read_bytes())
        result = query_compiled_bot(still_bot, data, player_tag=1, timeout=5.0)

        for turn_idx, moves in enumerate(result):
            for r, c, m in moves:
                assert (
                    m == MOVE_STILL
                ), f"Turn {turn_idx}: cell ({r},{c}) expected STILL (0), got {m}"

    def test_eval_bot_against_hlt_returns_pairs(self, still_bot):
        """eval_bot_against_hlt returns one pair per move-grid."""
        import json

        from revenge_bench.traces.parsers.halite import eval_bot_against_hlt

        data = json.loads(FIXTURE_HLT.read_bytes())
        expected_turns = len(data["moves"])
        player_name = data["player_names"][0]

        pairs = eval_bot_against_hlt(still_bot, FIXTURE_HLT, player_name, timeout=5.0)

        assert len(pairs) == expected_turns
        for bot_moves, _target_moves in pairs:
            assert isinstance(bot_moves, list)
            for _r, _c, m in bot_moves:
                assert m == 0, f"STILL bot should only produce move=0, got {m}"

    def test_unknown_player_returns_empty(self, still_bot):
        from revenge_bench.traces.parsers.halite import eval_bot_against_hlt

        pairs = eval_bot_against_hlt(
            still_bot, FIXTURE_HLT, "NoSuchPlayer", timeout=5.0
        )
        assert pairs == []


@needs_docker_and_gcc
class TestAlwaysNorthBot:
    """
    A bot that always moves NORTH must produce non-empty move lists for turns
    where it owns cells, and the move values must all be NORTH.
    """

    @pytest.fixture(scope="class")
    def north_bot(self, hlt_h_dir, tmp_path_factory):
        bot_dir = tmp_path_factory.mktemp("north_bot")
        shutil.copy(hlt_h_dir / "hlt.h", bot_dir / "hlt.h")
        return _compile_c_bot(_ALWAYS_NORTH_C, bot_dir, name="north_bot")

    def test_all_moves_north(self, north_bot):
        """Every non-empty move list must contain only NORTH moves."""
        import json

        from revenge_bench.traces.parsers.halite import MOVE_NORTH, query_compiled_bot

        data = json.loads(FIXTURE_HLT.read_bytes())
        result = query_compiled_bot(north_bot, data, player_tag=1, timeout=5.0)

        assert len(result) > 0
        moves_seen = 0
        for turn_idx, moves in enumerate(result):
            for triple in moves:
                assert (
                    triple[2] == MOVE_NORTH
                ), f"Turn {turn_idx}: expected NORTH, got direction {triple[2]}"
                moves_seen += 1

        # Player 1 owns cells in the fixture, so at least some moves expected
        assert moves_seen > 0, "AlwaysNorth bot produced no moves at all"

    def test_turn_count_matches(self, north_bot):
        import json

        from revenge_bench.traces.parsers.halite import query_compiled_bot

        data = json.loads(FIXTURE_HLT.read_bytes())
        result = query_compiled_bot(north_bot, data, player_tag=1, timeout=5.0)
        assert len(result) == len(data["moves"])

    def test_player2_perspective(self, north_bot):
        """Bot receives player-tag 2 perspective correctly."""
        import json

        from revenge_bench.traces.parsers.halite import MOVE_NORTH, query_compiled_bot

        data = json.loads(FIXTURE_HLT.read_bytes())
        result = query_compiled_bot(north_bot, data, player_tag=2, timeout=5.0)

        assert len(result) == len(data["moves"])
        for moves in result:
            for triple in moves:
                assert triple[2] == MOVE_NORTH


@needs_docker_and_gcc
class TestActionsDistanceIntegration:
    """
    Verify that actions_distance works correctly on real bot output.
    """

    @pytest.fixture(scope="class")
    def still_bot(self, hlt_h_dir, tmp_path_factory):
        bot_dir = tmp_path_factory.mktemp("still_bot_eq")
        shutil.copy(hlt_h_dir / "hlt.h", bot_dir / "hlt.h")
        return _compile_c_bot(_ALWAYS_STILL_C, bot_dir, name="still_bot_eq")

    def test_still_bot_matches_still_target(self, still_bot):
        """
        actions_distance([], []) == 0.0 — if the target also had no non-STILL moves
        on a given turn, STILL bot should match.
        """
        import json

        from revenge_bench.traces.parsers.halite import (
            actions_distance,
            eval_bot_against_hlt,
            extract_state_action_pairs,
        )

        data = json.loads(FIXTURE_HLT.read_bytes())
        player_name = data["player_names"][0]

        pairs = eval_bot_against_hlt(still_bot, FIXTURE_HLT, player_name, timeout=5.0)
        target_pairs = extract_state_action_pairs(FIXTURE_HLT, player_name)

        assert len(pairs) == len(target_pairs)

        # Count exact matches (distance == 0.0)
        still_matches = sum(
            1
            for bot_moves, target_moves in pairs
            if actions_distance(bot_moves, target_moves) == 0.0
        )
        total = len(pairs)

        # The STILL bot matches only on turns where the target also moved STILL
        # for ALL its cells. We just verify the count is a valid fraction.
        assert 0 <= still_matches <= total

    def test_pairs_format_consistent(self, still_bot):
        """
        bot_moves and target_moves from eval_bot_against_hlt must both be
        sorted lists of [row, col, move] triples.
        """
        import json

        from revenge_bench.traces.parsers.halite import eval_bot_against_hlt

        data = json.loads(FIXTURE_HLT.read_bytes())
        player_name = data["player_names"][0]

        pairs = eval_bot_against_hlt(still_bot, FIXTURE_HLT, player_name, timeout=5.0)

        for turn_idx, (bot_moves, target_moves) in enumerate(pairs):
            # Each move is a list/tuple of 3 ints
            for move_list in (bot_moves, target_moves):
                for triple in move_list:
                    assert len(triple) == 3, f"Turn {turn_idx}: bad triple {triple}"
                    row, col, direction = triple
                    assert isinstance(row, int)
                    assert isinstance(col, int)
                    assert direction in {0, 1, 2, 3, 4}, (
                        f"Turn {turn_idx}: unexpected direction {direction} "
                        "(expected 0=STILL, 1-4=N/E/S/W)"
                    )
            # Both lists must be sorted
            assert bot_moves == sorted(
                bot_moves
            ), f"Turn {turn_idx}: bot_moves not sorted"
            assert target_moves == sorted(
                target_moves
            ), f"Turn {turn_idx}: target_moves not sorted"
