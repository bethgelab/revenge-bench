"""
Tests for traces/parsers/huskybench.py - HuskyBenchTraceParser.

Tests:
1. normalize_action() with various input formats
2. actions_equal() including binned raise comparisons
3. bin_raise() for raise amount binning
4. extract_state_action_pairs() with synthetic game_log data
5. Community card slicing (no future info leakage)
6. State reconstruction (pot, stacks, action_history)
7. HuskyBenchTraceParser parse_file / parse_content
"""

import json

import pytest

from revenge_bench.traces.models import GameTrace
from revenge_bench.traces.parsers.huskybench import (
    HuskyBenchTraceParser,
    actions_distance,
    extract_state_action_pairs,
    normalize_action,
)

# =============================================================================
# Sample game log fixture
# =============================================================================

SAMPLE_HAND = {
    "gameId": "test-hand-001",
    "playerNames": {"100": "target", "200": "opponent"},
    "blinds": {"small": 5, "big": 10},
    "finalBoard": ["Td", "Ts", "Kh", "Jc", "Jh"],
    "playerHands": {
        "100": ["Ah", "Ks"],
        "200": ["7c", "2d"],
    },
    "playerMoney": {
        "initialAmount": 10000,
        "finalMoney": {"100": 10030, "200": 9970},
        "gameScores": {"100": 30, "200": -30},
    },
    "rounds": {
        "0": {  # Preflop
            "pot": 40,
            "bets": {"100": 20, "200": 20},
            "actions": {"100": "RAISE", "200": "CALL"},
            "action_sequence": [
                {
                    "player": 100,
                    "action": "RAISE",
                    "amount": 15,
                    "timestamp": 1000000,
                    "pot_after_action": 15,
                    "total_pot_after_action": 15,
                },
                {
                    "player": 200,
                    "action": "CALL",
                    "amount": 15,
                    "timestamp": 1000001,
                    "pot_after_action": 15,
                    "total_pot_after_action": 30,
                },
            ],
        },
        "1": {  # Flop
            "pot": 60,
            "bets": {"100": 10, "200": 10},
            "actions": {"100": "CHECK", "200": "CHECK"},
            "action_sequence": [
                {
                    "player": 100,
                    "action": "CHECK",
                    "amount": 0,
                    "timestamp": 1000002,
                    "pot_after_action": 0,
                    "total_pot_after_action": 30,
                },
                {
                    "player": 200,
                    "action": "CHECK",
                    "amount": 0,
                    "timestamp": 1000003,
                    "pot_after_action": 0,
                    "total_pot_after_action": 30,
                },
            ],
        },
        "2": {  # Turn
            "pot": 60,
            "bets": {"100": 0, "200": 0},
            "actions": {"200": "FOLD"},
            "action_sequence": [
                {
                    "player": 100,
                    "action": "RAISE",
                    "amount": 20,
                    "timestamp": 1000004,
                    "pot_after_action": 20,
                    "total_pot_after_action": 50,
                },
                {
                    "player": 200,
                    "action": "FOLD",
                    "amount": 0,
                    "timestamp": 1000005,
                    "pot_after_action": 0,
                    "total_pot_after_action": 50,
                },
            ],
        },
    },
}


@pytest.fixture
def sample_hand():
    return SAMPLE_HAND.copy()


@pytest.fixture
def sample_game_log(tmp_path, sample_hand):
    """Write sample hand to a game_log file and return its path."""
    path = tmp_path / "game_log_0_test-hand-001.json"
    path.write_text(json.dumps(sample_hand))
    return path


@pytest.fixture
def parser():
    return HuskyBenchTraceParser()


# =============================================================================
# Tests: normalize_action
# =============================================================================


