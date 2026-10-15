from __future__ import annotations

import hashlib
import random
from pathlib import Path

import yaml

from revenge_bench.harbor.robotrumble_task import resolve_task_instance
from revenge_bench.paths import CONFIG_DIR
from revenge_bench.strategy_pool import StrategyPool
from revenge_bench.utils.yaml_utils import resolve_includes


REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = REPO_ROOT / "harbor" / "tasks" / "robotrumble-gpt5-9aa3-v0"


def _normal_path_selection(config_path: Path, target_index: int):
    config = yaml.safe_load(resolve_includes(config_path.read_text(), base_dir=CONFIG_DIR))
    pool_config = config["strategy_pool"]
    game_name = config["game"]["name"]
    target_pool = StrategyPool(
        Path(pool_config["pool_dir"]),
        game_name,
        filters=pool_config.get("target_filter", {}),
    )
    opponent_pool = StrategyPool(
        Path(pool_config.get("opponent_pool_dir", pool_config["pool_dir"])),
        game_name,
        filters=pool_config.get("opponent_filter", {}),
    )

    targets = target_pool.top_by_elo(pool_config["top_elo_targets"])
    target = targets[target_index]
    available = [s for s in opponent_pool.strategies if s.resolve() != target.resolve()]
    seed = pool_config.get("seed")
    rng_seed = seed + target_index if seed is not None else None
    count = min(config["tournament"]["opponents_per_round"], len(available))
    opponents = random.Random(rng_seed).sample(available, count)
    return target, opponents, config


def test_robotrumble_harbor_instance_matches_normal_benchmark_pool_selection():
    instance = resolve_task_instance(TASK_DIR)
    target, opponents, config = _normal_path_selection(
        REPO_ROOT / instance.benchmark_config,
        instance.target_index,
    )

    assert instance.target_path == target.as_posix()
    assert instance.target_name == target.name
    assert instance.opponents == [p.as_posix() for p in opponents]
    assert instance.opponents_per_round == config["tournament"]["opponents_per_round"]
    assert instance.sims_per_round == config["game"]["sims_per_round"]
    assert instance.raw is True


def test_robotrumble_harbor_starter_matches_normal_arena_starter_hash():
    """Harbor must not replace the native RobotRumble starter with a custom stub."""
    starter = TASK_DIR / "environment" / "starter_robot.js"
    digest = hashlib.sha256(starter.read_bytes()).hexdigest()
    assert digest == "05abc6a4b14cfef98b2a84fb4fea1ff85bc19d0626205ded45b6adbf17c85ae5"
