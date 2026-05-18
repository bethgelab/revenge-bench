"""Tests for scripts/inverse/list_pool_targets.py."""

import json
from pathlib import Path

import pytest

from revenge_bench.scripts.inverse.list_pool_targets import list_targets


def _make_strategy(pool_dir: Path, name: str, elo_rank: int | None = None) -> Path:
    d = pool_dir / name
    d.mkdir(parents=True)
    (d / "main.py").write_text(f"# {name}")
    prov: dict = {}
    if elo_rank is not None:
        prov["elo_rank"] = elo_rank
    (d / "provenance.json").write_text(json.dumps(prov))
    return d


def _write_config(
    path: Path, pool_dir: Path, game: str = "BattleSnake", **pool_kwargs
) -> Path:
    """Write a minimal pool config YAML (no !include directives)."""
    extra_lines = "".join(f"\n  {k}: {v}" for k, v in pool_kwargs.items())
    config = f"""\
strategy_pool:
  pool_dir: {pool_dir}{extra_lines}

tournament:
  rounds: 3
  type: interventionist

game:
  name: {game}
  sims_per_round: 5

players:
  - agent: inverse
    name: learner
  - agent: static
    name: target
    args:
      source_path: {pool_dir}
  - agent: static
    name: opponent
    args:
      source_path: {pool_dir}
"""
    path.write_text(config)
    return path


class TestListTargets:
    def test_all_targets_returned_when_no_limit(self, tmp_path):
        pool_dir = tmp_path / "pool"
        for i, name in enumerate(["a", "b", "c"], start=1):
            _make_strategy(pool_dir, name, elo_rank=i)
        config = _write_config(tmp_path / "cfg.yaml", pool_dir)

        targets = list_targets(config)
        assert len(targets) == 3

    def test_top_elo_targets_selects_by_rank(self, tmp_path):
        pool_dir = tmp_path / "pool"
        for i in range(1, 7):
            _make_strategy(pool_dir, f"strat_{i:02d}", elo_rank=i)
        config = _write_config(tmp_path / "cfg.yaml", pool_dir, top_elo_targets=3)

        targets = list_targets(config)
        assert len(targets) == 3
        assert {t.name for t in targets} == {"strat_01", "strat_02", "strat_03"}

    def test_top_elo_targets_excludes_missing_elo_rank(self, tmp_path):
        pool_dir = tmp_path / "pool"
        _make_strategy(pool_dir, "ranked", elo_rank=1)
        _make_strategy(pool_dir, "no_rank")  # no elo_rank in provenance
        config = _write_config(tmp_path / "cfg.yaml", pool_dir, top_elo_targets=5)

        targets = list_targets(config)
        assert len(targets) == 1
        assert targets[0].name == "ranked"

    def test_top_elo_targets_takes_precedence_over_num_targets(self, tmp_path):
        pool_dir = tmp_path / "pool"
        for i in range(1, 5):
            _make_strategy(pool_dir, f"s{i}", elo_rank=i)
        # top_elo_targets=2 → 2 total; num_targets=4 should be ignored
        config = _write_config(
            tmp_path / "cfg.yaml", pool_dir, top_elo_targets=2, num_targets=4
        )

        assert len(list_targets(config)) == 2

    def test_num_targets_limit(self, tmp_path):
        pool_dir = tmp_path / "pool"
        for i, name in enumerate(["a", "b", "c", "d"], start=1):
            _make_strategy(pool_dir, name, elo_rank=i)
        config = _write_config(tmp_path / "cfg.yaml", pool_dir, num_targets=2, seed=42)

        assert len(list_targets(config)) == 2

    def test_returns_valid_paths(self, tmp_path):
        pool_dir = tmp_path / "pool"
        _make_strategy(pool_dir, "alpha", elo_rank=1)
        _make_strategy(pool_dir, "beta", elo_rank=2)
        config = _write_config(tmp_path / "cfg.yaml", pool_dir)

        for t in list_targets(config):
            assert t.is_dir()

    def test_no_strategy_pool_section_raises(self, tmp_path):
        config_path = tmp_path / "cfg.yaml"
        config_path.write_text(
            """\
tournament:
  rounds: 3
game:
  name: BattleSnake
  sims_per_round: 5
players: []
"""
        )
        with pytest.raises(ValueError, match="No strategy_pool section"):
            list_targets(config_path)

    def test_empty_pool_raises(self, tmp_path):
        pool_dir = tmp_path / "pool"
        pool_dir.mkdir()
        config = _write_config(tmp_path / "cfg.yaml", pool_dir)

        with pytest.raises(RuntimeError, match="No valid strategies"):
            list_targets(config)
