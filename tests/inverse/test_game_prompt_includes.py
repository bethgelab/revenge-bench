"""
Tests for game prompt include resolution.

Verifies that <<: !include inverse/prompts/game/{game}.yaml in pool configs
resolves to a non-empty game_description string.
"""

from pathlib import Path

import pytest
import yaml

POOL_CONFIGS = [
    ("configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_battlesnake.yaml", "BattleSnake"),
    ("configs/inverse/pool/gpt5/gpt5_battlesnake.yaml", "BattleSnake"),
    ("configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_halite.yaml", "Halite"),
    ("configs/inverse/pool/gpt54_mini/gpt54_mini_halite.yaml", "Halite"),
    ("configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_huskybench.yaml", "HuskyBench"),
    ("configs/inverse/pool/gpt54_mini/gpt54_mini_huskybench.yaml", "HuskyBench"),
    ("configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_robocode.yaml", "RoboCode"),
    ("configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_robotrumble.yaml", "RobotRumble"),
    ("configs/inverse/pool/gpt54_mini/gpt54_mini_robotrumble.yaml", "RobotRumble"),
]

PUBLIC_VARIANT_CONFIGS = [
    (str(p), "BattleSnake")
    for root in ("configs/inverse/conditions", "configs/inverse/baselines")
    for p in sorted(Path(root).rglob("*.yaml"))
]

ALL_CONFIGS = POOL_CONFIGS + PUBLIC_VARIANT_CONFIGS


def _resolve(config_path: str) -> dict:
    from revenge_bench import CONFIG_DIR
    from revenge_bench.utils.yaml_utils import resolve_includes

    content = Path(config_path).read_text()
    resolved = resolve_includes(content, base_dir=CONFIG_DIR)
    return yaml.safe_load(resolved)


@pytest.mark.parametrize(("config_path", "game_name"), ALL_CONFIGS)
def test_game_description_present(config_path, game_name):
    if not Path(config_path).exists():
        pytest.skip(f"{config_path} does not exist")
    cfg = _resolve(config_path)
    desc = cfg.get("prompts", {}).get("game_description", "")
    assert desc, f"game_description missing in {config_path}"
    assert len(desc) > 200, f"game_description too short in {config_path}"
    assert "{{player_id}}" in desc, f"missing player_id placeholder in {config_path}"


@pytest.mark.parametrize(("config_path", "game_name"), POOL_CONFIGS)
def test_game_description_mentions_game(config_path, game_name):
    cfg = _resolve(config_path)
    desc = cfg.get("prompts", {}).get("game_description", "")
    assert game_name in desc, f"game name {game_name!r} not found in game_description of {config_path}"


def test_same_game_configs_share_description():
    """Same-game pool configs must resolve to identical game_description."""
    same_game_pairs = [
        (
            "configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_halite.yaml",
            "configs/inverse/pool/gpt54_mini/gpt54_mini_halite.yaml",
        ),
        (
            "configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_huskybench.yaml",
            "configs/inverse/pool/gpt54_mini/gpt54_mini_huskybench.yaml",
        ),
        (
            "configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_robotrumble.yaml",
            "configs/inverse/pool/gpt54_mini/gpt54_mini_robotrumble.yaml",
        ),
        (
            "configs/inverse/pool/deepseek_v4_pro/deepseek_v4_pro_battlesnake.yaml",
            "configs/inverse/pool/gpt5/gpt5_battlesnake.yaml",
        ),
    ]
    for path_a, path_b in same_game_pairs:
        cfg_a = _resolve(path_a)
        cfg_b = _resolve(path_b)
        desc_a = cfg_a.get("prompts", {}).get("game_description", "")
        desc_b = cfg_b.get("prompts", {}).get("game_description", "")
        assert desc_a == desc_b, f"game_description differs between {path_a} and {path_b}"
