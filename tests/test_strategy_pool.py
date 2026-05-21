"""Tests for StrategyPool and main.py pool orchestration."""

import json
import random
from pathlib import Path

from revenge_bench.strategy_pool import StrategyPool
from main import (
    _get_player_source_path,
    _override_target_source,
    write_benchmark_summary,
)


class TestStrategyPool:
    """Tests for StrategyPool discovery and sampling."""

    def test_discover_battlesnake_targets(self):
        """Discovers targets from the battlesnake pool."""
        pool = StrategyPool(Path("data/targets"), "BattleSnake")
        names = [p.name for p in pool.strategies]
        # Pool contains model-generated strategies + debug targets
        assert len(names) >= 2

    def test_strategies_sorted_alphabetically(self):
        """Strategies are returned in alphabetical order."""
        pool = StrategyPool(Path("data/targets"), "BattleSnake")
        names = [p.name for p in pool.strategies]
        assert names == sorted(names)

    def test_empty_dir(self, tmp_path):
        """Empty directory yields no strategies."""
        pool = StrategyPool(tmp_path, "BattleSnake")
        assert pool.strategies == []

    def test_nonexistent_dir(self, tmp_path):
        """Nonexistent directory yields no strategies (no exception)."""
        pool = StrategyPool(tmp_path / "does_not_exist", "BattleSnake")
        assert pool.strategies == []

    def test_no_valid_strategies(self, tmp_path):
        """Directories without matching file extensions are skipped."""
        # Create a subdir with a .txt file but no .py file
        strat = tmp_path / "bad_strategy"
        strat.mkdir()
        (strat / "readme.txt").write_text("not a python file")

        pool = StrategyPool(tmp_path, "BattleSnake")
        assert pool.strategies == []

    def test_hidden_dirs_skipped(self, tmp_path):
        """Hidden directories (starting with .) are skipped."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "main.py").write_text("# hidden")

        visible = tmp_path / "visible"
        visible.mkdir()
        (visible / "main.py").write_text("# visible")

        pool = StrategyPool(tmp_path, "BattleSnake")
        names = [p.name for p in pool.strategies]
        assert ".hidden" not in names
        assert "visible" in names

    def test_files_at_top_level_ignored(self, tmp_path):
        """Files (not directories) at the top level are ignored."""
        (tmp_path / "stray_file.py").write_text("# not a strategy")
        strat = tmp_path / "real_strategy"
        strat.mkdir()
        (strat / "main.py").write_text("def move(state): return 'up'")

        pool = StrategyPool(tmp_path, "BattleSnake")
        assert len(pool.strategies) == 1
        assert pool.strategies[0].name == "real_strategy"

    def test_sample_basic(self, tmp_path):
        """sample() returns requested number of strategies."""
        for name in ["alpha", "beta", "gamma"]:
            d = tmp_path / name
            d.mkdir()
            (d / "main.py").write_text(f"# {name}")

        pool = StrategyPool(tmp_path, "BattleSnake")
        assert len(pool.strategies) == 3

        sampled = pool.sample(2, seed=42)
        assert len(sampled) == 2
        # All sampled items should be from the pool
        assert all(s in pool.strategies for s in sampled)

    def test_sample_more_than_available(self, tmp_path):
        """sample(n) where n > len returns all strategies."""
        d = tmp_path / "only_one"
        d.mkdir()
        (d / "main.py").write_text("# one")

        pool = StrategyPool(tmp_path, "BattleSnake")
        sampled = pool.sample(10)
        assert len(sampled) == 1

    def test_sample_reproducible(self, tmp_path):
        """Same seed produces same sample."""
        for name in ["a", "b", "c", "d", "e"]:
            d = tmp_path / name
            d.mkdir()
            (d / "main.py").write_text(f"# {name}")

        pool = StrategyPool(tmp_path, "BattleSnake")
        s1 = pool.sample(3, seed=123)
        s2 = pool.sample(3, seed=123)
        assert s1 == s2

    def test_sample_zero(self, tmp_path):
        """sample(0) returns empty list."""
        d = tmp_path / "strat"
        d.mkdir()
        (d / "main.py").write_text("# strat")

        pool = StrategyPool(tmp_path, "BattleSnake")
        assert pool.sample(0) == []

    def test_sample_sorted(self, tmp_path):
        """sample() returns results sorted alphabetically."""
        for name in ["zebra", "apple", "mango"]:
            d = tmp_path / name
            d.mkdir()
            (d / "main.py").write_text(f"# {name}")

        pool = StrategyPool(tmp_path, "BattleSnake")
        sampled = pool.sample(3, seed=1)
        names = [s.name for s in sampled]
        assert names == sorted(names)

    def test_top_by_elo_selects_by_rank(self, tmp_path):
        """top_by_elo(n) returns strategies with elo_rank <= n."""
        for i in range(1, 6):
            d = tmp_path / f"strat_{i:02d}"
            d.mkdir()
            (d / "main.py").write_text(f"# strat_{i:02d}")
            (d / "provenance.json").write_text(json.dumps({"elo_rank": i}))

        pool = StrategyPool(tmp_path, "BattleSnake")
        selected = pool.top_by_elo(3)
        assert len(selected) == 3
        assert {s.name for s in selected} == {"strat_01", "strat_02", "strat_03"}

    def test_top_by_elo_excludes_missing_rank(self, tmp_path):
        """Strategies without elo_rank are excluded from top_by_elo."""
        ranked = tmp_path / "ranked"
        ranked.mkdir()
        (ranked / "main.py").write_text("# ranked")
        (ranked / "provenance.json").write_text(json.dumps({"elo_rank": 1}))

        unranked = tmp_path / "unranked"
        unranked.mkdir()
        (unranked / "main.py").write_text("# unranked")
        (unranked / "provenance.json").write_text(json.dumps({}))

        pool = StrategyPool(tmp_path, "BattleSnake")
        selected = pool.top_by_elo(5)
        assert len(selected) == 1
        assert selected[0].name == "ranked"

    def test_top_by_elo_sorted_alphabetically(self, tmp_path):
        """top_by_elo returns results sorted alphabetically."""
        for name, rank in [("zebra", 1), ("apple", 2), ("mango", 3)]:
            d = tmp_path / name
            d.mkdir()
            (d / "main.py").write_text(f"# {name}")
            (d / "provenance.json").write_text(json.dumps({"elo_rank": rank}))

        pool = StrategyPool(tmp_path, "BattleSnake")
        selected = pool.top_by_elo(3)
        names = [s.name for s in selected]
        assert names == sorted(names)

    def test_other_game_extension(self, tmp_path):
        """Validates against the correct extension for non-BattleSnake games."""
        # CoreWar expects .red files
        d = tmp_path / "warrior"
        d.mkdir()
        (d / "warrior.red").write_text(";redcode")

        py_only = tmp_path / "py_strat"
        py_only.mkdir()
        (py_only / "main.py").write_text("# python only")

        pool = StrategyPool(tmp_path, "CoreWar")
        names = [p.name for p in pool.strategies]
        assert "warrior" in names
        assert "py_strat" not in names


class TestOverrideTargetSource:
    """Tests for _override_target_source config mutation."""

    def test_target_and_opponent_set_independently(self):
        config = {
            "players": [
                {"agent": "inverse", "name": "learner"},
                {
                    "agent": "static",
                    "name": "target",
                    "args": {"source_path": "old/path"},
                },
                {
                    "agent": "static",
                    "name": "opponent",
                    "args": {"source_path": "old/path"},
                },
            ]
        }
        result = _override_target_source(
            config, Path("new/target"), opponent_path=Path("new/opponent")
        )

        # Original unchanged
        assert config["players"][1]["args"]["source_path"] == "old/path"

        # Target and opponent set to different paths
        assert result["players"][1]["args"]["source_path"] == "new/target"
        assert result["players"][2]["args"]["source_path"] == "new/opponent"

    def test_opponent_defaults_to_target_when_not_given(self):
        config = {
            "players": [
                {"agent": "inverse", "name": "learner"},
                {
                    "agent": "static",
                    "name": "target",
                    "args": {"source_path": "old/path"},
                },
                {
                    "agent": "static",
                    "name": "opponent",
                    "args": {"source_path": "old/path"},
                },
            ]
        }
        result = _override_target_source(config, Path("new/target"))

        assert result["players"][1]["args"]["source_path"] == "new/target"
        assert result["players"][2]["args"]["source_path"] == "new/target"

    def test_leaves_inverse_player_alone(self):
        config = {
            "players": [
                {"agent": "inverse", "name": "learner", "config": {"model": "test"}},
                {"agent": "static", "name": "target"},
            ]
        }
        result = _override_target_source(config, Path("new/path"))
        assert "source_path" not in result["players"][0].get("args", {})
        assert result["players"][1]["args"]["source_path"] == "new/path"

    def test_creates_args_if_missing(self):
        config = {
            "players": [
                {"agent": "static", "name": "target"},
            ]
        }
        result = _override_target_source(config, Path("some/path"))
        assert result["players"][0]["args"]["source_path"] == "some/path"


class TestWriteBenchmarkSummary:
    """Tests for write_benchmark_summary."""

    def test_writes_valid_json(self, tmp_path):
        results = [
            {
                "target": "a",
                "final_distance": 0.1,
                "status": "completed",
                "distance_history": {0: 0.5, 1: 0.1},
            },
            {
                "target": "b",
                "final_distance": 0.3,
                "status": "completed",
                "distance_history": {0: 0.7, 1: 0.3},
            },
        ]
        config = {
            "game": {"name": "BattleSnake", "sims_per_round": 10},
            "tournament": {"rounds": 3},
        }

        path = write_benchmark_summary(tmp_path, results, config)
        assert path.exists()

        summary = json.loads(path.read_text())
        assert summary["num_targets"] == 2
        assert summary["num_completed"] == 2
        assert summary["num_failed"] == 0
        assert summary["aggregate"]["mean"] == 0.2
        assert summary["aggregate"]["min"] == 0.1
        assert summary["aggregate"]["max"] == 0.3
        assert len(summary["per_target"]) == 2

    def test_handles_failures(self, tmp_path):
        results = [
            {
                "target": "a",
                "final_distance": 0.1,
                "status": "completed",
                "distance_history": {0: 0.1},
            },
            {
                "target": "b",
                "final_distance": None,
                "status": "failed",
                "error": "boom",
                "distance_history": {},
            },
        ]
        config = {
            "game": {"name": "BattleSnake", "sims_per_round": 5},
            "tournament": {"rounds": 2},
        }

        path = write_benchmark_summary(tmp_path, results, config)
        summary = json.loads(path.read_text())
        assert summary["num_completed"] == 1
        assert summary["num_failed"] == 1
        # Aggregate only from completed
        assert summary["aggregate"]["mean"] == 0.1

    def test_all_failed(self, tmp_path):
        results = [
            {"target": "a", "final_distance": None, "status": "failed", "error": "err"},
        ]
        config = {
            "game": {"name": "BattleSnake", "sims_per_round": 5},
            "tournament": {"rounds": 1},
        }

        path = write_benchmark_summary(tmp_path, results, config)
        summary = json.loads(path.read_text())
        assert summary["aggregate"] == {}
        assert summary["num_completed"] == 0

    def test_config_section(self, tmp_path):
        results = []
        config = {
            "game": {"name": "BattleSnake", "sims_per_round": 10},
            "tournament": {"rounds": 3},
        }

        path = write_benchmark_summary(tmp_path, results, config)
        summary = json.loads(path.read_text())
        assert summary["config"]["game"] == "BattleSnake"
        assert summary["config"]["rounds"] == 3
        assert summary["config"]["sims_per_round"] == 10


class TestOpponentSampling:
    """Tests for opponent sampling in run_strategy_pool."""

    @staticmethod
    def _make_pool(tmp_path, names):
        """Create a pool directory with named strategies."""
        for name in names:
            d = tmp_path / name
            d.mkdir()
            (d / "main.py").write_text(f"# {name}")
        return StrategyPool(tmp_path, "BattleSnake")

    def _sample_opponents(self, pool, target_path, n_pick, seed, idx):
        """Replicate the opponent sampling logic from run_strategy_pool."""
        available = [s for s in pool.strategies if s != target_path]
        if not available:
            raise RuntimeError(
                "Opponent pool contains only the target — add at least one other strategy."
            )
        rng = random.Random(seed + idx if seed is not None else None)
        return rng.sample(available, min(n_pick, len(available)))

    def test_opponent_not_equal_to_target(self, tmp_path):
        pool = self._make_pool(tmp_path, ["alpha", "beta", "gamma", "delta"])
        target = pool.strategies[0]  # alpha
        opponents = self._sample_opponents(pool, target, n_pick=1, seed=42, idx=0)
        assert all(o != target for o in opponents)

    def test_single_opponent_returns_one(self, tmp_path):
        pool = self._make_pool(tmp_path, ["a", "b", "c"])
        target = pool.strategies[0]
        opponents = self._sample_opponents(pool, target, n_pick=1, seed=1, idx=0)
        assert len(opponents) == 1

    def test_multi_opponent_returns_n(self, tmp_path):
        pool = self._make_pool(tmp_path, ["a", "b", "c", "d"])
        target = pool.strategies[0]
        opponents = self._sample_opponents(pool, target, n_pick=3, seed=1, idx=0)
        assert len(opponents) == 3
        assert all(o != target for o in opponents)

    def test_deterministic_with_seed(self, tmp_path):
        pool = self._make_pool(tmp_path, ["a", "b", "c", "d"])
        target = pool.strategies[1]
        o1 = self._sample_opponents(pool, target, n_pick=2, seed=99, idx=0)
        o2 = self._sample_opponents(pool, target, n_pick=2, seed=99, idx=0)
        assert o1 == o2

    def test_different_seeds_differ(self, tmp_path):
        pool = self._make_pool(tmp_path, ["a", "b", "c", "d", "e"])
        target = pool.strategies[0]
        o1 = self._sample_opponents(pool, target, n_pick=1, seed=1, idx=0)
        o2 = self._sample_opponents(pool, target, n_pick=1, seed=2, idx=0)
        assert o1 != o2

    def test_single_strategy_pool_raises(self, tmp_path):
        """When pool has only the target, sampling raises rather than self-playing."""
        import pytest

        pool = self._make_pool(tmp_path, ["only_one"])
        target = pool.strategies[0]
        with pytest.raises(
            RuntimeError, match="Opponent pool contains only the target"
        ):
            self._sample_opponents(pool, target, n_pick=1, seed=42, idx=0)


class TestOverrideTargetSourceFixedTarget:
    """Tests for _override_target_source with fixed_target parameter."""

    def test_fixed_target_leaves_target_unchanged(self):
        config = {
            "players": [
                {"agent": "inverse", "name": "learner"},
                {
                    "agent": "static",
                    "name": "target",
                    "args": {"source_path": "original/target"},
                },
                {
                    "agent": "static",
                    "name": "opponent",
                    "args": {"source_path": "original/opponent"},
                },
            ]
        }
        result = _override_target_source(
            config,
            Path("new/target"),
            opponent_path=Path("new/opponent"),
            fixed_target=True,
        )
        # Target unchanged
        assert result["players"][1]["args"]["source_path"] == "original/target"
        # Opponent updated
        assert result["players"][2]["args"]["source_path"] == "new/opponent"

    def test_fixed_target_no_opponent_path_leaves_both_unchanged(self):
        config = {
            "players": [
                {
                    "agent": "static",
                    "name": "target",
                    "args": {"source_path": "original/target"},
                },
                {
                    "agent": "static",
                    "name": "opponent",
                    "args": {"source_path": "original/opponent"},
                },
            ]
        }
        result = _override_target_source(config, Path("ignored"), fixed_target=True)
        assert result["players"][0]["args"]["source_path"] == "original/target"
        assert result["players"][1]["args"]["source_path"] == "original/opponent"


class TestGetPlayerSourcePath:
    """Tests for _get_player_source_path helper."""

    def test_returns_source_path(self):
        config = {
            "players": [
                {
                    "agent": "static",
                    "name": "target",
                    "args": {"source_path": "my/target"},
                },
            ]
        }
        assert _get_player_source_path(config, "target") == "my/target"

    def test_returns_none_when_not_found(self):
        config = {"players": [{"agent": "inverse", "name": "learner"}]}
        assert _get_player_source_path(config, "target") is None

    def test_returns_none_when_no_args(self):
        config = {"players": [{"agent": "static", "name": "target"}]}
        assert _get_player_source_path(config, "target") is None


class TestFixedTarget:
    """Tests for fixed_target logic."""

    def test_fixed_target_no_source_path_raises(self, tmp_path):
        """fixed_target requires a target source_path in config."""
        import pytest

        from main import run_strategy_pool

        # Create a valid pool directory
        strat = tmp_path / "pool" / "s1"
        strat.mkdir(parents=True)
        (strat / "main.py").write_text("# s1")

        config = {
            "game": {"name": "BattleSnake", "sims_per_round": 5},
            "tournament": {"rounds": 2},
            "players": [
                {"agent": "inverse", "name": "learner"},
                {"agent": "static", "name": "target"},  # no source_path!
                {"agent": "static", "name": "opponent", "args": {"source_path": "o"}},
            ],
        }
        pool_config = {"pool_dir": str(tmp_path / "pool"), "fixed_target": True}

        with pytest.raises(
            ValueError, match="fixed_target is true but no target source_path"
        ):
            run_strategy_pool(
                config,
                pool_config,
                cleanup=False,
                timestamp="20260101_000000",
                keep_containers=False,
            )
