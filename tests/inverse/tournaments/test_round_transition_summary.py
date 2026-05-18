"""Tests for build_round_transition_summary."""

from revenge_bench.tournaments.inverse_strategy import build_round_transition_summary


class TestBuildRoundTransitionSummary:
    def test_includes_current_and_previous_distance(self):
        s = build_round_transition_summary(
            round_num=2, total_rounds=5, step_increment=30,
            distance_history={0: 0.7, 1: 0.5},
            mismatch_counts={0: 60, 1: 40},
            submission_status_per_round={1: "ok"},
        )
        assert s["distance"] == 0.5
        assert s["previous_distance"] == 0.7
        assert s["mismatches"] == 40
        assert s["submission_status"] == "ok"
        assert s["total_rounds"] == 5
        assert s["step_increment"] == 30

    def test_handles_missing_previous_round(self):
        s = build_round_transition_summary(
            round_num=2, total_rounds=5, step_increment=30,
            distance_history={1: 0.5},
            mismatch_counts={1: 40},
            submission_status_per_round={1: "ok"},
        )
        assert s["previous_distance"] is None

    def test_handles_failed_evaluation(self):
        s = build_round_transition_summary(
            round_num=2, total_rounds=5, step_increment=30,
            distance_history={0: 0.7, 1: None},
            mismatch_counts={0: 60, 1: None},
            submission_status_per_round={1: "evaluation_failed"},
        )
        assert s["distance"] is None
        assert s["submission_status"] == "evaluation_failed"
