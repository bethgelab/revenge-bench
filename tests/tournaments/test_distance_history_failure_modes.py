"""Regression: sim failures must be recorded in metadata, not silently defaulted."""

import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _build_minimal_tournament_stub(tmp_path: Path):
    """Bypass __init__ and set just enough state for _run_multi_opponent_sim.

    Pattern after tests/tournaments/test_persistent_context_integration.py:_build_tournament_stub.
    """
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

    t = object.__new__(InverseStrategyTournament)
    t.name = "InverseStrategyTournament"
    t.config = {
        "tournament": {"rounds": 1, "context_mode": "persistent"},
        "game": {"name": "BattleSnake", "sims_per_round": 4},
        "players": [],
        "prompts": {},
    }
    t._metadata = {}
    t.cleanup_on_end = False
    t.logger = logging.getLogger("test")
    t._output_dir = tmp_path
    # Game arena mock — its run_round will be controlled by patches
    t.game = MagicMock()
    t.game.name = "BattleSnake"
    t.game.log_local = tmp_path / "logs"
    t.game.log_local.mkdir(parents=True, exist_ok=True)
    # Agents
    t.target_agent = MagicMock(name="target")
    t.opponent_agent = MagicMock(name="opponent")
    t.game_agents = [t.target_agent, t.opponent_agent]
    return t


class TestSimulationFailureRecording:
    def test_timeout_records_failure_and_reraises(self, tmp_path):
        """When game.run_round raises (e.g., subprocess.TimeoutExpired from
        the arena's bounded execute call), _run_multi_opponent_sim must:
          1. Record evaluation_failed[round_num] = True.
          2. Record evaluation_errors[round_num] with a non-empty message.
          3. Record distance_history[round_num] = None.
          4. Record submission_status_per_round[round_num] = "simulation_failed".
          5. Record opponent_history[round_num] = full opponents list.
          6. Persist via _save().
          7. Re-raise the original exception.
        """
        t = _build_minimal_tournament_stub(tmp_path)

        opp_a = tmp_path / "opp_a"
        opp_a.mkdir()
        opp_b = tmp_path / "opp_b"
        opp_b.mkdir()
        opponents = [opp_a, opp_b]

        timeout_exc = subprocess.TimeoutExpired(cmd="run_game.sh", timeout=4000)
        t.game.run_round.side_effect = timeout_exc

        with patch.object(t, "_save", return_value=None) as mock_save:
            with pytest.raises(subprocess.TimeoutExpired):
                t._run_multi_opponent_sim(round_num=0, opponents=opponents)

        # Failure recorded
        assert t._metadata.get("distance_history", {}).get(0) is None
        assert t._metadata.get("evaluation_failed", {}).get(0) is True
        err = t._metadata.get("evaluation_errors", {}).get(0, "")
        assert "TimeoutExpired" in err
        assert "opp_a" in err  # the failing opponent's name
        assert (
            t._metadata.get("submission_status_per_round", {}).get(0)
            == "simulation_failed"
        )
        assert t._metadata.get("opponent_history", {}).get(0) == [
            str(opp_a),
            str(opp_b),
        ]
        # And metadata was persisted at least once during the failure path
        assert mock_save.called

    def test_generic_exception_also_recorded(self, tmp_path):
        """A non-timeout exception (e.g., RuntimeError from arena.get_results)
        must also be recorded with the same shape."""
        t = _build_minimal_tournament_stub(tmp_path)

        opp = tmp_path / "opp_c"
        opp.mkdir()
        opponents = [opp]
        t.game.run_round.side_effect = RuntimeError("engine returned non-zero exit")

        with patch.object(t, "_save", return_value=None):
            with pytest.raises(RuntimeError, match="engine returned non-zero exit"):
                t._run_multi_opponent_sim(round_num=0, opponents=opponents)

        assert t._metadata.get("evaluation_failed", {}).get(0) is True
        assert "RuntimeError" in t._metadata.get("evaluation_errors", {}).get(0, "")

    def test_failure_at_second_opponent_records_partial_progress(self, tmp_path):
        """If opponent 1 succeeds but opponent 2 raises, the recorded
        evaluation_errors message must identify the failing opponent index."""
        t = _build_minimal_tournament_stub(tmp_path)

        opp_a = tmp_path / "opp_aa"
        opp_a.mkdir()
        opp_b = tmp_path / "opp_bb"
        opp_b.mkdir()
        opp_c = tmp_path / "opp_cc"
        opp_c.mkdir()
        opponents = [opp_a, opp_b, opp_c]

        # Make game.run_round succeed on the first call, fail on the second.
        good_stats = MagicMock()
        good_stats.to_dict.return_value = {"ok": True}
        t.game.run_round.side_effect = [good_stats, RuntimeError("hung"), good_stats]

        # Stub _move_sim_files_to_subdir so we don't try to move real files.
        with patch.object(t, "_move_sim_files_to_subdir"), patch.object(
            t, "_save", return_value=None
        ):
            with pytest.raises(RuntimeError):
                t._run_multi_opponent_sim(round_num=0, opponents=opponents)

        err = t._metadata.get("evaluation_errors", {}).get(0, "")
        assert "2/3" in err  # opponent 2 of 3 failed
        assert "opp_bb" in err
