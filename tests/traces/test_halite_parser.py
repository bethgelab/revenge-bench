"""
Tests for the Halite I trace parser.
"""

import pytest

from revenge_bench.traces.parsers.halite import (
    MOVE_EAST,
    MOVE_NORTH,
    MOVE_SOUTH,
    MOVE_STILL,
    MOVE_WEST,
    actions_distance,
    extract_player_state,
    extract_state_action_pairs,
    normalize_action,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def minimal_frame():
    """
    A minimal 3x3 frame with two active players.

    Cell format: [owner, strength]
      owner 0 = neutral, 1 = player 1, 2 = player 2
    """
    return [
        [[0, 10], [1, 50], [0, 5]],  # row 0
        [[2, 30], [0, 8], [0, 12]],  # row 1
        [[0, 6], [0, 9], [0, 4]],  # row 2
    ]


@pytest.fixture
def minimal_data():
    """Minimal replay data to accompany frames."""
    return {
        "width": 3,
        "height": 3,
        "player_names": ["BotA", "BotB"],
        "num_players": 2,
        "productions": [
            [2, 3, 4],
            [1, 5, 2],
            [3, 1, 4],
        ],
    }


@pytest.fixture
def minimal_move_grid():
    """A 3x3 move grid for the minimal frame (owner=1 is at (0,1))."""
    return [
        [MOVE_STILL, MOVE_NORTH, MOVE_STILL],  # row 0
        [MOVE_EAST, MOVE_STILL, MOVE_STILL],  # row 1
        [MOVE_STILL, MOVE_STILL, MOVE_STILL],  # row 2
    ]


# =============================================================================
# extract_player_state
# =============================================================================


class TestExtractPlayerState:
    def _cells_at(self, state, r, c):
        """Return the cell entry [r, c, owner, strength, production] at (r, c), or None."""
        for cell in state["cells"]:
            if cell[0] == r and cell[1] == c:
                return cell
        return None

    def test_returns_state_for_active_player(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        assert state is not None
        assert state["turn"] == 0
        assert state["width"] == 3
        assert state["height"] == 3

    def test_cells_contains_owned_cell(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        # Player 1 owns (0, 1) with strength 50
        cell = self._cells_at(state, 0, 1)
        assert cell is not None
        assert cell[2] == 1  # owner
        assert cell[3] == 50  # strength

    def test_cells_contains_enemy_cell(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        # Player 2 owns (1, 0) with strength 30
        cell = self._cells_at(state, 1, 0)
        assert cell is not None
        assert cell[2] == 2  # owner
        assert cell[3] == 30  # strength

    def test_neutral_cells_excluded(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        # Neutral cells (owner == 0) must not appear in cells
        owners = [cell[2] for cell in state["cells"]]
        assert 0 not in owners

    def test_production_included_in_cells(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        # Cell (0, 1): production should be minimal_data["productions"][0][1] = 3
        cell = self._cells_at(state, 0, 1)
        assert cell is not None
        assert cell[4] == 3  # production

    def test_player_names_present(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        assert "player_names" in state
        assert state["player_names"] == minimal_data["player_names"]

    def test_dimensions_from_data(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        assert state["width"] == minimal_data["width"]
        assert state["height"] == minimal_data["height"]

    def test_state_is_neutral_regardless_of_player_tag(
        self, minimal_frame, minimal_data
    ):
        """Same cells appear regardless of which player_tag is passed."""
        state1 = extract_player_state(minimal_frame, 0, 1, minimal_data)
        state2 = extract_player_state(minimal_frame, 0, 2, minimal_data)
        assert state1["cells"] == state2["cells"]

    def test_cells_are_json_serializable(self, minimal_frame, minimal_data):
        import json

        state = extract_player_state(minimal_frame, 0, 1, minimal_data)
        # Must not raise
        json.dumps(state)


# =============================================================================
# extract_state_action_pairs
# =============================================================================


class TestExtractStateActionPairs:
    def _make_hlt_file(self, tmp_path, data: dict, filename: str = "1234-5678.hlt"):
        import json

        hlt_file = tmp_path / filename
        hlt_file.write_text(json.dumps(data))
        return hlt_file

    def test_basic_pairs_extracted(
        self, tmp_path, minimal_frame, minimal_data, minimal_move_grid
    ):
        """Extract one turn's pairs from a minimal replay."""
        data = {
            **minimal_data,
            "num_frames": 2,
            "frames": [minimal_frame, minimal_frame],
            "moves": [minimal_move_grid],  # one move grid (for frame 0)
        }
        hlt_file = self._make_hlt_file(tmp_path, data)
        pairs = extract_state_action_pairs(hlt_file, "BotA")

        assert len(pairs) == 1
        state, action = pairs[0]
        assert "cells" in state
        # Player 1 (BotA) owns cell (0, 1); move is NORTH (1)
        assert [0, 1, MOVE_NORTH] in action

    def test_action_only_covers_owned_cells(
        self, tmp_path, minimal_frame, minimal_data, minimal_move_grid
    ):
        """Action triples must only include cells owned by the player."""
        data = {
            **minimal_data,
            "num_frames": 2,
            "frames": [minimal_frame, minimal_frame],
            "moves": [minimal_move_grid],
        }
        hlt_file = self._make_hlt_file(tmp_path, data)
        pairs = extract_state_action_pairs(hlt_file, "BotA")

        state, action = pairs[0]
        # Only player 1's cell (0, 1) should be in BotA's action
        rows_cols = [(t[0], t[1]) for t in action]
        assert (0, 1) in rows_cols
        # Enemy cell (1, 0) must not appear
        assert (1, 0) not in rows_cols

    def test_action_is_sorted(self, tmp_path, minimal_data):
        """Action triples must be sorted by (row, col, move)."""
        # Player 1 owns multiple cells
        frame = [
            [[1, 20], [1, 30], [0, 5]],
            [[0, 8], [1, 15], [0, 12]],
            [[0, 6], [0, 9], [0, 4]],
        ]
        move_grid = [
            [MOVE_NORTH, MOVE_EAST, MOVE_STILL],
            [MOVE_STILL, MOVE_SOUTH, MOVE_STILL],
            [MOVE_STILL, MOVE_STILL, MOVE_STILL],
        ]
        data = {
            **minimal_data,
            "num_frames": 2,
            "frames": [frame, frame],
            "moves": [move_grid],
        }
        hlt_file = self._make_hlt_file(tmp_path, data)
        pairs = extract_state_action_pairs(hlt_file, "BotA")

        state, action = pairs[0]
        assert action == sorted(action), "Action triples should be sorted"

    def test_returns_empty_for_unknown_player(
        self, tmp_path, minimal_frame, minimal_data, minimal_move_grid
    ):
        data = {
            **minimal_data,
            "num_frames": 2,
            "frames": [minimal_frame, minimal_frame],
            "moves": [minimal_move_grid],
        }
        hlt_file = self._make_hlt_file(tmp_path, data)
        pairs = extract_state_action_pairs(hlt_file, "NonExistentBot")
        assert pairs == []

    def test_multiple_turns(self, tmp_path, minimal_data):
        """All turns are returned (one pair per move grid)."""
        frame = [
            [[1, 20], [0, 10], [0, 5]],
            [[0, 8], [0, 15], [2, 12]],
            [[0, 6], [0, 9], [0, 4]],
        ]
        move_grid = [
            [MOVE_NORTH, MOVE_STILL, MOVE_STILL],
            [MOVE_STILL, MOVE_STILL, MOVE_EAST],
            [MOVE_STILL, MOVE_STILL, MOVE_STILL],
        ]
        data = {
            **minimal_data,
            "num_frames": 4,
            "frames": [frame, frame, frame, frame],
            "moves": [move_grid, move_grid, move_grid],  # 3 move grids
        }
        hlt_file = self._make_hlt_file(tmp_path, data)
        pairs = extract_state_action_pairs(hlt_file, "BotA")
        assert len(pairs) == 3


# =============================================================================
# actions_distance
# =============================================================================


class TestActionsDistance:
    """Test normalized action distance (0.0 = identical, 1.0 = completely different)."""

    def test_identical_actions_return_zero(self):
        """Identical actions have distance 0.0."""
        action = [[0, 5, MOVE_NORTH]]
        assert actions_distance(action, action) == 0.0

    def test_order_independent(self):
        """Distance is order-independent (uses sets internally)."""
        a1 = [[0, 5, MOVE_NORTH], [2, 3, MOVE_STILL]]
        a2 = [[2, 3, MOVE_STILL], [0, 5, MOVE_NORTH]]
        assert actions_distance(a1, a2) == 0.0

    def test_different_direction_one_cell(self):
        """One cell with different move = distance 1.0."""
        a1 = [[0, 5, MOVE_NORTH]]
        a2 = [[0, 5, MOVE_SOUTH]]
        assert actions_distance(a1, a2) == 1.0

    def test_partial_match(self):
        """50% cells match = distance 0.5."""
        a1 = [[0, 5, MOVE_NORTH], [2, 3, MOVE_STILL]]
        a2 = [[0, 5, MOVE_NORTH], [2, 3, MOVE_EAST]]  # One cell different
        assert actions_distance(a1, a2) == 0.5

    def test_completely_different_cells(self):
        """Different cells controlled = distance 1.0."""
        a1 = [[0, 5, MOVE_NORTH]]
        a2 = [[2, 3, MOVE_STILL]]
        assert actions_distance(a1, a2) == 1.0

    def test_empty_actions_have_zero_distance(self):
        """Empty actions are equal."""
        assert actions_distance([], []) == 0.0

    def test_none_actions_equal(self):
        """None actions are equal (both invalid)."""
        assert actions_distance(None, None) == 0.0

    def test_none_vs_valid_is_one(self):
        """None vs valid action = distance 1.0."""
        assert actions_distance(None, [[0, 5, MOVE_NORTH]]) == 1.0
        assert actions_distance([[0, 5, MOVE_NORTH]], None) == 1.0

    def test_superset_action(self):
        """Action with extra cells has proportional distance."""
        a1 = [[0, 0, MOVE_STILL]]
        a2 = [[0, 0, MOVE_STILL], [1, 1, MOVE_NORTH]]
        # 1 of 2 cells match = distance 0.5
        assert actions_distance(a1, a2) == 0.5

    def test_three_cells_one_different(self):
        """2/3 cells match = distance 1/3."""
        a1 = [[0, 0, MOVE_NORTH], [1, 1, MOVE_EAST], [2, 2, MOVE_SOUTH]]
        a2 = [[0, 0, MOVE_NORTH], [1, 1, MOVE_EAST], [2, 2, MOVE_WEST]]
        assert actions_distance(a1, a2) == pytest.approx(1 / 3)

    def test_normalized_between_zero_and_one(self):
        """Distance is always normalized [0.0, 1.0]."""
        a1 = [[i, j, MOVE_NORTH] for i in range(5) for j in range(5)]  # 25 cells
        a2 = [[i, j, MOVE_SOUTH] for i in range(5) for j in range(5)]  # All different
        distance = actions_distance(a1, a2)
        assert 0.0 <= distance <= 1.0
        assert distance == 1.0  # All cells different


# =============================================================================
# normalize_action
# =============================================================================


class TestNormalizeAction:
    def test_valid_single_triple(self):
        action = [[0, 5, MOVE_NORTH]]
        assert normalize_action(action) == [[0, 5, MOVE_NORTH]]

    def test_valid_multiple_triples_returns_sorted(self):
        action = [[2, 1, MOVE_EAST], [0, 5, MOVE_NORTH]]
        result = normalize_action(action)
        assert result == sorted(result)
        assert [0, 5, MOVE_NORTH] in result
        assert [2, 1, MOVE_EAST] in result

    def test_accepts_tuple_triples(self):
        # Tuples should also be accepted
        action = [(0, 5, MOVE_NORTH)]
        result = normalize_action(action)
        assert result == [[0, 5, MOVE_NORTH]]

    def test_invalid_move_value_returns_none(self):
        action = [[0, 5, 99]]  # 99 is not a valid move
        assert normalize_action(action) is None

    def test_none_returns_none(self):
        assert normalize_action(None) is None

    def test_non_list_returns_none(self):
        assert normalize_action("move north") is None
        assert normalize_action(42) is None

    def test_empty_list(self):
        assert normalize_action([]) == []

    def test_wrong_triple_length_returns_none(self):
        assert normalize_action([[0, 5]]) is None  # too short
        assert normalize_action([[0, 5, 1, 2]]) is None  # too long

    def test_all_valid_moves(self):
        action = [
            [0, 0, MOVE_STILL],
            [0, 1, MOVE_NORTH],
            [0, 2, MOVE_EAST],
            [1, 0, MOVE_SOUTH],
            [1, 1, MOVE_WEST],
        ]
        result = normalize_action(action)
        assert result is not None
        assert len(result) == 5
