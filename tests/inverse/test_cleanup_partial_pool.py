"""Tests for cleanup_partial_pool's classifier."""
from __future__ import annotations

from pathlib import Path

import pytest

from revenge_bench.scripts.inverse.cleanup_partial_pool import (
    Classification,
    classify_tournament,
    find_tournaments,
)


def _make_tournament(
    base: Path,
    game: str,
    target_hash: str,
    *,
    n_rounds: int,
    log_tail: str,
    seed: int = 42,
) -> Path:
    """Create a fake <pool>/<game>/target<hash>/seed<N>/ dir on disk.

    Returns the seed dir (the unit `cleanup_partial_pool` operates on).
    """
    sdir = base / game / f"target{target_hash}" / f"seed{seed}"
    (sdir / "rounds").mkdir(parents=True)
    for i in range(n_rounds):
        (sdir / "rounds" / f"round_{i}.tar.gz").write_bytes(b"")
    (sdir / "metadata.json").write_text("{}")
    (sdir / "everything.log").write_text(log_tail)
    return sdir


def test_complete_tournament(tmp_path: Path):
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=6,
                         log_tail="Tournament finished\n")
    assert classify_tournament(t, expected_rounds=6) is Classification.COMPLETE


def test_transient_unable_to_get_json(tmp_path: Path):
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=3,
                         log_tail=(
                             "Traceback (most recent call last):\n"
                             "  File \"...\"\n"
                             "litellm.exceptions.APIError: litellm.APIError: "
                             "APIError: OpenrouterException - Unable to get "
                             "json response - Expecting value: line 1\n"))
    assert classify_tournament(t, expected_rounds=6) is Classification.TRANSIENT_ERROR


def test_transient_server_disconnected(tmp_path: Path):
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=2,
                         log_tail=(
                             "litellm.exceptions.APIError: litellm.APIError: "
                             "APIError: OpenrouterException - Server "
                             "disconnected without sending a response.\n"))
    assert classify_tournament(t, expected_rounds=6) is Classification.TRANSIENT_ERROR


def test_permanent_context_overflow(tmp_path: Path):
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=5,
                         log_tail=(
                             "litellm.exceptions.BadRequestError: "
                             "litellm.BadRequestError: OpenrouterException - "
                             "{\"error\":{\"message\":\"This endpoint's "
                             "maximum context length is 262144 tokens. "
                             "However, you requested about 3069389 tokens\"}}\n"))
    assert classify_tournament(t, expected_rounds=6) is Classification.PERMANENT_ERROR


def test_unknown_low_round_count_no_traceback(tmp_path: Path):
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=2,
                         log_tail="some normal log line\n")
    assert classify_tournament(t, expected_rounds=6) is Classification.UNKNOWN


def test_find_tournaments_walks_all_games(tmp_path: Path):
    _make_tournament(tmp_path, "halite", "aaa", n_rounds=6, log_tail="ok\n")
    _make_tournament(tmp_path, "robocode", "bbb", n_rounds=2,
                     log_tail="litellm.exceptions.APIError\n")
    found = list(find_tournaments(tmp_path))
    assert len(found) == 2
    # Each yielded path is the per-seed dir, parented under target<hash>/.
    assert {p.name for p in found} == {"seed42"}
    assert {p.parent.name for p in found} == {"targetaaa", "targetbbb"}
    assert {p.parent.parent.name for p in found} == {"halite", "robocode"}


def test_complete_tournament_ignores_mid_run_transient_traceback(tmp_path: Path):
    """A tournament that hit transient errors but completed all rounds is COMPLETE."""
    log_text = (
        "round 0 starting\n"
        + ("x" * 200_000)  # filler — pushes the traceback well past any small tail window
        + "litellm.exceptions.APIError: transient retry hiccup\n"
        + ("y" * 200_000)
        + "round 5 done\nMetadata saved\n"
    )
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=6,
                         log_tail=log_text)
    assert classify_tournament(t, expected_rounds=6) is Classification.COMPLETE


def test_partial_tournament_finds_error_outside_tail(tmp_path: Path):
    """A partial tournament whose error is mid-file (not in the last 32KB) is still classified."""
    log_text = (
        "litellm.exceptions.APIError: real failure that aborted\n"
        + ("x" * 200_000)  # filler so the error is far from the EOF
        + "Metadata saved\n"
    )
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=3,
                         log_tail=log_text)
    assert classify_tournament(t, expected_rounds=6) is Classification.TRANSIENT_ERROR


def test_partial_tournament_with_only_generic_traceback(tmp_path: Path):
    """A partial tournament whose log has only a generic Traceback (no
    specific litellm pattern) is still TRANSIENT_ERROR — covers process-kill
    / sleep / OOM cases where the wrapping litellm exception never wrote.
    """
    t = _make_tournament(tmp_path, "halite", "abc",
                         n_rounds=4,
                         log_tail=(
                             "round 0 ok\n"
                             "Traceback (most recent call last):\n"
                             "  File \"/foo/bar.py\", line 10, in <module>\n"
                             "Some non-litellm exception happened here\n"
                             "round 1 also ok\n"
                             "Metadata saved\n"))
    assert classify_tournament(t, expected_rounds=6) is Classification.TRANSIENT_ERROR


def test_find_tournaments_yields_one_per_seed(tmp_path: Path):
    """A target with two seed dirs yields two tournaments, classified independently."""
    complete = _make_tournament(
        tmp_path, "halite", "aaa", n_rounds=6, log_tail="ok\n", seed=42,
    )
    partial = _make_tournament(
        tmp_path, "halite", "aaa",
        n_rounds=2,
        log_tail="litellm.exceptions.APIError: transient\n",
        seed=100,
    )
    found = sorted(find_tournaments(tmp_path))
    assert found == sorted([complete, partial])
    assert classify_tournament(complete, expected_rounds=6) is Classification.COMPLETE
    assert classify_tournament(partial, expected_rounds=6) is Classification.TRANSIENT_ERROR


def test_find_tournaments_warns_on_target_with_no_seed_dirs(tmp_path: Path, capsys):
    """A target<hash>/ stub with no seed*/ children is skipped with a stderr warning."""
    # One real tournament so find_tournaments doesn't bail at the game-dir level.
    _make_tournament(tmp_path, "halite", "aaa", n_rounds=6, log_tail="ok\n")
    # A stub target with no seed dirs.
    (tmp_path / "halite" / "targetbbb").mkdir()

    found = list(find_tournaments(tmp_path))
    assert len(found) == 1
    assert found[0].parent.name == "targetaaa"
    captured = capsys.readouterr()
    assert "targetbbb" in captured.err
    assert "no seed" in captured.err
