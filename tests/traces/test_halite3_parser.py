"""
Tests for the Halite III trace parser.
"""

import pytest

from revenge_bench.traces.parsers.halite3 import (
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
    """A minimal frame with two active players."""
    return {
        "turn": 1,
        "cells": [],
        "energy": {"0": 5000, "1": 4800},
        "entities": {
            "0": {"1": {"x": 16, "y": 32, "energy": 100, "is_inspired": False}},
            "1": {"2": {"x": 48, "y": 32, "energy": 200, "is_inspired": False}},
        },
        "deposited": {"0": 0, "1": 0},
        "events": [],
        "moves": {
            "0": [{"type": "m", "id": 1, "direction": "n"}],
            "1": [{"type": "g"}],
        },
    }


@pytest.fixture
def minimal_data():
    """Minimal replay data to accompany frames."""
    return {
        "production_map": {"width": 64, "height": 64, "grid": []},
        "GAME_CONSTANTS": {},
        "players": [
            {"player_id": 0, "name": "BotA", "factory_location": {"x": 16, "y": 32}},
            {"player_id": 1, "name": "BotB", "factory_location": {"x": 48, "y": 32}},
        ],
    }


# =============================================================================
# extract_player_state
# =============================================================================


class TestExtractPlayerState:
    def test_returns_state_for_active_player(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, "0", minimal_data)
        assert state is not None
        assert state["my_energy"] == 5000
        assert state["my_ships"] == minimal_frame["entities"]["0"]
        assert state["my_shipyard"] == {"x": 16, "y": 32}

    def test_returns_none_for_eliminated_player(self, minimal_frame, minimal_data):
        """Player absent from entities is eliminated; state must be None."""
        frame_without_player0 = {
            **minimal_frame,
            "entities": {"1": minimal_frame["entities"]["1"]},
        }
        state = extract_player_state(frame_without_player0, "0", minimal_data)
        assert state is None

    def test_opponent_ids_exclude_self(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, "0", minimal_data)
        assert "0" not in state["opponent_ships"]
        assert "1" in state["opponent_ships"]

    def test_map_size_from_production_map(self, minimal_frame, minimal_data):
        state = extract_player_state(minimal_frame, "0", minimal_data)
        assert state["map_size"] == {"width": 64, "height": 64}


# =============================================================================
# extract_state_action_pairs
# =============================================================================


class TestExtractStateActionPairs:
    def test_skips_eliminated_frames(self, tmp_path, minimal_data):
        """Frames where the player has no entities entry must be skipped."""
        import json

        import zstandard as zstd

        active_frame = {
            "turn": 1,
            "cells": [],
            "energy": {"0": 5000, "1": 4800},
            "entities": {
                "0": {"1": {"x": 16, "y": 32, "energy": 100, "is_inspired": False}},
                "1": {"2": {"x": 48, "y": 32, "energy": 200, "is_inspired": False}},
            },
            "deposited": {},
            "events": [],
            "moves": {"0": [{"type": "m", "id": 1, "direction": "n"}], "1": []},
        }
        eliminated_frame = {
            "turn": 2,
            "cells": [],
            "energy": {"1": 4800},
            "entities": {
                # player 0 is gone
                "1": {"2": {"x": 48, "y": 32, "energy": 200, "is_inspired": False}},
            },
            "deposited": {},
            "events": [],
            "moves": {"1": []},
        }

        replay = {**minimal_data, "full_frames": [active_frame, eliminated_frame]}
        compressed = zstd.ZstdCompressor().compress(json.dumps(replay).encode())
        hlt_file = tmp_path / "test.hlt"
        hlt_file.write_bytes(compressed)

        pairs = extract_state_action_pairs(hlt_file, "BotA")

        # Only the active frame (idx=1, active_frame) should be included
        assert len(pairs) == 1
        state, actions = pairs[0]
        assert state["my_energy"] == 5000
        assert actions == [{"type": "m", "id": 1, "direction": "n"}]

    def test_returns_empty_for_unknown_player(self, tmp_path, minimal_data):
        import json

        import zstandard as zstd

        replay = {**minimal_data, "full_frames": []}
        compressed = zstd.ZstdCompressor().compress(json.dumps(replay).encode())
        hlt_file = tmp_path / "test.hlt"
        hlt_file.write_bytes(compressed)

        pairs = extract_state_action_pairs(hlt_file, "NonExistentBot")
        assert pairs == []


# =============================================================================
# actions_distance
# =============================================================================


class TestActionsDistance:
    """Test normalized action distance (0.0 = identical, 1.0 = completely different)."""

    def test_identical_move_returns_zero(self):
        """Identical move actions have distance 0.0."""
        action = [{"type": "m", "id": 1, "direction": "n"}]
        assert actions_distance(action, action) == 0.0

    def test_order_independent(self):
        """Distance is order-independent."""
        a1 = [{"type": "m", "id": 1, "direction": "n"}, {"type": "g"}]
        a2 = [{"type": "g"}, {"type": "m", "id": 1, "direction": "n"}]
        assert actions_distance(a1, a2) == 0.0

    def test_different_direction_same_ship(self):
        """Same ship, different direction = distance 1.0."""
        a1 = [{"type": "m", "id": 1, "direction": "n"}]
        a2 = [{"type": "m", "id": 1, "direction": "s"}]
        assert actions_distance(a1, a2) == 1.0

    def test_partial_match_two_actions(self):
        """1 of 2 actions match = distance 0.5."""
        a1 = [{"type": "m", "id": 1, "direction": "n"}, {"type": "g"}]
        a2 = [{"type": "m", "id": 1, "direction": "n"}]  # Missing spawn
        assert actions_distance(a1, a2) == 0.5

    def test_spawn_actions_match(self):
        """Identical spawn actions = distance 0.0."""
        assert actions_distance([{"type": "g"}], [{"type": "g"}]) == 0.0

    def test_different_action_types(self):
        """Different action types = distance 1.0."""
        a1 = [{"type": "g"}]
        a2 = [{"type": "m", "id": 1, "direction": "n"}]
        assert actions_distance(a1, a2) == 1.0

    def test_convert_actions(self):
        """Convert actions by ship id."""
        a1 = [{"type": "c", "id": 5}]
        a2 = [{"type": "c", "id": 5}]
        assert actions_distance(a1, a2) == 0.0

    def test_different_ship_ids(self):
        """Different ship ids = distance 1.0."""
        a1 = [{"type": "m", "id": 1, "direction": "n"}]
        a2 = [{"type": "m", "id": 2, "direction": "n"}]
        assert actions_distance(a1, a2) == 1.0

    def test_empty_actions_have_zero_distance(self):
        """Empty actions are equal."""
        assert actions_distance([], []) == 0.0

    def test_none_actions_equal(self):
        """None actions are equal (both invalid)."""
        assert actions_distance(None, None) == 0.0

    def test_none_vs_valid_is_one(self):
        """None vs valid action = distance 1.0."""
        assert actions_distance(None, [{"type": "g"}]) == 1.0
        assert actions_distance([{"type": "g"}], None) == 1.0

    def test_complex_action_set(self):
        """Complex action set with multiple ships."""
        a1 = [
            {"type": "m", "id": 1, "direction": "n"},
            {"type": "m", "id": 2, "direction": "e"},
            {"type": "g"},
        ]
        a2 = [
            {"type": "m", "id": 1, "direction": "n"},  # Same
            {"type": "m", "id": 2, "direction": "w"},  # Different direction
            {"type": "g"},  # Same
        ]
        # Union has 4 unique actions: (ship1 n, ship2 e, ship2 w, spawn)
        # Symmetric diff has 2: (ship2 e, ship2 w)
        # Distance = 2/4 = 0.5
        assert actions_distance(a1, a2) == 0.5

    def test_normalized_between_zero_and_one(self):
        """Distance is always normalized [0.0, 1.0]."""
        # Many different actions
        a1 = [{"type": "m", "id": i, "direction": "n"} for i in range(10)]
        a2 = [{"type": "m", "id": i, "direction": "s"} for i in range(10)]
        distance = actions_distance(a1, a2)
        assert 0.0 <= distance <= 1.0
        assert distance == 1.0  # All different


# =============================================================================
# normalize_action
# =============================================================================


class TestNormalizeAction:
    def test_valid_move(self):
        action = [{"type": "m", "id": 1, "direction": "n"}]
        assert normalize_action(action) == action

    def test_valid_spawn(self):
        assert normalize_action([{"type": "g"}]) == [{"type": "g"}]

    def test_filters_invalid_direction(self):
        action = [{"type": "m", "id": 1, "direction": "z"}]
        assert normalize_action(action) == []

    def test_none_returns_none(self):
        assert normalize_action(None) is None

    def test_non_list_returns_none(self):
        assert normalize_action("move north") is None

    def test_empty_list(self):
        assert normalize_action([]) == []
