#!/usr/bin/env python3
"""Print target paths for a full-pool config, one per line.

Reads the strategy_pool section of a config YAML and applies the same
target-selection logic as main.py (top_elo_targets → num_targets → all).
Used by scripts/inverse/run_pool.sh to discover targets before launching parallel jobs,
so the bash script never needs to re-implement pool filtering logic.

Usage:
    python -m revenge_bench.scripts.inverse.list_pool_targets <config.yaml>
"""

import argparse
import sys
from pathlib import Path

import yaml

from revenge_bench import CONFIG_DIR
from revenge_bench.strategy_pool import StrategyPool
from revenge_bench.utils.yaml_utils import resolve_includes


def list_targets(config_path: Path) -> list[Path]:
    """Return the selected target paths for a pool config.

    Applies the same priority as run_strategy_pool:
      top_elo_targets → num_targets → all strategies.
    """
    yaml_content = config_path.read_text()
    preprocessed = resolve_includes(yaml_content, base_dir=CONFIG_DIR)
    config = yaml.safe_load(preprocessed)

    pool_config = config.get("strategy_pool")
    if not pool_config:
        raise ValueError(f"No strategy_pool section in {config_path}")

    game_name = config["game"]["name"]
    pool_dir = Path(pool_config["pool_dir"])
    target_filter = pool_config.get("target_filter", {})
    target_names = pool_config.get("target_names")
    top_elo_targets = pool_config.get("top_elo_targets")
    num_targets = pool_config.get("num_targets")
    seed = pool_config.get("seed")

    pool = StrategyPool(pool_dir, game_name, filters=target_filter)

    if not pool.strategies:
        raise RuntimeError(f"No valid strategies found in {pool_dir} for {game_name}")

    if target_names is not None:
        name_set = set(target_names)
        return [s for s in pool.strategies if s.name in name_set]
    elif top_elo_targets is not None:
        return pool.top_by_elo(top_elo_targets)
    elif num_targets is not None:
        return pool.sample(num_targets, seed=seed)
    else:
        return pool.strategies


def main():
    parser = argparse.ArgumentParser(
        description="List target paths for a pool config (one per line)"
    )
    parser.add_argument("config_path", type=Path, help="Path to the pool config YAML")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write paths to this file instead of stdout (avoids import-time banner pollution)",
    )
    args = parser.parse_args()

    try:
        targets = list_targets(args.config_path)
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        args.output.write_text("\n".join(str(t) for t in targets) + "\n")
    else:
        for t in targets:
            print(t)


if __name__ == "__main__":
    main()
