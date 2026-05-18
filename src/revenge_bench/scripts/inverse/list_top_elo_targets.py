#!/usr/bin/env python3
"""Print the top-N strategies by ELO rank for a given arena game.

Usage:
    python -m revenge_bench.scripts.inverse.top_elo <game> <n>

Examples:
    python -m revenge_bench.scripts.inverse.top_elo battlesnake 10
    python -m revenge_bench.scripts.inverse.top_elo halite 5
"""

import argparse
import sys

from revenge_bench import REPO_DIR
from revenge_bench.strategy_pool import _GAME_STRATEGY_EXT, StrategyPool

# Map lowercase CLI names → canonical game names used by StrategyPool
_GAME_ALIASES: dict[str, str] = {g.lower(): g for g in _GAME_STRATEGY_EXT}


def main() -> None:
    parser = argparse.ArgumentParser(description="Print top-N strategy paths by ELO rank for a given game")
    parser.add_argument(
        "game",
        help=f"Game name (case-insensitive). Known games: {', '.join(sorted(_GAME_ALIASES))}",
    )
    parser.add_argument("n", type=int, help="Number of top strategies to print")
    args = parser.parse_args()

    game_key = args.game.lower()
    if game_key not in _GAME_ALIASES:
        print(
            f"ERROR: unknown game '{args.game}'. Known games: {', '.join(sorted(_GAME_ALIASES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    game_name = _GAME_ALIASES[game_key]
    pool_dir = REPO_DIR / "data" / "inverse" / "targets" / game_key

    pool = StrategyPool(pool_dir, game_name)
    if not pool.strategies:
        print(f"ERROR: no strategies found in {pool_dir}", file=sys.stderr)
        sys.exit(1)

    top = pool.top_by_elo(args.n)
    if not top:
        print(
            f"No strategies with elo_rank <= {args.n} found in {pool_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    for path in top:
        print(path)


if __name__ == "__main__":
    main()