class TestNormalizeAction:
    def test_fold_lowercase(self):
        assert normalize_action("fold") == "FOLD"

    def test_fold_uppercase(self):
        assert normalize_action("FOLD") == "FOLD"

    def test_check(self):
        assert normalize_action("CHECK") == "CHECK"

    def test_call(self):
        assert normalize_action("call") == "CALL"

    def test_raise_plain_no_context_defaults_to_half(self):
        # No player_stack context -> default to midpoint 0.5
        assert normalize_action("RAISE") == "RAISE:0.5000"

    def test_raise_ratio_format_passthrough(self):
        # Already in ratio format -> normalize to 4 decimal places
        assert normalize_action("RAISE:0.2500") == "RAISE:0.2500"
        assert normalize_action("RAISE:1.0") == "RAISE:1.0000"
        assert normalize_action("RAISE:0.75") == "RAISE:0.7500"

    def test_raise_old_binned_returns_none(self):
        # Old binned format is no longer valid
        assert normalize_action("RAISE:SMALL") is None
        assert normalize_action("RAISE:MEDIUM") is None
        assert normalize_action("RAISE:LARGE") is None
        assert normalize_action("RAISE:ALLIN") is None

    def test_dict_format_fold(self):
        assert normalize_action({"action": "FOLD", "amount": 0}) == "FOLD"

    def test_dict_format_raise_with_stack(self):
        # amount=50, player_stack=200 -> ratio=0.25
        result = normalize_action({"action": "RAISE", "amount": 50}, player_stack=200)
        assert result == "RAISE:0.2500"

    def test_dict_format_raise_allin(self):
        # amount >= player_stack -> ratio=1.0
        result = normalize_action({"action": "RAISE", "amount": 500}, player_stack=500)
        assert result == "RAISE:1.0000"

    def test_none_returns_none(self):
        assert normalize_action(None) is None

    def test_invalid_string_returns_none(self):
        assert normalize_action("BLUFF") is None

    def test_invalid_type_returns_none(self):
        assert normalize_action(42) is None


# =============================================================================
# Tests: actions_distance
# =============================================================================


