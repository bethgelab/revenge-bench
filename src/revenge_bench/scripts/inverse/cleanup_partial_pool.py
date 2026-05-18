"""Classify and (optionally) delete partially-completed tournament directories
under a single pool-run log dir.

Designed to chain with `scripts/inverse/run_pool.sh --timestamp <old> --resume` to retry only
the tournaments that crashed mid-run, without disturbing the ones that
already finished.

Usage:
    # Dry-run: list every tournament with its classification, no changes.
    python -m revenge_bench.scripts.inverse.cleanup_partial_pool \\
        logs/gemma_4_26b_a4b_full_pool_20260426_030536

    # Actually delete the dirs that hit a recoverable error.
    python -m revenge_bench.scripts.inverse.cleanup_partial_pool \\
        logs/gemma_4_26b_a4b_full_pool_20260426_030536 --delete

    # Also delete the dirs that hit a permanent (context-length) error
    # — only useful if you've also changed the config to lower step_limit etc.
    python -m revenge_bench.scripts.inverse.cleanup_partial_pool \\
        logs/gemma_4_26b_a4b_full_pool_20260426_030536 --delete --include-permanent
"""
from __future__ import annotations

import argparse
import enum
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Iterator


class Classification(str, enum.Enum):
    COMPLETE = "complete"
    TRANSIENT_ERROR = "transient_error"
    PERMANENT_ERROR = "permanent_error"
    UNKNOWN = "unknown"


# Substring matchers, applied in order. First match wins.
_PERMANENT_PATTERNS = (
    "maximum context length is",
    "BadRequestError",
)
_TRANSIENT_PATTERNS = (
    "OpenrouterException - Unable to get json response",
    "OpenrouterException - Server disconnected",
    "litellm.exceptions.APIError",
    "litellm.exceptions.RateLimitError",
    "litellm.exceptions.Timeout",
    # Generic Python traceback — catches mid-run process kills (sleep, OOM,
    # SIGKILL) where the specific litellm pattern never made it to disk.
    # Safe under round-count gating: complete tournaments are returned
    # COMPLETE before this pattern list is consulted, so retries that
    # happened mid-run don't false-positive.
    "Traceback (most recent call last):",
)
# Cap how many bytes we read of any single log file. Some tournaments
# accumulate huge contexts before crashing (e.g. context-length BadRequest
# from OpenRouter), so the relevant traceback can appear tens of MB into
# the file. The cap is only paid for partial tournaments — fully-completed
# ones don't read the log at all.
_LOG_READ_CAP_BYTES = 64_000_000


def _read_log(log_path: Path) -> str:
    """Read up to _LOG_READ_CAP_BYTES of a log file, decoded leniently."""
    if not log_path.exists():
        return ""
    with log_path.open("rb") as f:
        return f.read(_LOG_READ_CAP_BYTES).decode("utf-8", errors="replace")


def find_tournaments(pool_dir: Path) -> Iterator[Path]:
    """Yield every <game>/target<hash>/seed<N>/ directory under pool_dir.

    Each yielded path is a single tournament — one (target, seed) pair.
    A multi-seed run produces one yield per seed; a single-seed run
    produces one yield per target.

    A target<hash>/ dir with no seed*/ children produces a stderr warning
    and is skipped. This usually means the pool run crashed before the
    target produced any output and the dir is a stub.
    """
    for game_dir in sorted(pool_dir.iterdir()):
        if not game_dir.is_dir():
            continue
        for target_dir in sorted(game_dir.iterdir()):
            if not (target_dir.is_dir() and target_dir.name.startswith("target")):
                continue
            found_seed = False
            for seed_dir in sorted(target_dir.iterdir()):
                if seed_dir.is_dir() and seed_dir.name.startswith("seed"):
                    found_seed = True
                    yield seed_dir
            if not found_seed:
                print(
                    f"WARNING: {target_dir.relative_to(pool_dir)} has no seed*/ "
                    "children — skipped (stub or pre-seed-layout dir).",
                    file=sys.stderr,
                )


def _round_count(tournament_dir: Path) -> int:
    rounds_dir = tournament_dir / "rounds"
    if not rounds_dir.is_dir():
        return 0
    return sum(1 for _ in rounds_dir.glob("round_*.tar.gz"))


