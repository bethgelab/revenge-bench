#!/usr/bin/env python3
"""Select a deterministic subset of targets by Elo.

Two selection modes:
  * ``--per-tier N`` (default): group by ``elo_tier`` (easy/medium/hard),
    sort each tier alphabetically, take the first N from each.
  * ``--top-n N``: pick the N strategies with the lowest ``elo_rank``
    (strongest by Elo), ignoring tier stratification.

Selected strategies are symlinked (not copied) into a parallel directory
tree so the full pool remains available for opponents.

Usage:
    # Stratified: 5 per tier for all games (default):
    python -m revenge_bench.scripts.select_targets

    # Stratified: 3 per tier, custom output:
    python -m revenge_bench.scripts.select_targets --per-tier 3

    # Top-N by Elo: pick the 15 highest-Elo huskybench strategies:
    python -m revenge_bench.scripts.select_targets --games huskybench --top-n 15

    # Specific games only:
    python -m revenge_bench.scripts.select_targets --games battlesnake halite

    # Dry run (just print selections):
    python -m revenge_bench.scripts.select_targets --dry-run
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

GAMES = ["battlesnake", "halite", "robotrumble", "huskybench"]
SOURCE_ROOT = Path("data/targets")
DEST_ROOT = Path("data/targets_selected")


def read_provenance(strategy_dir: Path) -> dict:
    prov_file = strategy_dir / "provenance.json"
    if not prov_file.exists():
        return {}
    with open(prov_file) as f:
        return json.load(f)


def select_targets(
    game: str, per_tier: int, source_root: Path
) -> dict[str, list[Path]]:
    """Return {tier: [sorted strategy paths]} with at most per_tier per tier."""
    pool_dir = source_root / game
    if not pool_dir.is_dir():
        print(f"  WARNING: {pool_dir} does not exist, skipping", file=sys.stderr)
        return {}

    # Group by elo_tier
    by_tier: dict[str, list[Path]] = defaultdict(list)
    for entry in sorted(pool_dir.iterdir()):
        if not entry.is_dir():
            continue
        prov = read_provenance(entry)
        tier = prov.get("elo_tier", "unknown")
        by_tier[tier].append(entry)

    # Sort each tier alphabetically and take first per_tier
    selected: dict[str, list[Path]] = {}
    for tier in sorted(by_tier.keys()):
        strategies = sorted(by_tier[tier], key=lambda p: p.name)
        selected[tier] = strategies[:per_tier]

    return selected


def select_top_n(
    game: str, top_n: int, source_root: Path
) -> dict[str, list[Path]]:
    """Return {"top": [paths sorted by elo_rank asc]} with at most top_n entries.

    Strategies without an ``elo_rank`` in provenance are skipped (they were
    never rated by the tournament).
    """
    pool_dir = source_root / game
    if not pool_dir.is_dir():
        print(f"  WARNING: {pool_dir} does not exist, skipping", file=sys.stderr)
        return {}

    ranked: list[tuple[int, Path]] = []
    for entry in sorted(pool_dir.iterdir()):
        if not entry.is_dir():
            continue
        prov = read_provenance(entry)
        rank = prov.get("elo_rank")
        if rank is None:
            continue
        ranked.append((rank, entry))

    ranked.sort(key=lambda r: (r[0], r[1].name))
    return {"top": [p for _, p in ranked[:top_n]]}


def main():
    parser = argparse.ArgumentParser(
        description="Select deterministic target subsets by Elo tier or top-N Elo rank"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--per-tier",
        type=int,
        default=None,
        help="Number of targets per complexity tier (default mode; 5 if neither flag given)",
    )
    mode.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Select the N strongest strategies by elo_rank, ignoring tiers",
    )
    parser.add_argument(
        "--games", nargs="+", default=GAMES, help="Games to process (default: all)"
    )
    parser.add_argument(
        "--source", type=Path, default=SOURCE_ROOT, help="Source pool root"
    )
    parser.add_argument(
        "--dest", type=Path, default=DEST_ROOT, help="Destination root for symlinks"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selections without creating symlinks",
    )
    args = parser.parse_args()

    # Resolve selection mode: --top-n takes precedence if given; otherwise
    # per-tier with default 5.
    use_top_n = args.top_n is not None
    per_tier = args.per_tier if args.per_tier is not None else 5

    for game in args.games:
        print(f"\n=== {game} ===")
        if use_top_n:
            selected = select_top_n(game, args.top_n, args.source)
        else:
            selected = select_targets(game, per_tier, args.source)
        if not selected:
            continue

        dest_dir = args.dest / game
        total = 0

        # Clean out old symlinks before creating new ones
        if not args.dry_run and dest_dir.exists():
            for old in dest_dir.iterdir():
                if old.is_symlink():
                    old.unlink()

        for tier, strategies in selected.items():
            print(f"  {tier}: {len(strategies)} targets")
            for s in strategies:
                print(f"    {s.name}")
                total += 1

                if not args.dry_run:
                    link = dest_dir / s.name
                    link.parent.mkdir(parents=True, exist_ok=True)
                    # Use relative symlink so the repo stays portable
                    target = os.path.relpath(s, link.parent)
                    if link.is_symlink() or link.exists():
                        link.unlink()
                    link.symlink_to(target)

        print(f"  TOTAL: {total} targets selected")
        if not args.dry_run:
            print(f"  → {dest_dir}")


if __name__ == "__main__":
    main()
