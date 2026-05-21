#!/usr/bin/env python3
"""
Fix broken strategies in existing pools.

For each game: validate the current pool, remove broken strategies,
replace with the next-best spare from the selection report, validate
the replacements, and update the selection report.

Usage:
    python -m revenge_bench.scripts.codeclash_strategies.fix_pools --games HuskyBench CoreWar RobotRumble
    python -m revenge_bench.scripts.codeclash_strategies.fix_pools --games HuskyBench --dry-run
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from revenge_bench.paths import REPO_ROOT as ROOT
from revenge_bench.scripts.codeclash_strategies.select_candidates import (
    _STATIC_VALIDATORS,
    validate_pool,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Map game names to pool dirs
POOL_DIRS = {
    "HuskyBench": ROOT / "data" / "targets" / "huskybench",
    "CoreWar": ROOT / "data" / "targets" / "corewar",
    "RobotRumble": ROOT / "data" / "targets" / "robotrumble",
    "BattleSnake": ROOT / "data" / "targets" / "battlesnake",
    "Halite": ROOT / "data" / "targets" / "halite",
    "RoboCode": ROOT / "data" / "targets" / "robocode",
}


def _dir_name_for_profile(profile: dict) -> str:
    """Compute the directory name that select_candidates uses for a profile."""
    model = profile["model"]
    content_hash = profile["content_hash"]
    return f"{model}__{content_hash}"


def _copy_spare_to_pool(profile: dict, pool_dir: Path, game: str):
    """Copy a spare strategy into the pool directory."""
    src = Path(profile["path"])
    dir_name = _dir_name_for_profile(profile)
    dest = pool_dir / dir_name

    if dest.exists():
        logger.warning(f"    Destination already exists, removing: {dest}")
        shutil.rmtree(dest)

    dest.mkdir(parents=True)

    # Determine game extension
    ext_map = {
        "BattleSnake": ".py",
        "HuskyBench": ".py",
        "Halite": ".c",
        "CoreWar": ".red",
        "RoboCode": ".java",
        "RobotRumble": ".js",
    }
    ext = ext_map.get(game, ".*")

    # Copy main file
    main_file = Path(profile.get("main_file", ""))
    if main_file.exists():
        shutil.copy2(main_file, dest / main_file.name)
    else:
        # Try to find main file in source dir
        for f in src.iterdir():
            if f.suffix == ext and f.is_file():
                shutil.copy2(f, dest / f.name)

    # Copy auxiliary files (same extension)
    for f in src.iterdir():
        if f.is_file() and f.suffix == ext and not (dest / f.name).exists():
            shutil.copy2(f, dest / f.name)

    # Copy provenance if exists
    prov_src = src / "provenance.json"
    if prov_src.exists():
        shutil.copy2(prov_src, dest / "provenance.json")

    logger.info(f"    Copied spare: {dir_name}")
    return dir_name


def fix_game(game: str, dry_run: bool = False) -> dict:
    """Validate and fix one game's pool. Returns summary dict."""
    pool_dir = POOL_DIRS[game]
    report_path = pool_dir / "selection_report.json"

    logger.info(f"\n{'='*60}")
    logger.info(f"Fixing pool: {game}")
    logger.info(f"  Pool dir: {pool_dir}")
    logger.info(f"{'='*60}")

    # Load selection report for spare candidates
    report = json.load(report_path.open())
    all_profiles = report.get("all_profiles", [])

    # Current pool
    pool_dirs = sorted(
        d.name for d in pool_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    logger.info(f"  Current pool size: {len(pool_dirs)}")

    # Find spares (deduped, not selected)
    spares = [
        p
        for p in all_profiles
        if p.get("cluster_id", -1) >= 0 and not p.get("selected")
    ]
    spares.sort(key=lambda p: -p.get("complexity_score", 0))
    logger.info(f"  Available spares: {len(spares)}")

    # Phase 1: Validate
    logger.info("\n  Validating pool...")
    broken = validate_pool(pool_dir, game, sims=1, remove_broken=not dry_run)

    if not broken:
        logger.info("  Pool is clean — no broken strategies")
        return {"game": game, "broken": [], "replaced": [], "status": "clean"}

    if dry_run:
        logger.info(f"\n  DRY RUN — would remove {len(broken)} and replace")
        return {"game": game, "broken": broken, "replaced": [], "status": "dry_run"}

    # Phase 2: Replace broken with spares
    replaced = []
    broken_names = {b["name"] for b in broken}
    spare_idx = 0

    # Pre-validate spares with static check before copying
    static_checker = _STATIC_VALIDATORS.get(game)

    for b in broken:
        logger.info(f"\n  Replacing {b['name']}...")

        found_replacement = False
        while spare_idx < len(spares):
            candidate = spares[spare_idx]
            spare_idx += 1
            cand_name = _dir_name_for_profile(candidate)

            # Skip if already in pool
            if cand_name in pool_dirs or cand_name in broken_names:
                continue

            # Static pre-check for the spare
            if static_checker:
                src_path = Path(candidate["path"])
                reason = static_checker(src_path)
                if reason:
                    logger.info(f"    Skipping spare {cand_name}: {reason}")
                    continue

            # Copy and add to pool
            _copy_spare_to_pool(candidate, pool_dir, game)
            replaced.append(
                {
                    "broken": b["name"],
                    "replacement": cand_name,
                    "model": candidate["model"],
                    "complexity": candidate.get("complexity_score", 0),
                }
            )
            pool_dirs.append(cand_name)
            found_replacement = True
            break

        if not found_replacement:
            logger.warning(f"    No valid spare found for {b['name']}!")

    # Phase 3: Re-validate replacements
    if replaced:
        logger.info("\n  Re-validating pool after replacements...")
        broken2 = validate_pool(pool_dir, game, sims=1, remove_broken=True)
        if broken2:
            logger.warning(f"  {len(broken2)} replacement(s) also broken!")
            # Could recurse, but let's stop here and report
            for b2 in broken2:
                replaced.append(
                    {
                        "broken": b2["name"],
                        "replacement": None,
                        "reason": b2["reason"],
                    }
                )

    final_size = sum(
        1 for d in pool_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    logger.info(f"\n  Final pool size: {final_size}")

    # Update selection report
    report["validation_fixes"] = {
        "broken_removed": [b["name"] for b in broken],
        "replacements": replaced,
        "final_pool_size": final_size,
    }
    report_path.write_text(json.dumps(report, indent=2))
    logger.info(f"  Updated selection report: {report_path}")

    return {
        "game": game,
        "broken": broken,
        "replaced": replaced,
        "final_size": final_size,
        "status": "fixed",
    }


def main():
    parser = argparse.ArgumentParser(description="Fix broken strategies in pools")
    parser.add_argument(
        "--games",
        nargs="+",
        default=["HuskyBench", "CoreWar", "RobotRumble"],
        help="Games to fix (default: HuskyBench CoreWar RobotRumble)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only detect broken strategies, don't replace",
    )
    args = parser.parse_args()

    results = []
    for game in args.games:
        if game not in POOL_DIRS:
            logger.error(f"Unknown game: {game}")
            continue
        result = fix_game(game, dry_run=args.dry_run)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        broken_count = len(r.get("broken", []))
        replaced_count = len([x for x in r.get("replaced", []) if x.get("replacement")])
        print(
            f"  {r['game']:15s}  broken={broken_count}  replaced={replaced_count}  status={r['status']}"
        )


if __name__ == "__main__":
    main()