class TestActionsDistance:
    """Raise-distance is log-normalized per the actor's stack S:
        c(r; S) = log1p(r * S) / log1p(S)
        d(r1, r2; S) = |c(r1; S) - c(r2; S)|
    Passed via optional player_stack (default 10_000 when None).
    See revenge_bench/traces/parsers/huskybench.py::actions_distance.
    """

    # --- Identity / non-raise rules (stack-agnostic) -------------------------

    def test_same_fold(self):
        assert actions_distance("FOLD", "FOLD") == 0.0

    def test_same_check(self):
        assert actions_distance("CHECK", "CHECK") == 0.0

    def test_same_call(self):
        assert actions_distance("CALL", "CALL") == 0.0

    def test_fold_vs_check(self):
        assert actions_distance("FOLD", "CHECK") == pytest.approx(1.0)

    def test_fold_vs_call(self):
        assert actions_distance("FOLD", "CALL") == pytest.approx(1.0)

    def test_check_vs_call(self):
        assert actions_distance("CHECK", "CALL") == pytest.approx(0.0)

    def test_same_raise(self):
        assert actions_distance("RAISE:0.5000", "RAISE:0.5000") == 0.0

    def test_raise_vs_fold(self):
        assert actions_distance("RAISE:0.5000", "FOLD") == 1.0

    def test_none_left_returns_max(self):
        assert actions_distance(None, "FOLD") == 1.0

    def test_none_right_returns_max(self):
        assert actions_distance("FOLD", None) == 1.0

    # --- Symmetry ------------------------------------------------------------

    def test_symmetry_fold_vs_passive(self):
        assert actions_distance("FOLD", "CHECK") == actions_distance("CHECK", "FOLD")

    def test_symmetry_raise_vs_passive(self):
        assert actions_distance("RAISE:0.3000", "CALL") == actions_distance(
            "CALL", "RAISE:0.3000"
        )

    def test_symmetry_raise(self):
        assert actions_distance("RAISE:0.3000", "RAISE:0.8000") == actions_distance(
            "RAISE:0.8000", "RAISE:0.3000"
        )

    # --- Raise distances at the default stack (S = 10_000) ------------------

    def test_raise_ratio_distance_log_scale(self):
        # |log1p(2500) - log1p(7500)| / log1p(10_000) ≈ 0.119250
        # (under linear this was exactly 0.5).
        assert actions_distance("RAISE:0.2500", "RAISE:0.7500") == pytest.approx(
            0.119250, abs=1e-4
        )

    def test_raise_allin_vs_zero_is_max(self):
        assert actions_distance("RAISE:1.0000", "RAISE:0.0000") == pytest.approx(1.0)

    def test_raise_half_vs_call_under_log(self):
        # c(0.5; 10_000) = log1p(5000) / log1p(10_000) ≈ 0.924754.
        assert actions_distance("RAISE:0.5000", "CALL") == pytest.approx(
            0.924754, abs=1e-4
        )

    def test_raise_quarter_vs_check_under_log(self):
        # c(0.25; 10_000) ≈ 0.849519.
        assert actions_distance("RAISE:0.2500", "CHECK") == pytest.approx(
            0.849519, abs=1e-4
        )

    def test_small_raise_vs_passive_is_meaningful(self):
        # KEY difference vs linear: a 1%-of-stack raise vs CALL is ~0.50,
        # not 0.01 — the whole point of the log scale.
        assert actions_distance("RAISE:0.0100", "CALL") == pytest.approx(
            0.501075, abs=1e-4
        )

    def test_tiny_raise_separates_from_check(self):
        # Single-chip raise on full stack: c(0.0001; 10_000) ≈ 0.075.
        assert actions_distance("RAISE:0.0001", "CHECK") == pytest.approx(
            0.075257, abs=1e-4
        )

    def test_case_insensitive(self):
        assert actions_distance("fold", "check") == pytest.approx(1.0)
        assert actions_distance("raise:0.5000", "call") == pytest.approx(
            0.924754, abs=1e-4
        )

    # --- Stack parameter: None falls back to 10_000 --------------------------

    def test_default_stack_matches_explicit_10000(self):
        d_default = actions_distance("RAISE:0.2500", "RAISE:0.7500")
        d_explicit = actions_distance(
            "RAISE:0.2500", "RAISE:0.7500", player_stack=10_000
        )
        assert d_default == pytest.approx(d_explicit)

    # --- Per-stack normalization (short-stack invariants) -------------------

    def test_allin_vs_passive_is_max_at_any_stack(self):
        # The [0, 1] range must hold per state, regardless of stack size.
        for stack in (10_000, 1_000, 100, 20):
            assert actions_distance(
                "RAISE:1.0000", "CHECK", player_stack=stack
            ) == pytest.approx(1.0)
            assert actions_distance(
                "RAISE:1.0000", "CALL", player_stack=stack
            ) == pytest.approx(1.0)

    def test_short_stack_differs_from_default(self):
        # Same ratios, different stacks should yield different distances.
        d_short = actions_distance("RAISE:0.5000", "CHECK", player_stack=1_000)
        d_full = actions_distance("RAISE:0.5000", "CHECK", player_stack=10_000)
        assert d_short == pytest.approx(0.899816, abs=1e-4)
        assert d_full == pytest.approx(0.924754, abs=1e-4)
        assert d_short != pytest.approx(d_full, abs=1e-3)

    def test_short_stack_raise_vs_raise(self):
        # c(0.1; 1000) vs c(0.5; 1000): |log1p(100) - log1p(500)| / log1p(1000)
        # ≈ 0.231805.
        assert actions_distance(
            "RAISE:0.1000", "RAISE:0.5000", player_stack=1_000
        ) == pytest.approx(0.231805, abs=1e-4)

    def test_distance_always_in_unit_interval(self):
        # Spot-check the bounds across ratios and stack sizes.
        import itertools
        ratios = [0.0, 0.0001, 0.01, 0.1, 0.25, 0.5, 0.75, 1.0]
        stacks = [10_000, 1_000, 100, 20]
        for r1, r2 in itertools.product(ratios, ratios):
            a1 = f"RAISE:{r1:.4f}"
            a2 = f"RAISE:{r2:.4f}"
            for S in stacks:
                d = actions_distance(a1, a2, player_stack=S)
                assert 0.0 <= d <= 1.0, f"{a1} vs {a2} at S={S} -> {d}"


# =============================================================================
# Tests: extract_state_action_pairs
# =============================================================================


