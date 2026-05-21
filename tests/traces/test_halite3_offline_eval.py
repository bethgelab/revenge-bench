"""
Integration tests for the Halite III subprocess offline evaluation pipeline.

Tests the round-trip: encode frames → run compiled bot (via Docker) → decode
commands → compare.

The tests compile and run the Rust bot inside the Docker image
``revenge_bench/halite3_testbot:latest`` (built from ``revenge_bench/halite3:latest``
with ``cargo build`` run during the image build).

Verification checks:
  1. encode_init produces a parseable multi-line packet.
  2. encode_turn produces a correct per-turn packet.
  3. decode_commands parses all command types correctly.
  4. query_compiled_bot returns one response per frame.
  5. eval_bot_against_hlt returns (bot, target) pairs in the right format.
  6. An unknown player_name returns [].

Requires:
  - Docker with revenge_bench/halite3:latest image available
  - revenge_bench/halite3_testbot:latest built (see _build_testbot_image helper)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

FIXTURE_HLT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "test_fixtures"
    / "traces"
    / "halite3"
    / "short_game.hlt"
)

HALITE3_BASE_IMAGE = "revenge_bench/halite3:latest"
HALITE3_TEST_IMAGE = "revenge_bench/halite3_testbot:latest"
BOT_PATH_IN_IMAGE = "/workspace/submission/target/debug/main"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True if Docker is usable and the base Halite3 image is present."""
    try:
        out = subprocess.check_output(
            ["docker", "images", "-q", HALITE3_BASE_IMAGE],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return bool(out)
    except Exception:
        return False


def _testbot_image_available() -> bool:
    """Return True if the pre-compiled test-bot image exists."""
    try:
        out = subprocess.check_output(
            ["docker", "images", "-q", HALITE3_TEST_IMAGE],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return bool(out)
    except Exception:
        return False


def _build_testbot_image() -> None:
    """
    Build the ``revenge_bench/halite3_testbot:latest`` image by running
    ``cargo build`` on top of the base image.

    Only called if the image does not already exist (checked by the
    module-level fixture).
    """
    dockerfile = (
        f"FROM {HALITE3_BASE_IMAGE}\n"
        "WORKDIR /workspace/submission\n"
        "RUN cargo build --quiet 2>&1 | grep -v '^warning' || true\n"
    )
    subprocess.check_call(
        ["docker", "build", "-t", HALITE3_TEST_IMAGE, "-"],
        input=dockerfile.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _bot_cmd() -> list[str]:
    """Return the docker run command for the pre-compiled bot."""
    return ["docker", "run", "-i", "--rm", HALITE3_TEST_IMAGE, BOT_PATH_IN_IMAGE]


# ---------------------------------------------------------------------------
# Skip condition
# ---------------------------------------------------------------------------

needs_docker = pytest.mark.skipif(
    not _docker_available(),
    reason=f"Requires Docker with {HALITE3_BASE_IMAGE}",
)


# ---------------------------------------------------------------------------
# Module-level fixture: ensure test image is built once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def ensure_testbot_image():
    """Build the pre-compiled bot image if it doesn't exist yet."""
    if not _docker_available():
        return  # tests will be skipped anyway
    if not _testbot_image_available():
        _build_testbot_image()


# ---------------------------------------------------------------------------
# Unit-level tests (no Docker needed)
# ---------------------------------------------------------------------------


class TestEncodeDecodeRoundTrip:
    """Test encode/decode functions in isolation."""

    def test_encode_init_line_count(self):
        """Init packet has: 1 constants + 1 num_players + N players + 1 dims + H rows."""
        from revenge_bench.traces.parsers.halite3 import encode_init, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        init = encode_init(data, 0)
        lines = [l for l in init.split("\n") if l]

        h = data["production_map"]["height"]
        n_players = len(data["players"])
        # 1 constants + 1 "{num_players} {my_id}" + n_players + 1 "{w} {h}" + h rows
        expected = 1 + 1 + n_players + 1 + h
        assert (
            len(lines) == expected
        ), f"Expected {expected} non-empty lines, got {len(lines)}"

    def test_encode_init_first_line_is_json(self):
        """First line of init packet must be valid JSON (game constants)."""
        import json

        from revenge_bench.traces.parsers.halite3 import encode_init, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        init = encode_init(data, 0)
        first_line = init.split("\n")[0]
        parsed = json.loads(first_line)
        assert isinstance(parsed, dict)
        assert "MAX_ENERGY" in parsed or "EXTRACT_RATIO" in parsed

    def test_encode_init_player_id_in_packet(self):
        """The impersonated player ID must appear in line 2 of the init packet."""
        from revenge_bench.traces.parsers.halite3 import encode_init, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        for pid in (0, 1):
            init = encode_init(data, pid)
            line2 = init.split("\n")[1]
            parts = line2.split()
            assert (
                int(parts[1]) == pid
            ), f"Expected my_player_id={pid} on line 2, got '{line2}'"

    def test_encode_init_map_rows_count(self):
        """Init packet must include exactly height rows of halite values."""
        from revenge_bench.traces.parsers.halite3 import encode_init, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        height = data["production_map"]["height"]
        width = data["production_map"]["width"]
        init = encode_init(data, 0)
        lines = init.split("\n")
        # Find the "width height" line
        dim_line_idx = next(
            i for i, l in enumerate(lines) if l.strip() == f"{width} {height}"
        )
        map_rows = [l for l in lines[dim_line_idx + 1 :] if l.strip()]
        assert len(map_rows) == height

    def test_encode_turn_produces_turn_number(self):
        """Per-turn packet must start with the correct turn number."""
        from revenge_bench.traces.parsers.halite3 import encode_turn, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        prod = data["production_map"]
        w, _h = prod["width"], prod["height"]
        halite_map = [[row[x]["energy"] for x in range(w)] for row in prod["grid"]]

        for turn_num in (1, 5, 10):
            pkt, halite_map = encode_turn(
                turn_num, data["full_frames"][turn_num - 1], halite_map, data
            )
            first_line = pkt.split("\n")[0]
            assert first_line == str(
                turn_num
            ), f"Expected first line '{turn_num}', got '{first_line}'"

    def test_decode_commands_empty_line(self):
        from revenge_bench.traces.parsers.halite3 import decode_commands

        assert decode_commands("") == []
        assert decode_commands("   \n") == []

    def test_decode_commands_spawn(self):
        from revenge_bench.traces.parsers.halite3 import decode_commands

        result = decode_commands("g")
        assert result == [{"type": "g"}]

    def test_decode_commands_move(self):
        from revenge_bench.traces.parsers.halite3 import decode_commands

        result = decode_commands("m 3 n")
        assert result == [{"type": "m", "id": 3, "direction": "n"}]

    def test_decode_commands_convert(self):
        from revenge_bench.traces.parsers.halite3 import decode_commands

        result = decode_commands("c 7")
        assert result == [{"type": "c", "id": 7}]

    def test_decode_commands_multiple_sorted(self):
        """decode_commands returns actions sorted by (type_priority, id)."""
        from revenge_bench.traces.parsers.halite3 import decode_commands

        result = decode_commands("g m 5 s m 2 n")
        # Expected order: move (id=2), move (id=5), spawn
        assert result[0] == {"type": "m", "id": 2, "direction": "n"}
        assert result[1] == {"type": "m", "id": 5, "direction": "s"}
        assert result[2] == {"type": "g"}

    def test_decode_commands_roundtrip_from_fixture(self):
        """decode_commands must handle all action types found in the fixture."""
        from revenge_bench.traces.parsers.halite3 import (
            _action_to_token,
            decode_commands,
            load_hlt_file,
        )

        data = load_hlt_file(FIXTURE_HLT)
        for frame in data["full_frames"][:20]:
            for _pid, moves in frame.get("moves", {}).items():
                token_str = " ".join(_action_to_token(m) for m in moves)
                decoded = decode_commands(token_str)
                # Every decoded action must have a valid type
                for act in decoded:
                    assert act["type"] in ("m", "g", "c")
                    if act["type"] == "m":
                        assert act["direction"] in ("n", "s", "e", "w", "o")

    def test_action_to_token_roundtrip(self):
        """_action_to_token is the inverse of decode_commands for single actions."""
        from revenge_bench.traces.parsers.halite3 import _action_to_token, decode_commands

        cases = [
            {"type": "g"},
            {"type": "m", "id": 4, "direction": "s"},
            {"type": "c", "id": 11},
        ]
        for act in cases:
            token = _action_to_token(act)
            decoded = decode_commands(token)
            assert len(decoded) == 1
            assert decoded[0] == act


# ---------------------------------------------------------------------------
# Integration tests (requires Docker + pre-compiled bot image)
# ---------------------------------------------------------------------------


@needs_docker
class TestQueryCompiledBot:
    """
    Tests for query_compiled_bot using the pre-compiled bot Docker image.
    """

    def test_turn_count_matches_frames(self):
        """query_compiled_bot returns one list per full_frame."""
        from revenge_bench.traces.parsers.halite3 import load_hlt_file, query_compiled_bot

        data = load_hlt_file(FIXTURE_HLT)
        # Use only first 20 frames to keep the test fast
        mini = dict(data)
        mini["full_frames"] = data["full_frames"][:20]

        result = query_compiled_bot(_bot_cmd(), mini, player_id=0, timeout=15.0)

        assert len(result) == 20, f"Expected 20 turns, got {len(result)}"

    def test_responses_are_lists_of_dicts(self):
        """Every per-turn response is a list of action dicts."""
        from revenge_bench.traces.parsers.halite3 import load_hlt_file, query_compiled_bot

        data = load_hlt_file(FIXTURE_HLT)
        mini = dict(data)
        mini["full_frames"] = data["full_frames"][:15]

        result = query_compiled_bot(_bot_cmd(), mini, player_id=0, timeout=15.0)

        for turn_idx, cmds in enumerate(result):
            assert isinstance(
                cmds, list
            ), f"Turn {turn_idx}: expected list, got {type(cmds)}"
            for act in cmds:
                assert isinstance(
                    act, dict
                ), f"Turn {turn_idx}: action is not a dict: {act}"
                assert "type" in act

    def test_valid_action_types(self):
        """All decoded action types must be one of 'm', 'g', 'c'."""
        from revenge_bench.traces.parsers.halite3 import load_hlt_file, query_compiled_bot

        data = load_hlt_file(FIXTURE_HLT)
        mini = dict(data)
        mini["full_frames"] = data["full_frames"][:15]

        result = query_compiled_bot(_bot_cmd(), mini, player_id=0, timeout=15.0)

        for turn_idx, cmds in enumerate(result):
            for act in cmds:
                assert act["type"] in (
                    "m",
                    "g",
                    "c",
                ), f"Turn {turn_idx}: unexpected action type '{act['type']}'"
                if act["type"] == "m":
                    assert act["direction"] in (
                        "n",
                        "s",
                        "e",
                        "w",
                        "o",
                    ), f"Turn {turn_idx}: unexpected direction '{act['direction']}'"

    def test_bot_spawns_ship_early(self):
        """The random bot should spawn a ship on one of the early turns."""
        from revenge_bench.traces.parsers.halite3 import load_hlt_file, query_compiled_bot

        data = load_hlt_file(FIXTURE_HLT)
        mini = dict(data)
        mini["full_frames"] = data["full_frames"][:10]

        result = query_compiled_bot(_bot_cmd(), mini, player_id=0, timeout=15.0)

        spawns = sum(1 for cmds in result for act in cmds if act["type"] == "g")
        assert spawns > 0, "Expected at least one spawn in the first 10 turns"

    def test_player_id_1_perspective(self):
        """Bot can also be run as player 1."""
        from revenge_bench.traces.parsers.halite3 import load_hlt_file, query_compiled_bot

        data = load_hlt_file(FIXTURE_HLT)
        mini = dict(data)
        mini["full_frames"] = data["full_frames"][:10]

        result = query_compiled_bot(_bot_cmd(), mini, player_id=1, timeout=15.0)

        assert len(result) == 10
        for cmds in result:
            assert isinstance(cmds, list)


@needs_docker
class TestEvalBotAgainstHlt:
    """
    Tests for eval_bot_against_hlt using the pre-compiled bot Docker image.
    """

    def test_returns_one_pair_per_frame(self):
        """eval_bot_against_hlt returns one (bot, target) pair per full_frame."""
        from revenge_bench.traces.parsers.halite3 import eval_bot_against_hlt, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        player_name = data["players"][0]["name"]

        # Monkey-patch to limit frames (avoid running 500 turns in a test)
        import revenge_bench.traces.parsers.halite3 as h3mod

        orig_load = h3mod.load_hlt_file

        def patched_load(path):
            d = orig_load(path)
            d["full_frames"] = d["full_frames"][:20]
            return d

        h3mod.load_hlt_file = patched_load
        try:
            pairs = eval_bot_against_hlt(
                _bot_cmd(), FIXTURE_HLT, player_name, timeout=15.0
            )
        finally:
            h3mod.load_hlt_file = orig_load

        assert len(pairs) == 20

    def test_pair_format(self):
        """Each pair is (list[dict], list[dict])."""
        import revenge_bench.traces.parsers.halite3 as h3mod
        from revenge_bench.traces.parsers.halite3 import eval_bot_against_hlt, load_hlt_file

        data = load_hlt_file(FIXTURE_HLT)
        player_name = data["players"][0]["name"]

        orig_load = h3mod.load_hlt_file

        def patched_load(path):
            d = orig_load(path)
            d["full_frames"] = d["full_frames"][:15]
            return d

        h3mod.load_hlt_file = patched_load
        try:
            pairs = eval_bot_against_hlt(
                _bot_cmd(), FIXTURE_HLT, player_name, timeout=15.0
            )
        finally:
            h3mod.load_hlt_file = orig_load

        for turn_idx, (bot_cmds, target_cmds) in enumerate(pairs):
            assert isinstance(bot_cmds, list), f"Turn {turn_idx}: bot_cmds is not list"
            assert isinstance(
                target_cmds, list
            ), f"Turn {turn_idx}: target_cmds is not list"
            for act in bot_cmds + target_cmds:
                assert isinstance(act, dict), f"Turn {turn_idx}: action not dict: {act}"
                assert act["type"] in ("m", "g", "c")

    def test_unknown_player_returns_empty(self):
        """An unrecognised player name returns []."""
        from revenge_bench.traces.parsers.halite3 import eval_bot_against_hlt

        pairs = eval_bot_against_hlt(
            _bot_cmd(), FIXTURE_HLT, "NoSuchPlayer", timeout=5.0
        )
        assert pairs == []

    def test_target_commands_match_fixture(self):
        """
        Target commands decoded by eval_bot_against_hlt must match what
        extract_state_action_pairs returns for the same player and frames.
        """
        import revenge_bench.traces.parsers.halite3 as h3mod
        from revenge_bench.traces.parsers.halite3 import (
            _action_to_token,
            actions_distance,
            decode_commands,
            eval_bot_against_hlt,
            load_hlt_file,
        )

        data = load_hlt_file(FIXTURE_HLT)
        player_name = data["players"][0]["name"]
        player_id_str = "0"

        # Limit to 10 frames
        orig_load = h3mod.load_hlt_file

        def patched_load(path):
            d = orig_load(path)
            d["full_frames"] = d["full_frames"][:10]
            return d

        h3mod.load_hlt_file = patched_load
        try:
            pairs = eval_bot_against_hlt(
                _bot_cmd(), FIXTURE_HLT, player_name, timeout=15.0
            )
        finally:
            h3mod.load_hlt_file = orig_load

        # Cross-check target_commands against raw fixture moves
        frames = data["full_frames"][:10]
        for turn_idx, (_, target_cmds) in enumerate(pairs):
            raw_moves = frames[turn_idx].get("moves", {}).get(player_id_str, [])
            expected = decode_commands(" ".join(_action_to_token(m) for m in raw_moves))
            assert actions_distance(target_cmds, expected) == 0.0, (
                f"Turn {turn_idx}: target_cmds mismatch\n"
                f"  got:      {target_cmds}\n"
                f"  expected: {expected}"
            )


@needs_docker
class TestActionsDistanceIntegration:
    """
    Verify actions_distance works correctly on real bot and target output.
    """

    def test_actions_distance_on_real_pairs(self):
        """actions_distance must not raise on real pairs from eval_bot_against_hlt."""
        import revenge_bench.traces.parsers.halite3 as h3mod
        from revenge_bench.traces.parsers.halite3 import (
            actions_distance,
            eval_bot_against_hlt,
            load_hlt_file,
        )

        data = load_hlt_file(FIXTURE_HLT)
        player_name = data["players"][0]["name"]

        orig_load = h3mod.load_hlt_file

        def patched_load(path):
            d = orig_load(path)
            d["full_frames"] = d["full_frames"][:15]
            return d

        h3mod.load_hlt_file = patched_load
        try:
            pairs = eval_bot_against_hlt(
                _bot_cmd(), FIXTURE_HLT, player_name, timeout=15.0
            )
        finally:
            h3mod.load_hlt_file = orig_load

        for turn_idx, (bot_cmds, target_cmds) in enumerate(pairs):
            result = actions_distance(bot_cmds, target_cmds)
            assert isinstance(
                result, float
            ), f"Turn {turn_idx}: actions_distance returned non-float"
            assert (
                0.0 <= result <= 1.0
            ), f"Turn {turn_idx}: actions_distance not in [0.0, 1.0]: {result}"

    def test_actions_distance_self(self):
        """actions_distance(x, x) is always 0.0."""
        import revenge_bench.traces.parsers.halite3 as h3mod
        from revenge_bench.traces.parsers.halite3 import (
            actions_distance,
            eval_bot_against_hlt,
            load_hlt_file,
        )

        data = load_hlt_file(FIXTURE_HLT)
        player_name = data["players"][0]["name"]

        orig_load = h3mod.load_hlt_file

        def patched_load(path):
            d = orig_load(path)
            d["full_frames"] = d["full_frames"][:10]
            return d

        h3mod.load_hlt_file = patched_load
        try:
            pairs = eval_bot_against_hlt(
                _bot_cmd(), FIXTURE_HLT, player_name, timeout=15.0
            )
        finally:
            h3mod.load_hlt_file = orig_load

        for turn_idx, (_, target_cmds) in enumerate(pairs):
            assert (
                actions_distance(target_cmds, target_cmds) == 0.0
            ), f"Turn {turn_idx}: actions_distance(x, x) is not 0.0 for {target_cmds}"
