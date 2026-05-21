"""Strategy pool for discovering and sampling target strategies.

Supports optional provenance-based filtering.  If a strategy directory
contains a ``provenance.json`` file, its fields can be matched against
filter criteria (e.g. ``elo_tier``, ``model``, ``complexity_tier``).
Strategies without ``provenance.json`` or without the requested field
are silently skipped when a filter is active, but included when no
filter is set.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Duplicated from revenge_bench.agents.static_agent to avoid circular imports.
_GAME_STRATEGY_EXT: dict[str, str] = {
    "BattleSnake": ".py",
    "CoreWar": ".red",
    "Halite": ".c",
    "HuskyBench": ".py",
    "RoboCode": ".java",
    "RobotRumble": ".js",
}


def _read_provenance(strategy_dir: Path) -> dict[str, Any]:
    """Read provenance.json from a strategy directory, returning {} on failure."""
    prov_file = strategy_dir / "provenance.json"
    if not prov_file.exists():
        return {}
    try:
        return json.loads(prov_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _matches_filters(
    provenance: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    """Check whether *provenance* satisfies all *filters*.

    Each filter key corresponds to a provenance field name.  The filter
    value can be:

    * A single scalar (str / int / float) — exact match.
    * A list — provenance value must be **in** the list.

    If a filter key is absent from provenance the strategy is **excluded**
    (the user explicitly asked for something and this strategy can't
    provide it).

    When *filters* is empty every strategy matches (backward-compatible).
    """
    if not filters:
        return True

    for key, expected in filters.items():
        actual = provenance.get(key)
        if actual is None:
            return False  # field missing → can't satisfy filter

        if isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False

    return True


class StrategyPool:
    """Discovers and samples target strategies from a directory.

    Recursively scans a directory tree for valid strategy subdirectories
    (those containing files matching the game's expected extension).

    Optional *filters* restrict which strategies are included based on
    fields in their ``provenance.json``.  When no filters are given
    (the default), all valid strategies are included — so existing
    configs continue to work unchanged.

    Usage::

        # No filters — all strategies
        pool = StrategyPool(Path("data/targets/battlesnake"), "BattleSnake")

        # Filter by Elo tier
        pool = StrategyPool(..., filters={"elo_tier": "hard"})

        # Filter by model (list = OR)
        pool = StrategyPool(..., filters={"model": ["gpt5", "o3"]})

        # Combine filters (AND)
        pool = StrategyPool(..., filters={"elo_tier": "hard", "model": "gpt5"})

        pool.strategies        # filtered strategies, sorted alphabetically
        pool.sample(3, seed=42)
    """

    def __init__(
        self,
        pool_dir: Path,
        game_name: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> None:
        self.pool_dir = Path(pool_dir)
        self.game_name = game_name
        self.filters: dict[str, Any] = filters or {}
        self._strategies: list[Path] = []
        self._discover()

    def _discover(self) -> None:
        """Recursively scan pool_dir for valid strategy subdirectories.

        Walks the directory tree and collects every directory that directly
        contains files matching the game's expected extension.  This handles
        both flat layouts (``pool_dir/strategy/main.py``) and nested ones
        produced by the CodeClash extractor
        (``pool_dir/match/final/player/main.py``).

        When filters are active, strategies whose provenance does not
        satisfy the criteria are excluded.
        """
        if not self.pool_dir.is_dir():
            logger.warning(f"Strategy pool directory does not exist: {self.pool_dir}")
            return

        total_valid = 0
        for dirpath, dirnames, _filenames in os.walk(self.pool_dir, followlinks=True):
            # Skip hidden directories
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))

            path = Path(dirpath)
            if path == self.pool_dir:
                continue
            if not self._is_valid_strategy(path):
                continue

            total_valid += 1

            # Apply provenance filters (if any)
            if self.filters:
                prov = _read_provenance(path)
                if not _matches_filters(prov, self.filters):
                    continue

            self._strategies.append(path)

        self._strategies.sort(key=lambda p: p.name)

        if self.filters:
            logger.info(
                f"Discovered {len(self._strategies)}/{total_valid} strategies "
                f"for {self.game_name} in {self.pool_dir} "
                f"(filters: {self.filters})"
            )
        else:
            logger.info(
                f"Discovered {len(self._strategies)} strategies "
                f"for {self.game_name} in {self.pool_dir}"
            )

    def _is_valid_strategy(self, path: Path) -> bool:
        """Check if a directory contains files matching the game's expected extension."""
        ext = _GAME_STRATEGY_EXT.get(self.game_name)
        if not ext:
            logger.warning(
                f"No known extension for game {self.game_name}, accepting all directories"
            )
            return True
        return any(f.suffix == ext for f in path.iterdir() if f.is_file())

    @property
    def strategies(self) -> list[Path]:
        """All discovered strategies, sorted alphabetically by name."""
        return list(self._strategies)

    def sample(self, n: int, *, seed: int | None = None) -> list[Path]:
        """Return a random sample of strategies.

        Returns min(n, len(strategies)) items. Uses a local Random
        instance for reproducibility when seed is provided.
        """
        count = min(n, len(self._strategies))
        if count <= 0:
            return []
        rng = random.Random(seed)
        return sorted(rng.sample(self._strategies, count), key=lambda p: p.name)

    def top_by_elo(self, n: int) -> list[Path]:
        """Return the top-N strategies by ELO rank.

        Selects strategies whose provenance.json contains ``elo_rank <= n``.
        Strategies missing ``elo_rank`` are excluded.
        Returns the selected strategies sorted alphabetically by name.
        """
        selected = [
            p for p in self._strategies
            if _read_provenance(p).get("elo_rank", float("inf")) <= n
        ]
        logger.info(
            f"top_by_elo: {len(selected)} strategies with elo_rank <= {n} "
            f"from {len(self._strategies)} available"
        )
        return sorted(selected, key=lambda p: p.name)
