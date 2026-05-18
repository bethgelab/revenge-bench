"""Emit a per-target pool config from a base full-pool YAML.

Replaces the brittle sed-based comment-marker substitution in
``run_pool.sh``. Loads the base YAML (resolving ``!include`` directives
the same way ``main.py`` does), mutates the structure to pin a single
target + seed, and writes the result to the temp config path
``run_pool.sh`` then hands to ``main.py``.

Mutations applied:
- ``tournament.seed`` → the requested seed
- ``strategy_pool.fixed_target`` → ``true``
- the static ``target`` player's ``args.source_path`` → the requested path

Comments and the upstream ``!include`` shape are not preserved (the
output is the resolved/flattened YAML); ``main.py``'s loader handles
both forms identically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from revenge_bench.paths import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))

from revenge_bench import CONFIG_DIR  # noqa: E402
from revenge_bench.utils.yaml_utils import resolve_includes  # noqa: E402


def build_target_config(
    base_config_path: Path,
    *,
    seed: int,
    target_source_path: str,
) -> dict:
    raw = base_config_path.read_text()
    resolved = resolve_includes(raw, base_dir=CONFIG_DIR)
    cfg = yaml.safe_load(resolved)

    cfg.setdefault("tournament", {})["seed"] = seed

    cfg.setdefault("strategy_pool", {})["fixed_target"] = True

    target_set = False
    for player in cfg.get("players", []):
        if player.get("agent") == "static" and player.get("name") == "target":
            player.setdefault("args", {})["source_path"] = target_source_path
            target_set = True
            break
    if not target_set:
        raise SystemExit(
            f"{base_config_path}: no static 'target' player to pin "
            "(expected players[].agent='static' with name='target')"
        )

    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config_file", type=Path, help="Base full-pool YAML.")
    parser.add_argument("output_file", type=Path, help="Per-target config to write.")
    parser.add_argument("--seed", type=int, required=True, help="Tournament seed.")
    parser.add_argument(
        "--target-source-path",
        required=True,
        help="Path that becomes the static target's args.source_path.",
    )
    args = parser.parse_args()

    cfg = build_target_config(
        args.config_file,
        seed=args.seed,
        target_source_path=args.target_source_path,
    )
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(yaml.safe_dump(cfg, sort_keys=False))


if __name__ == "__main__":
    main()
