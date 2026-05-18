"""Trim disk usage in pool log dirs by removing analysis-irrelevant artifacts.

Two cleanup tiers:
  Tier 1: delete players/learner/changes_r*.json (workspace git diffs;
          ~68 GB across the 6 main full_pool runs).
  Tier 2: repack rounds/round_*.tar.gz to keep only the entries needed
          for distance-history / per-action analysis: <N>/traces.json
          and <N>/results.json. Drops <N>/learner_code/ and <N>/opp_*/.

Preserved (untouched by either tier):
  - metadata.json
  - players/learner/learner_r*.traj.json
  - top-level *.log files
  - <N>/traces.json + <N>/results.json inside the repacked tars (Tier 2 only)

Usage:
  scripts/inverse/cleanup_log_artifacts.py <pool_dir> [<pool_dir> ...] \\
      --tier {1,2,both} [--apply] [--parallel N]

Default mode is dry-run: prints what would be deleted/repacked and the byte
totals, then exits without modifying anything. Pass --apply to execute.

Idempotent. Safe to interrupt: each repack swaps via os.replace on the same
filesystem (atomic).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import os
import tarfile

GAMES = ("battlesnake", "halite", "huskybench", "robocode", "robotrumble")


def iter_seed_dirs(pool_dir: Path):
    """Yield every <pool>/<game>/target<hash>/seed*/ directory."""
    for game in GAMES:
        game_dir = pool_dir / game
        if not game_dir.is_dir():
            continue
        for tgt in sorted(game_dir.iterdir()):
            if not (tgt.is_dir() and tgt.name.startswith("target")):
                continue
            for sd in sorted(tgt.iterdir()):
                if sd.is_dir() and sd.name.startswith("seed"):
                    yield sd


# Basenames inside a round tar that we keep, but ONLY when they sit
# directly under the round dir (i.e. exactly two path components:
# "<round>/traces.json", "<round>/results.json"). A deeper file with the
# same basename — e.g. "0/learner_code/workspace/traces.json" — is NOT kept.
_TIER2_KEEP_BASENAMES = frozenset({"traces.json", "results.json"})


def _is_keep_path(name: str) -> bool:
    parts = name.split("/")
    return len(parts) == 2 and parts[1] in _TIER2_KEEP_BASENAMES


def _is_already_minimal(tar_path: Path) -> bool:
    """True iff every regular-file member sits at <round>/{traces.json,results.json}."""
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            if not _is_keep_path(m.name):
                return False
    return True


def repack_round_tar(tar_path: Path) -> int:
    """Rewrite tar_path in place keeping only <round>/traces.json and
    <round>/results.json. Returns bytes saved (0 if already minimal).

    Drops directory entries entirely — Python's tarfile reconstructs parent
    dirs implicitly during extraction. Atomic: writes to tar_path + '.repack-tmp'
    then os.replace().
    """
    if _is_already_minimal(tar_path):
        return 0

    bytes_before = tar_path.stat().st_size
    tmp_path = tar_path.with_suffix(tar_path.suffix + ".repack-tmp")

    try:
        with tarfile.open(tar_path, "r:gz") as src, \
             tarfile.open(tmp_path, "w:gz") as dst:
            for m in src.getmembers():
                if not m.isfile():
                    continue
                if not _is_keep_path(m.name):
                    continue
                f = src.extractfile(m)
                if f is None:
                    continue
                dst.addfile(m, f)
        os.replace(tmp_path, tar_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return bytes_before - tar_path.stat().st_size


def run_tier1(pool_dirs, *, apply: bool) -> int:
    """Delete players/learner/changes_r*.json under every seed dir."""
    print(f"\n=== Tier 1 ({'APPLY' if apply else 'DRY-RUN'}): "
          f"delete players/learner/changes_r*.json ===")
    grand_bytes = 0
    grand_count = 0
    for pool in pool_dirs:
        pool_bytes = 0
        pool_count = 0
        for sd in iter_seed_dirs(pool):
            for f in sorted((sd / "players" / "learner").glob("changes_r*.json")):
                size = f.stat().st_size
                pool_bytes += size
                pool_count += 1
                if apply:
                    f.unlink()
        print(f"  {pool.name}: {pool_count} files, {pool_bytes / 1e9:.2f} GB")
        grand_bytes += pool_bytes
        grand_count += pool_count
    print(f"  TOTAL: {grand_count} files, {grand_bytes / 1e9:.2f} GB"
          f"{'' if apply else '  (dry-run — pass --apply to delete)'}")
    return 0


def _iter_round_tars(pool_dirs):
    for pool in pool_dirs:
        for sd in iter_seed_dirs(pool):
            rounds = sd / "rounds"
            if not rounds.is_dir():
                continue
            for tar_path in sorted(rounds.glob("round_*.tar.gz")):
                yield pool, tar_path


def run_tier2(pool_dirs, *, apply: bool, parallel: int) -> int:
    """Repack rounds/round_*.tar.gz keeping only traces.json + results.json."""
    from concurrent.futures import ThreadPoolExecutor

    print(f"\n=== Tier 2 ({'APPLY' if apply else 'DRY-RUN'}): "
          f"repack round_*.tar.gz keeping only traces+results ===")

    work = list(_iter_round_tars(pool_dirs))
    print(f"  candidate tars: {len(work)}")

    if not apply:
        # Dry-run: estimate by reading current sizes; we can't predict
        # post-repack size without doing the work, so just report the
        # original byte total in scope.
        per_pool: dict[Path, int] = {}
        for pool, tar in work:
            per_pool[pool] = per_pool.get(pool, 0) + tar.stat().st_size
        for pool, b in per_pool.items():
            print(f"  {pool.name}: {b / 1e9:.2f} GB of round tars in scope")
        print("  (re-run with --apply to actually repack. Per-arena savings "
              "vary widely: ~99% on battlesnake/robocode/robotrumble/huskybench, "
              "~38% on halite. See the implementation plan for measured numbers.)")
        return 0

    # Apply path: optionally threaded. Note: tarfile gzip is largely C-level
    # work that releases the GIL inconsistently; expect modest speedup from
    # threading, mostly via I/O overlap.
    saved_total = 0
    skipped = 0
    failed = 0

    def _do(args):
        pool, tar = args
        try:
            return pool, tar, repack_round_tar(tar), None
        except Exception as e:  # noqa: BLE001
            return pool, tar, 0, e

    if parallel <= 1:
        results_iter = map(_do, work)
        ex = None
    else:
        ex = ThreadPoolExecutor(max_workers=parallel)
        results_iter = ex.map(_do, work)

    try:
        per_pool_saved: dict[Path, int] = {}
        for i, (pool, tar, saved, err) in enumerate(results_iter, start=1):
            if err is not None:
                failed += 1
                print(f"  ERROR repacking {tar}: {err}", file=sys.stderr)
                continue
            if saved == 0:
                skipped += 1
            else:
                saved_total += saved
                per_pool_saved[pool] = per_pool_saved.get(pool, 0) + saved
            if i % 100 == 0:
                print(f"  ... {i}/{len(work)} processed, "
                      f"{saved_total / 1e9:.2f} GB saved so far")
    finally:
        if ex is not None:
            ex.shutdown(wait=True)

    for pool, b in per_pool_saved.items():
        print(f"  {pool.name}: saved {b / 1e9:.2f} GB")
    print(f"  TOTAL saved: {saved_total / 1e9:.2f} GB "
          f"(skipped already-minimal: {skipped}, failed: {failed})")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("pool_dirs", type=Path, nargs="+", help="Pool log dirs to clean")
    p.add_argument("--tier", choices=("1", "2", "both"), required=True,
                   help="Which cleanup tier to run.")
    p.add_argument("--apply", action="store_true",
                   help="Actually delete/repack. Default is dry-run.")
    p.add_argument("--parallel", type=int, default=1,
                   help="Tier 2: number of repack workers. Default 1.")
    args = p.parse_args(argv)

    for pd in args.pool_dirs:
        if not pd.is_dir():
            print(f"ERROR: not a directory: {pd}", file=sys.stderr)
            return 2

    rc = 0
    if args.tier in ("1", "both"):
        rc |= run_tier1(args.pool_dirs, apply=args.apply)
    if args.tier in ("2", "both"):
        rc |= run_tier2(args.pool_dirs, apply=args.apply, parallel=args.parallel)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
