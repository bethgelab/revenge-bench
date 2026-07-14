#!/usr/bin/env python3
"""Prepare root-only HuskyBench target/opponent client directories."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from huskybench_common import copy_strategy_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-source", type=Path, required=True)
    parser.add_argument("--target-dest", type=Path, required=True)
    parser.add_argument("--opponents-source", type=Path, required=True)
    parser.add_argument("--opponents-dest", type=Path, required=True)
    args = parser.parse_args()

    if args.target_dest.exists():
        shutil.rmtree(args.target_dest)
    args.target_dest.mkdir(parents=True)
    copy_strategy_source(args.target_source, args.target_dest)

    if args.opponents_dest.exists():
        shutil.rmtree(args.opponents_dest)
    args.opponents_dest.mkdir(parents=True)
    for opponent_source in sorted(p for p in args.opponents_source.iterdir() if p.is_dir()):
        dest = args.opponents_dest / opponent_source.name
        dest.mkdir(parents=True)
        copy_strategy_source(opponent_source, dest)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