def classify_tournament(tournament_dir: Path, *, expected_rounds: int) -> Classification:
    """Classify a tournament by round-file count first, log content second.

    Logic:
      - If round count >= expected -> COMPLETE.  We don't scan the log in
        this case so that mid-tournament transient errors that ultimately
        recovered don't false-positive as broken.
      - Otherwise, scan the whole everything.log:
          - If a permanent-error pattern matches -> PERMANENT_ERROR.
          - If a transient-error pattern matches -> TRANSIENT_ERROR.
          - Else -> UNKNOWN (don't auto-touch).
    """
    n = _round_count(tournament_dir)
    if n >= expected_rounds:
        return Classification.COMPLETE

    text = _read_log(tournament_dir / "everything.log")
    if any(p in text for p in _PERMANENT_PATTERNS):
        return Classification.PERMANENT_ERROR
    if any(p in text for p in _TRANSIENT_PATTERNS):
        return Classification.TRANSIENT_ERROR
    return Classification.UNKNOWN


def detect_expected_rounds(pool_dir: Path) -> int:
    """Use the modal round count across the pool as the 'expected' value.

    Empirically, a fully-finished tournament in this codebase emits one
    `round_<N>.tar.gz` file per executed round. Different configs yield
    different counts (rounds=5 typically yields 6 files), so don't hardcode.
    """
    counts = [_round_count(t) for t in find_tournaments(pool_dir)]
    if not counts:
        return 0
    return Counter(counts).most_common(1)[0][0]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("pool_dir", type=Path, help="logs/<pool_name>_<timestamp>/ directory")
    p.add_argument("--delete", action="store_true",
                   help="Actually delete dirs classified as recoverable.")
    p.add_argument("--include-permanent", action="store_true",
                   help="Also delete dirs with permanent (context-length) errors.")
    p.add_argument("--include-unknown", action="store_true",
                   help="Also delete dirs whose log doesn't match a known error pattern. "
                        "Useful when the failure trace was written to the scripts/inverse/run_pool.sh "
                        "per-target wrapper log instead of everything.log.")
    p.add_argument("--expected-rounds", type=int, default=None,
                   help="Override expected round count (default: modal across pool).")
    args = p.parse_args(argv)

    pool_dir: Path = args.pool_dir
    if not pool_dir.is_dir():
        print(f"ERROR: not a directory: {pool_dir}", file=sys.stderr)
        return 2

    expected = args.expected_rounds
    if expected is None:
        expected = detect_expected_rounds(pool_dir)
    if expected == 0:
        print(f"ERROR: no tournaments found under {pool_dir}", file=sys.stderr)
        return 2

    rows: list[tuple[Classification, int, Path]] = []
    for t in find_tournaments(pool_dir):
        c = classify_tournament(t, expected_rounds=expected)
        rows.append((c, _round_count(t), t))

    by_class: Counter[Classification] = Counter(c for c, _, _ in rows)
    print(f"Pool: {pool_dir}")
    print(f"Expected rounds (modal): {expected}")
    print(f"Tournaments: {len(rows)}")
    for c in Classification:
        print(f"  {c.value}: {by_class[c]}")
    print()

    deletable = {Classification.TRANSIENT_ERROR}
    if args.include_permanent:
        deletable.add(Classification.PERMANENT_ERROR)
    if args.include_unknown:
        deletable.add(Classification.UNKNOWN)

    print(f"{'CLASS':<18} {'ROUNDS':<8} TARGET")
    for c, n, t in rows:
        if c is Classification.COMPLETE:
            continue
        print(f"  {c.value:<16} {n:<8} {t.relative_to(pool_dir)}")

    to_delete = [t for c, _, t in rows if c in deletable]
    if not to_delete:
        print("\nNothing to delete.")
        return 0

    if not args.delete:
        print(f"\nWould delete {len(to_delete)} dirs (run again with --delete).")
        return 0

    print(f"\nDeleting {len(to_delete)} tournament dirs:")
    for t in to_delete:
        print(f"  rm -rf {t}")
        shutil.rmtree(t)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