class TestExtractStateActionPairs:
    def test_extracts_target_pairs(self, sample_game_log):
        """Should extract state-action pairs for the target player."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        # target acts in: preflop (RAISE), flop (CHECK), turn (RAISE)
        assert len(pairs) == 3

    def test_extracts_opponent_pairs(self, sample_game_log):
        """Should extract state-action pairs for the opponent player."""
        pairs = extract_state_action_pairs(sample_game_log, "opponent")
        # opponent acts in: preflop (CALL), flop (CHECK), turn (FOLD)
        assert len(pairs) == 3

    def test_unknown_player_returns_empty(self, sample_game_log):
        pairs = extract_state_action_pairs(sample_game_log, "nonexistent")
        assert pairs == []

    def test_connected_player_id_selector_with_anonymized_names(
        self, tmp_path, sample_hand
    ):
        """Should resolve connected IDs when game logs anonymize player names."""
        hand = json.loads(json.dumps(sample_hand))
        id_map = {"100": "99", "200": "199"}

        hand["playerNames"] = {
            "99": "player100",
            "199": "player200",
        }
        hand["playerHands"] = {
            id_map[pid]: cards for pid, cards in hand["playerHands"].items()
        }
        hand["playerMoney"]["finalMoney"] = {
            id_map[pid]: amount
            for pid, amount in hand["playerMoney"]["finalMoney"].items()
        }
        hand["playerMoney"]["gameScores"] = {
            id_map[pid]: score
            for pid, score in hand["playerMoney"]["gameScores"].items()
        }

        for round_data in hand["rounds"].values():
            round_data["bets"] = {
                id_map[pid]: amount for pid, amount in round_data["bets"].items()
            }
            round_data["actions"] = {
                id_map[pid]: action for pid, action in round_data["actions"].items()
            }
            for seq_action in round_data.get("action_sequence", []):
                seq_action["player"] = int(id_map[str(seq_action["player"])])

        path = tmp_path / "game_log_0_anonymized.json"
        path.write_text(json.dumps(hand))

        # Connected client id "100" should resolve to internal id key "99".
        pairs = extract_state_action_pairs(path, "100")
        assert len(pairs) == 3

    def test_state_has_required_fields(self, sample_game_log):
        """Each state should have all required fields."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        state, action = pairs[0]

        assert "game_id" in state
        assert "hand_number" in state
        assert "round" in state
        assert "position" in state
        assert "hole_cards" in state
        assert "community_cards" in state
        assert "pot" in state
        assert "current_bet" in state
        assert "my_stack" in state
        assert "opponent_stacks" in state
        assert "blinds" in state
        assert "action_history" in state

    def test_preflop_no_community_cards(self, sample_game_log):
        """Preflop state should have no community cards."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        # First action is preflop
        state, action = pairs[0]
        assert state["round"] == "preflop"
        assert state["community_cards"] == []

    def test_flop_has_three_community_cards(self, sample_game_log):
        """Flop state should have exactly 3 community cards."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        # Second action is flop
        state, action = pairs[1]
        assert state["round"] == "flop"
        assert len(state["community_cards"]) == 3
        assert state["community_cards"] == ["Td", "Ts", "Kh"]

    def test_turn_has_four_community_cards(self, sample_game_log):
        """Turn state should have exactly 4 community cards."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        # Third action is turn
        state, action = pairs[2]
        assert state["round"] == "turn"
        assert len(state["community_cards"]) == 4
        assert state["community_cards"] == ["Td", "Ts", "Kh", "Jc"]

    def test_hole_cards_are_players_own(self, sample_game_log):
        """State should contain the correct player's hole cards."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        state, _ = pairs[0]
        assert state["hole_cards"] == ["Ah", "Ks"]

        pairs_opp = extract_state_action_pairs(sample_game_log, "opponent")
        state_opp, _ = pairs_opp[0]
        assert state_opp["hole_cards"] == ["7c", "2d"]

    def test_action_history_uses_you_and_opponent(self, sample_game_log):
        """Action history should use 'you'/'opponent' labels, not player IDs."""
        pairs = extract_state_action_pairs(sample_game_log, "opponent")
        # Opponent's first action is preflop CALL (second in sequence)
        state, _ = pairs[0]
        # Should see target's RAISE before this action
        assert len(state["action_history"]) == 1
        assert (
            state["action_history"][0]["player"] == "opponent"
        )  # target is "opponent" from opponent's view

    def test_actions_are_canonical(self, sample_game_log):
        """Extracted actions should be in canonical format (FOLD/CHECK/CALL or RAISE:<ratio>)."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        for _state, action in pairs:
            assert action in ("FOLD", "CHECK", "CALL") or action.startswith("RAISE:")
            if action.startswith("RAISE:"):
                ratio = float(action.split(":")[1])
                assert 0.0 < ratio <= 1.0

    def test_pot_computed_correctly_at_flop(self, sample_game_log):
        """Pot at flop should include preflop bets."""
        pairs = extract_state_action_pairs(sample_game_log, "target")
        flop_state, _ = pairs[1]
        # Preflop: target raised 15, opponent called 15 -> pot = 30
        assert flop_state["pot"] == 30

    def test_stacks_decrease_with_bets(self, sample_game_log):
        """Player stacks should decrease as bets are placed."""
        pairs = extract_state_action_pairs(sample_game_log, "target")

        # At preflop (first action), no bets placed yet -> full stack
        preflop_state, _ = pairs[0]
        assert preflop_state["my_stack"] == 10000

        # At flop, target has bet 15 in preflop -> stack = 10000 - 15
        flop_state, _ = pairs[1]
        assert flop_state["my_stack"] == 10000 - 15


# =============================================================================
# Tests: HuskyBenchTraceParser
# =============================================================================


class TestHuskyBenchTraceParser:
    def test_parse_file_returns_game_trace(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        assert isinstance(trace, GameTrace)

    def test_parse_extracts_game_id(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        assert trace.game_id == "test-hand-001"

    def test_parse_extracts_game_type(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        assert trace.game_type == "HuskyBench"

    def test_parse_extracts_players(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        player_names = [p["name"] for p in trace.metadata.players]
        assert "target" in player_names
        assert "opponent" in player_names

    def test_parse_extracts_winner(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        assert trace.winner == "target"
        assert trace.is_draw is False

    def test_parse_extracts_turns_per_round(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        # 3 betting rounds (preflop, flop, turn)
        assert trace.total_turns == 3

    def test_parse_content_directly(self, parser, sample_hand):
        content = json.dumps(sample_hand)
        trace = parser.parse_content(content)
        assert trace.game_id == "test-hand-001"

    def test_source_metadata_attached(self, parser, sample_game_log):
        source = {"tournament_id": "test-tournament", "round": 1}
        trace = parser.parse_file(sample_game_log, source=source)
        assert trace.metadata.source["tournament_id"] == "test-tournament"

    def test_results_have_scores(self, parser, sample_game_log):
        trace = parser.parse_file(sample_game_log)
        for result in trace.results:
            assert result.final_score is not None


# =============================================================================
# Tests: Collector Integration
# =============================================================================


class TestCollectorIntegration:
    def test_collector_uses_huskybench_parser(self):
        from revenge_bench.traces.collector import TraceCollector

        collector = TraceCollector(game_type="HuskyBench")
        assert collector.parser_class.__name__ == "HuskyBenchTraceParser"

    def test_collector_parses_directory(self, tmp_path, sample_hand):
        from revenge_bench.traces.collector import TraceCollector

        # Write fixture with expected naming
        path = tmp_path / "game_log_0_test.json"
        path.write_text(json.dumps(sample_hand))

        collector = TraceCollector(game_type="HuskyBench")
        traces = collector.collect_from_round(tmp_path)

        assert len(traces) == 1
        assert traces[0].game_id == "test-hand-001"


# =============================================================================
# Tests: Draw game
# =============================================================================


class TestDrawGame:
    def test_draw_when_scores_zero(self, parser, tmp_path):
        """Game with both scores = 0 should be a draw."""
        hand = SAMPLE_HAND.copy()
        hand["playerMoney"] = {
            "initialAmount": 10000,
            "finalMoney": {"100": 10000, "200": 10000},
            "gameScores": {"100": 0, "200": 0},
        }
        path = tmp_path / "game_log_draw.json"
        path.write_text(json.dumps(hand))

        trace = parser.parse_file(path)
        assert trace.is_draw is True
        assert trace.winner is None
