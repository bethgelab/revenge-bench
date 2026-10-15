from __future__ import annotations

import json
from pathlib import Path

from revenge_bench.harbor.battlesnake_task import resolve_task_instance
from revenge_bench.harbor.inventory import build_inventory, canonical_task_name


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "harbor" / "tasks" / "manifest.json"
PILOT_BATTLESNAKE = REPO_ROOT / "harbor" / "tasks" / "battlesnake-gpt5-9aa3-v0"


def test_manifest_contains_all_top15_gpt5_game_instances():
    inventory = json.loads(MANIFEST.read_text())

    assert inventory["schema_version"] == 1
    assert inventory["target_count_per_game"] == 15
    assert set(inventory["games"]) == {
        "battlesnake",
        "halite",
        "huskybench",
        "robocode",
        "robotrumble",
    }
    assert len(inventory["tasks"]) == 75
    assert len({entry["task_name"] for entry in inventory["tasks"]}) == 75

    for entry in inventory["tasks"]:
        resolved = entry["resolved"]
        assert entry["task_name"] == canonical_task_name(
            entry["game"],
            resolved["benchmark_config"],
            resolved["target_index"],
            resolved["target_name"],
        )
        assert entry["normal_path_key"] == {
            "benchmark_config": resolved["benchmark_config"],
            "target_index": resolved["target_index"],
        }
        assert len(entry["opponents"]) == resolved["opponents_per_round"] == 20
        assert entry["target"]["path"] == resolved["target_path"]


def test_manifest_is_fresh():
    committed = json.loads(MANIFEST.read_text())
    regenerated = build_inventory()
    assert committed == regenerated


def test_current_battlesnake_pilot_maps_to_canonical_manifest_entry():
    instance = resolve_task_instance(PILOT_BATTLESNAKE)
    canonical = canonical_task_name(
        "battlesnake",
        instance.benchmark_config,
        instance.target_index,
        instance.target_name,
    )
    inventory = json.loads(MANIFEST.read_text())
    manifest_entry = next(
        entry for entry in inventory["tasks"] if entry["task_name"] == canonical
    )

    assert PILOT_BATTLESNAKE.name != canonical
    assert manifest_entry["normal_path_key"] == {
        "benchmark_config": instance.benchmark_config,
        "target_index": instance.target_index,
    }
    assert manifest_entry["resolved"]["target_name"] == instance.target_name
    assert manifest_entry["resolved"]["opponents"] == instance.opponents
