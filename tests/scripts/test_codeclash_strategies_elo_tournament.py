"""Tests for the CodeClash strategy Elo update logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from revenge_bench.scripts.codeclash_strategies import elo_tournament

expected_score = elo_tournament.expected_score
update_elo = elo_tournament.update_elo
K_FACTOR = elo_tournament.K_FACTOR


class TestExpectedScore:
    def test_equal_ratings_give_half(self):
        assert expected_score(1500.0, 1500.0) == pytest.approx(0.5)

    def test_higher_rating_favored(self):
        assert expected_score(1600.0, 1400.0) == pytest.approx(0.7597, abs=1e-3)

    def test_complementary(self):
        # e_a + e_b == 1 exactly
        a, b = 1234.0, 1789.0
        assert expected_score(a, b) + expected_score(b, a) == pytest.approx(1.0)


class TestUpdateEloSignature:
    """update_elo must take s_a directly (not raw scores + sims)."""

    def test_equal_ratings_win_moves_by_half_k(self):
        new_a, new_b = update_elo(1500.0, 1500.0, 1.0)
        assert new_a == pytest.approx(1500.0 + K_FACTOR * 0.5)
        assert new_b == pytest.approx(1500.0 - K_FACTOR * 0.5)

    def test_equal_ratings_loss_symmetric(self):
        new_a, new_b = update_elo(1500.0, 1500.0, 0.0)
        assert new_a == pytest.approx(1500.0 - K_FACTOR * 0.5)
        assert new_b == pytest.approx(1500.0 + K_FACTOR * 0.5)

    def test_draw_is_zero_delta(self):
        new_a, new_b = update_elo(1500.0, 1500.0, 0.5)
        assert new_a == pytest.approx(1500.0)
        assert new_b == pytest.approx(1500.0)

    def test_zero_sum(self):
        # Total Elo is conserved: delta_a + delta_b == 0 for any s_a.
        for s_a in (0.0, 0.25, 0.5, 0.75, 1.0):
            new_a, new_b = update_elo(1600.0, 1400.0, s_a)
            assert (new_a - 1600.0) + (new_b - 1400.0) == pytest.approx(0.0)

    def test_upset_larger_delta(self):
        # Weaker beats stronger → bigger Elo move than expected result.
        new_weak, new_strong = update_elo(1400.0, 1600.0, 1.0)
        assert new_weak - 1400.0 > K_FACTOR * 0.5  # more than equal-rating win
        assert new_strong - 1600.0 < -K_FACTOR * 0.5

    def test_custom_k(self):
        new_a, _ = update_elo(1500.0, 1500.0, 1.0, k=16.0)
        assert new_a == pytest.approx(1508.0)

    def test_does_not_accept_legacy_score_kwargs(self):
        # Regression guard: the old (score_a, score_b, sims) signature
        # must not silently accept 4 positional floats.
        with pytest.raises(TypeError):
            update_elo(1500.0, 1500.0, 10075, 9925, 10)  # type: ignore[misc]

class TestSwissMatchLoopUsesWinner:
    """Integration check: the match loop passes s_a ∈ {0, 0.5, 1} to update_elo,
    never raw scores."""

    def _run_one_round(self, tmp_path, winner_name: str | None, scores: dict):
        # Build two dummy strategy dirs so discover_strategies() picks them up.
        pool = tmp_path / "pool"
        for name in ("alpha", "bravo"):
            (pool / name).mkdir(parents=True)
            (pool / name / "main.py").write_text("# stub\n")

        fake_result = {"winner": winner_name, "scores": scores, "resumed": True}

        observed_calls: list[tuple[float, float, float]] = []

        def fake_update(a, b, s_a, k=K_FACTOR):
            observed_calls.append((a, b, s_a))
            return a, b

        with (
            patch.object(elo_tournament, "run_match", return_value=fake_result),
            patch.object(elo_tournament, "update_elo", side_effect=fake_update),
        ):
            elo_tournament.run_swiss_tournament(
                pool_dir=pool,
                game_name="HuskyBench",
                num_rounds=1,
                sims_per_match=100,
                output_dir=tmp_path / "out",
            )
        return observed_calls

    def test_bankroll_scores_produce_decisive_s_a(self, tmp_path):
        # Real HuskyBench-shape result: winner is clear, scores are chip totals.
        calls = self._run_one_round(
            tmp_path,
            winner_name="alpha",
            scores={"alpha": 10075, "bravo": 9925},
        )
        assert len(calls) == 1
        _, _, s_a = calls[0]
        assert s_a in (0.0, 1.0), f"expected decisive 0/1 for winner, got s_a={s_a}"

    def test_no_winner_is_draw(self, tmp_path):
        calls = self._run_one_round(
            tmp_path,
            winner_name=None,
            scores={"alpha": 10000, "bravo": 10000},
        )
        assert len(calls) == 1
        assert calls[0][2] == 0.5
