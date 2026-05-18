"""
Tests for traces/parsers/robocode.py - RoboCodeTraceParser.

Written from the design doc (docs/plans/2026-02-16-robocode-inverse-strategy-design.md).

Tests:
1. normalize_action: canonical 5-key dict, missing keys default to 0.0, None handling
2. actions_distance: continuous [0,1] distance score (0=identical, 1=different)
3. extract_player_state: XML turn → simplified numeric dict (radians → degrees)
4. extract_player_action: consecutive turns → inferred action dict
5. extract_state_action_pairs: reads XML file, returns (state, action) tuples
6. RoboCodeTraceParser: produces GameTrace objects
7. Parser registry integration
"""

import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from revenge_bench.traces.models import GameTrace
from revenge_bench.traces.parsers.robocode import (
    ACTION_COMPONENTS,
    RoboCodeTraceParser,
    _parse_turn_elem,
    actions_distance,
    extract_player_action,
    extract_player_state,
    extract_state_action_pairs,
    normalize_action,
    parse_robocode_trace,
)

# =============================================================================
# Fixtures
# =============================================================================

FIXTURES_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "data"
    / "inverse"
    / "test_fixtures"
    / "traces"
    / "robocode"
)


@pytest.fixture
def short_game_path():
    """Path to short_game.xml fixture (2 rounds, fire event)."""
    return FIXTURES_DIR / "short_game.xml"


@pytest.fixture
def draw_game_path():
    """Path to draw_game.xml fixture (equal energy at end)."""
    return FIXTURES_DIR / "draw_game.xml"


@pytest.fixture
def parser():
    """Create a RoboCodeTraceParser instance."""
    return RoboCodeTraceParser()


def _make_xml_turns(turns_xml: str) -> str:
    """Wrap turn XML elements in a <record> root."""
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<record>\n{turns_xml}\n</record>'


def _parse_inline_turns(turns_xml: str) -> list[dict]:
    """Parse inline XML turn elements into dicts."""
    root = ET.fromstring(_make_xml_turns(turns_xml))
    return [_parse_turn_elem(elem) for elem in root.findall("turn")]


def _write_temp_xml(content: str) -> Path:
    """Write XML content to a temporary file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# =============================================================================
# Two-robot turn XML snippet for inline tests
# =============================================================================

TURN_A = """
<turn round="0" turn="0" ver="1">
    <robots>
        <robot id="0" vsName="MyTank*" state="ACTIVE"
               energy="100.0" x="100.0" y="200.0"
               bodyHeading="0.0" gunHeading="0.0" radarHeading="0.0"
               gunHeat="3.0" velocity="0.0"
               teamName="target.MyTank*" name="target.MyTank*"/>
        <robot id="1" vsName="EnemyBot*" state="ACTIVE"
               energy="90.0" x="600.0" y="400.0"
               bodyHeading="3.14159" gunHeading="3.14159" radarHeading="3.14159"
               gunHeat="3.0" velocity="0.0"
               teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets/>
</turn>
"""

TURN_B = """
<turn round="0" turn="1" ver="1">
    <robots>
        <robot id="0" vsName="MyTank*" state="ACTIVE"
               energy="100.0" x="108.0" y="200.0"
               bodyHeading="0.174533" gunHeading="0.349066" radarHeading="0.785398"
               gunHeat="2.8" velocity="8.0"
               teamName="target.MyTank*" name="target.MyTank*"/>
        <robot id="1" vsName="EnemyBot*" state="ACTIVE"
               energy="90.0" x="592.0" y="400.0"
               bodyHeading="3.31613" gunHeading="3.31613" radarHeading="3.31613"
               gunHeat="2.8" velocity="-8.0"
               teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets/>
</turn>
"""

# Turn C: target fires a bullet (new bullet owned by robot 0)
TURN_C_WITH_FIRE = """
<turn round="0" turn="2" ver="1">
    <robots>
        <robot id="0" vsName="MyTank*" state="ACTIVE"
               energy="97.0" x="116.0" y="200.0"
               bodyHeading="0.349066" gunHeading="0.698132" radarHeading="1.5708"
               gunHeat="1.6" velocity="8.0"
               teamName="target.MyTank*" name="target.MyTank*"/>
        <robot id="1" vsName="EnemyBot*" state="ACTIVE"
               energy="90.0" x="584.0" y="400.0"
               bodyHeading="3.49066" gunHeading="3.49066" radarHeading="3.49066"
               gunHeat="2.6" velocity="-8.0"
               teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets>
        <bullet id="b0" owner="0" state="FIRED"
                x="116.0" y="200.0" heading="0.698132" power="3.0"/>
    </bullets>
</turn>
"""

# Turn C variant: real RoboCode logs may omit owner attribute and encode it in id (e.g. "0-123")
TURN_C_WITH_FIRE_ID_PREFIX_OWNER = """
<turn round="0" turn="2" ver="1">
    <robots>
        <robot id="0" vsName="MyTank*" state="ACTIVE"
               energy="97.0" x="116.0" y="200.0"
               bodyHeading="0.349066" gunHeading="0.698132" radarHeading="1.5708"
               gunHeat="1.6" velocity="8.0"
               teamName="target.MyTank*" name="target.MyTank*"/>
        <robot id="1" vsName="EnemyBot*" state="ACTIVE"
               energy="90.0" x="584.0" y="400.0"
               bodyHeading="3.49066" gunHeading="3.49066" radarHeading="3.49066"
               gunHeat="2.6" velocity="-8.0"
               teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets>
        <bullet id="0-123" state="FIRED"
                x="116.0" y="200.0" heading="0.698132" power="2.0"/>
    </bullets>
</turn>
"""

# Turn C variant: ownerless bullet id without parsable owner prefix should be ignored
TURN_C_WITH_FIRE_UNPARSEABLE_ID = """
<turn round="0" turn="2" ver="1">
    <robots>
        <robot id="0" vsName="MyTank*" state="ACTIVE"
               energy="97.0" x="116.0" y="200.0"
               bodyHeading="0.349066" gunHeading="0.698132" radarHeading="1.5708"
               gunHeat="1.6" velocity="8.0"
               teamName="target.MyTank*" name="target.MyTank*"/>
        <robot id="1" vsName="EnemyBot*" state="ACTIVE"
               energy="90.0" x="584.0" y="400.0"
               bodyHeading="3.49066" gunHeading="3.49066" radarHeading="3.49066"
               gunHeat="2.6" velocity="-8.0"
               teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets>
        <bullet id="not-an-owner-prefix" state="FIRED"
                x="116.0" y="200.0" heading="0.698132" power="2.5"/>
    </bullets>
</turn>
"""

# Turn in round 1 (different round, should not pair with round 0 turns)
TURN_ROUND1 = """
<turn round="1" turn="0" ver="1">
    <robots>
        <robot id="0" vsName="MyTank*" state="ACTIVE"
               energy="100.0" x="200.0" y="300.0"
               bodyHeading="1.5708" gunHeading="1.5708" radarHeading="1.5708"
               gunHeat="3.0" velocity="0.0"
               teamName="target.MyTank*" name="target.MyTank*"/>
        <robot id="1" vsName="EnemyBot*" state="ACTIVE"
               energy="100.0" x="500.0" y="300.0"
               bodyHeading="4.71239" gunHeading="4.71239" radarHeading="4.71239"
               gunHeat="3.0" velocity="0.0"
               teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
    </robots>
    <bullets/>
</turn>
"""


# =============================================================================
# Tests: normalize_action
# =============================================================================


class TestNormalizeAction:
    """Tests for normalize_action() based on design doc spec."""

    def test_full_action_returns_same_values(self):
        """Action dict with all 5 keys should be returned unchanged."""
        action = {
            "velocity": 5.0,
            "turn_body": 3.0,
            "turn_gun": -10.0,
            "turn_radar": 20.0,
            "fire_power": 2.0,
        }
        result = normalize_action(action)
        assert result == action

    def test_missing_keys_default_to_zero(self):
        """Action dict with missing keys should have them filled with 0.0."""
        action = {"velocity": 5.0}
        result = normalize_action(action)
        assert result["velocity"] == 5.0
        assert result["turn_body"] == 0.0
        assert result["turn_gun"] == 0.0
        assert result["turn_radar"] == 0.0
        assert result["fire_power"] == 0.0

    def test_empty_dict_fills_all_zeros(self):
        """Empty dict should produce all-zeros action."""
        result = normalize_action({})
        for key in ACTION_COMPONENTS:
            assert result[key] == 0.0

    def test_none_returns_none(self):
        """None input should return None."""
        assert normalize_action(None) is None

    def test_non_dict_returns_none(self):
        """Non-dict input should return None."""
        assert normalize_action("velocity=5") is None
        assert normalize_action(42) is None
        assert normalize_action([1, 2, 3]) is None

    def test_values_converted_to_float(self):
        """Integer values should be converted to float."""
        action = {"velocity": 5, "fire_power": 2}
        result = normalize_action(action)
        assert isinstance(result["velocity"], float)
        assert isinstance(result["fire_power"], float)

    def test_result_has_exactly_five_keys(self):
        """Result should have exactly the 5 canonical action keys."""
        action = {"velocity": 1.0, "extra_key": 999}
        result = normalize_action(action)
        assert set(result.keys()) == set(ACTION_COMPONENTS)


# =============================================================================
# Tests: actions_distance
# =============================================================================


class TestActionsDistance:
    """Tests for actions_distance() — 0=identical, 1=different."""

    def test_identical_actions_return_0(self):
        """Identical actions should have distance 0.0."""
        a = {
            "velocity": 5.0,
            "turn_body": 3.0,
            "turn_gun": -10.0,
            "turn_radar": 20.0,
            "fire_power": 2.0,
        }
        assert actions_distance(a, a) == 0.0

    def test_all_zero_actions_return_0(self):
        """Two all-zero actions should have distance 0.0."""
        a = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }
        assert actions_distance(a, a) == 0.0

    def test_both_none_returns_1(self):
        """Both None → distance 1.0 (both invalid)."""
        assert actions_distance(None, None) == 1.0

    def test_one_none_returns_1(self):
        """One None and one valid action → distance 1.0."""
        a = {"velocity": 5.0}
        assert actions_distance(None, a) == 1.0
        assert actions_distance(a, None) == 1.0

    def test_non_dict_returns_1(self):
        """Non-dict inputs → distance 1.0."""
        a = {"velocity": 5.0}
        assert actions_distance("velocity=5", a) == 1.0
        assert actions_distance(a, 42) == 1.0
        assert actions_distance([1, 2, 3], a) == 1.0

    def test_max_opposite_actions_give_distance_1(self):
        """Actions at maximum opposite extremes should have distance 1.0."""
        a = {
            "velocity": 8.0,
            "turn_body": 10.0,
            "turn_gun": 20.0,
            "turn_radar": 45.0,
            "fire_power": 3.0,
        }
        b = {
            "velocity": -8.0,
            "turn_body": -10.0,
            "turn_gun": -20.0,
            "turn_radar": -45.0,
            "fire_power": 0.0,
        }
        assert actions_distance(a, b) == pytest.approx(1.0, abs=0.01)

    def test_small_difference_gives_low_distance(self):
        """Actions with small differences should have low distance."""
        a = {
            "velocity": 5.0,
            "turn_body": 3.0,
            "turn_gun": -10.0,
            "turn_radar": 20.0,
            "fire_power": 2.0,
        }
        b = {
            "velocity": 5.1,
            "turn_body": 3.1,
            "turn_gun": -10.1,
            "turn_radar": 20.1,
            "fire_power": 2.1,
        }
        assert actions_distance(a, b) < 0.05

    def test_distance_is_symmetric(self):
        """distance(a, b) == distance(b, a)."""
        a = {
            "velocity": 5.0,
            "turn_body": 3.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 1.0,
        }
        b = {
            "velocity": -3.0,
            "turn_body": -5.0,
            "turn_gun": 10.0,
            "turn_radar": -30.0,
            "fire_power": 0.0,
        }
        assert actions_distance(a, b) == pytest.approx(actions_distance(b, a))

    def test_distance_between_0_and_1(self):
        """Distance should always be in [0, 1]."""
        a = {
            "velocity": 8.0,
            "turn_body": 10.0,
            "turn_gun": 20.0,
            "turn_radar": 45.0,
            "fire_power": 3.0,
        }
        b = {
            "velocity": -8.0,
            "turn_body": -10.0,
            "turn_gun": -20.0,
            "turn_radar": -45.0,
            "fire_power": 0.0,
        }
        d = actions_distance(a, b)
        assert 0.0 <= d <= 1.0

    def test_only_fire_power_differs(self):
        """When only fire_power differs maximally (0 vs 3), distance should be 0.2."""
        a = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }
        b = {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 3.0,
        }
        # fire_power diff = 3/3 = 1.0, all others = 0.0
        # total = 1.0/5 = 0.2
        assert actions_distance(a, b) == pytest.approx(0.2, abs=0.01)


# =============================================================================
# Tests: extract_player_state
# =============================================================================


class TestExtractPlayerState:
    """Tests for extract_player_state() based on design doc spec."""

    def test_returns_none_for_unknown_player(self):
        """Should return None if player name not found in turn."""
        turns = _parse_inline_turns(TURN_A)
        result = extract_player_state(turns[0], "nonexistent_player")
        assert result is None

    def test_state_has_all_required_keys(self):
        """State dict should have all keys from the design doc."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")

        required_keys = [
            "tick",
            "my_x",
            "my_y",
            "my_heading",
            "my_gun_heading",
            "my_radar_heading",
            "my_energy",
            "my_velocity",
            "my_gun_heat",
            "arena_width",
            "arena_height",
            "enemy_x",
            "enemy_y",
            "enemy_heading",
            "enemy_energy",
            "enemy_velocity",
            "enemy_distance",
            "enemy_bearing",
        ]
        for key in required_keys:
            assert key in state, f"Missing key: {key}"

    def test_tick_matches_turn_number(self):
        """tick should match the turn number from XML."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        assert state["tick"] == 0

    def test_position_from_xml(self):
        """my_x, my_y should match robot's x, y from XML."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        assert state["my_x"] == 100.0
        assert state["my_y"] == 200.0

    def test_headings_converted_to_degrees(self):
        """Headings should be converted from radians (XML) to degrees (state)."""
        turns = _parse_inline_turns(TURN_B)
        state = extract_player_state(turns[0], "target")

        # bodyHeading=0.174533 rad ≈ 10.0 degrees
        assert state["my_heading"] == pytest.approx(10.0, abs=0.1)
        # gunHeading=0.349066 rad ≈ 20.0 degrees
        assert state["my_gun_heading"] == pytest.approx(20.0, abs=0.1)
        # radarHeading=0.785398 rad ≈ 45.0 degrees
        assert state["my_radar_heading"] == pytest.approx(45.0, abs=0.1)

    def test_energy_velocity_gun_heat(self):
        """Energy, velocity, gun_heat should come directly from XML."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        assert state["my_energy"] == 100.0
        assert state["my_velocity"] == 0.0
        assert state["my_gun_heat"] == 3.0

    def test_enemy_info_populated(self):
        """Enemy fields should be populated from the other robot."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        assert state["enemy_x"] == 600.0
        assert state["enemy_y"] == 400.0
        assert state["enemy_energy"] == 90.0
        assert state["enemy_velocity"] == 0.0

    def test_enemy_distance_computed(self):
        """enemy_distance should be Euclidean distance to enemy."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        expected_dist = math.sqrt((600 - 100) ** 2 + (400 - 200) ** 2)
        assert state["enemy_distance"] == pytest.approx(expected_dist, abs=0.1)

    def test_enemy_bearing_computed(self):
        """enemy_bearing should be angle from my heading to enemy in degrees."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        # bodyHeading=0.0, enemy at (600,400) from (100,200)
        # angle_to_enemy = atan2(200, 500) ≈ 0.3805 rad ≈ 21.8 degrees
        # bearing = angle_to_enemy - bodyHeading = 21.8 degrees
        assert isinstance(state["enemy_bearing"], float)

    def test_arena_dimensions_passed_through(self):
        """arena_width, arena_height should match the parameters."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(
            turns[0], "target", arena_width=1000, arena_height=750
        )
        assert state["arena_width"] == 1000
        assert state["arena_height"] == 750

    def test_default_arena_dimensions(self):
        """Default arena dimensions should be 800x600."""
        turns = _parse_inline_turns(TURN_A)
        state = extract_player_state(turns[0], "target")
        assert state["arena_width"] == 800
        assert state["arena_height"] == 600

    def test_dead_enemy_excluded(self):
        """DEAD enemies should not be included as the enemy."""
        dead_enemy_xml = """
        <turn round="0" turn="0" ver="1">
            <robots>
                <robot id="0" vsName="MyTank*" state="ACTIVE"
                       energy="100.0" x="100.0" y="200.0"
                       bodyHeading="0.0" gunHeading="0.0" radarHeading="0.0"
                       gunHeat="3.0" velocity="0.0"
                       teamName="target.MyTank*" name="target.MyTank*"/>
                <robot id="1" vsName="EnemyBot*" state="DEAD"
                       energy="0.0" x="600.0" y="400.0"
                       bodyHeading="0.0" gunHeading="0.0" radarHeading="0.0"
                       gunHeat="0.0" velocity="0.0"
                       teamName="opponent.EnemyBot*" name="opponent.EnemyBot*"/>
            </robots>
            <bullets/>
        </turn>
        """
        turns = _parse_inline_turns(dead_enemy_xml)
        state = extract_player_state(turns[0], "target")
        # No living enemies, so enemy fields should be default/zero
        assert state["enemy_distance"] == 0.0


# =============================================================================
# Tests: extract_player_action
# =============================================================================


class TestExtractPlayerAction:
    """Tests for extract_player_action() based on design doc spec."""

    def test_returns_dict_with_five_keys(self):
        """Action should have all 5 canonical keys."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "target")
        assert action is not None
        assert set(action.keys()) == set(ACTION_COMPONENTS)

    def test_velocity_from_next_turn(self):
        """velocity should come from the next turn's velocity field."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "target")
        # Next turn velocity = 8.0
        assert action["velocity"] == 8.0

    def test_turn_body_from_heading_delta(self):
        """turn_body should be bodyHeading delta in degrees."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "target")
        # bodyHeading: 0.0 → 0.174533 rad, delta ≈ 10.0 deg
        assert action["turn_body"] == pytest.approx(10.0, abs=0.1)

    def test_turn_gun_from_heading_delta(self):
        """turn_gun should be the total gunHeading delta in degrees."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "target")
        # gunHeading: 0.0 → 0.349066 rad, delta ≈ 20.0 deg
        assert action["turn_gun"] == pytest.approx(20.0, abs=0.1)

    def test_turn_radar_from_heading_delta(self):
        """turn_radar should be the total radarHeading delta in degrees."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "target")
        # radarHeading: 0.0 → 0.785398 rad, delta ≈ 45.0 deg
        assert action["turn_radar"] == pytest.approx(45.0, abs=0.1)

    def test_no_fire_gives_zero_fire_power(self):
        """No new bullets → fire_power = 0.0."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "target")
        assert action["fire_power"] == 0.0

    def test_fire_detected_from_new_bullet(self):
        """New bullet owned by player → fire_power = bullet's power."""
        turns = _parse_inline_turns(TURN_B + TURN_C_WITH_FIRE)
        action = extract_player_action(turns[0], turns[1], "target")
        # Bullet b0 with power=3.0 owned by robot 0 (target)
        assert action["fire_power"] == 3.0

    def test_fire_detected_from_ownerless_bullet_id_prefix(self):
        """Owner-less bullet ids like '0-123' should map to robot id 0."""
        turns = _parse_inline_turns(TURN_B + TURN_C_WITH_FIRE_ID_PREFIX_OWNER)
        action = extract_player_action(turns[0], turns[1], "target")
        assert action["fire_power"] == 2.0

    def test_unparseable_ownerless_bullet_id_is_ignored(self):
        """Owner-less bullets without parsable id prefix should not crash or mis-attribute."""
        turns = _parse_inline_turns(TURN_B + TURN_C_WITH_FIRE_UNPARSEABLE_ID)
        action = extract_player_action(turns[0], turns[1], "target")
        assert action["fire_power"] == 0.0

    def test_returns_none_for_unknown_player(self):
        """Should return None if player not found in turns."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "nonexistent")
        assert action is None

    def test_opponent_action_also_extracted(self):
        """Should work for the opponent player too."""
        turns = _parse_inline_turns(TURN_A + TURN_B)
        action = extract_player_action(turns[0], turns[1], "opponent")
        assert action is not None
        assert action["velocity"] == -8.0


# =============================================================================
# Tests: extract_state_action_pairs
# =============================================================================


class TestExtractStateActionPairs:
    """Tests for extract_state_action_pairs() based on design doc spec."""

    def test_returns_list_of_tuples(self, short_game_path):
        """Should return list of (state, action) tuples."""
        pairs = extract_state_action_pairs(short_game_path, "target")
        assert isinstance(pairs, list)
        assert len(pairs) > 0
        for state, action in pairs:
            assert isinstance(state, dict)
            assert isinstance(action, dict)

    def test_correct_number_of_pairs(self, short_game_path):
        """N consecutive turns in same round → N-1 pairs per round."""
        pairs = extract_state_action_pairs(short_game_path, "target")
        # Round 0: 4 turns → 3 pairs
        # Round 1: 2 turns → 1 pair
        # Total: 4 pairs
        assert len(pairs) == 4

    def test_pairs_not_across_round_boundary(self):
        """Pairs should NOT be generated across round boundaries."""
        xml_content = _make_xml_turns(TURN_A + TURN_B + TURN_ROUND1)
        tmp = _write_temp_xml(xml_content)
        try:
            pairs = extract_state_action_pairs(tmp, "target")
            # TURN_A (round 0) + TURN_B (round 0) → 1 pair
            # TURN_B (round 0) → TURN_ROUND1 (round 1) should NOT produce a pair
            assert len(pairs) == 1
        finally:
            tmp.unlink()

    def test_state_has_required_keys(self, short_game_path):
        """Each state in pairs should have all required keys."""
        pairs = extract_state_action_pairs(short_game_path, "target")
        state, _ = pairs[0]
        assert "tick" in state
        assert "my_x" in state
        assert "my_heading" in state
        assert "enemy_distance" in state

    def test_action_has_five_components(self, short_game_path):
        """Each action in pairs should have all 5 action components."""
        pairs = extract_state_action_pairs(short_game_path, "target")
        _, action = pairs[0]
        for key in ACTION_COMPONENTS:
            assert key in action

    def test_fire_event_detected_in_pairs(self, short_game_path):
        """Fire event at turn 2 should appear in pairs."""
        pairs = extract_state_action_pairs(short_game_path, "target")
        # The fire event happens between turn 1 and turn 2 in round 0
        # So the pair at index 1 (state at turn 1, action from turn 1→2) should have fire_power > 0
        fire_detected = any(action["fire_power"] > 0 for _, action in pairs)
        assert fire_detected, "Expected at least one pair with fire_power > 0"

    def test_empty_for_unknown_player(self, short_game_path):
        """Should return empty list for player not in the XML."""
        pairs = extract_state_action_pairs(short_game_path, "nonexistent_player")
        assert pairs == []

    def test_works_with_path_object(self, short_game_path):
        """Should accept Path objects."""
        pairs = extract_state_action_pairs(short_game_path, "target")
        assert len(pairs) > 0

    def test_works_with_string_path(self, short_game_path):
        """Should accept string paths."""
        pairs = extract_state_action_pairs(str(short_game_path), "target")
        assert len(pairs) > 0


# =============================================================================
# Tests: RoboCodeTraceParser
# =============================================================================


class TestRoboCodeTraceParser:
    """Tests for RoboCodeTraceParser based on design doc spec."""

    def test_parse_file_returns_game_trace(self, parser, short_game_path):
        """Parser should return a GameTrace object."""
        trace = parser.parse_file(short_game_path)
        assert isinstance(trace, GameTrace)

    def test_game_type_is_robocode(self, parser, short_game_path):
        """Game type should be 'RoboCode'."""
        trace = parser.parse_file(short_game_path)
        assert trace.game_type == "RoboCode"

    def test_extracts_players(self, parser, short_game_path):
        """Should extract player names from first turn's robots."""
        trace = parser.parse_file(short_game_path)
        player_names = [p["name"] for p in trace.metadata.players]
        assert "target" in player_names
        assert "opponent" in player_names

    def test_extracts_turns(self, parser, short_game_path):
        """Should extract all turns from XML."""
        trace = parser.parse_file(short_game_path)
        # 4 turns in round 0 + 2 turns in round 1 = 6 total
        assert len(trace.turns) == 6

    def test_extracts_winner(self, parser, short_game_path):
        """Should determine winner from final energy levels."""
        trace = parser.parse_file(short_game_path)
        # target has more energy at end
        assert trace.winner is not None
        assert trace.is_draw is False

    def test_handles_draw(self, parser, draw_game_path):
        """Should detect draw when both robots have equal energy."""
        trace = parser.parse_file(draw_game_path)
        assert trace.is_draw is True
        assert trace.winner is None

    def test_source_metadata_attached(self, parser, short_game_path):
        """Source metadata should be passed through."""
        source = {"tournament_id": "test-123", "round": 1}
        trace = parser.parse_file(short_game_path, source=source)
        assert trace.metadata.source["tournament_id"] == "test-123"

    def test_arena_dimensions_in_config(self, short_game_path):
        """Arena dimensions should be in metadata config."""
        parser = RoboCodeTraceParser(arena_width=1000, arena_height=750)
        trace = parser.parse_file(short_game_path)
        assert trace.metadata.config["width"] == 1000
        assert trace.metadata.config["height"] == 750

    def test_convenience_function(self, short_game_path):
        """parse_robocode_trace() convenience function should work."""
        trace = parse_robocode_trace(short_game_path)
        assert isinstance(trace, GameTrace)
        assert trace.game_type == "RoboCode"

    def test_empty_xml_raises_error(self, parser):
        """Parsing XML with no <turn> elements should raise ValueError."""
        tmp = _write_temp_xml(_make_xml_turns("<!-- no turns -->"))
        try:
            with pytest.raises(ValueError):
                parser.parse_file(tmp)
        finally:
            tmp.unlink()


# =============================================================================
# Tests: Parser Registry Integration
# =============================================================================


class TestParserRegistryIntegration:
    """Tests for RoboCode parser registration in __init__.py."""

    def test_robocode_in_trace_parsers(self):
        """RoboCode should be in the TRACE_PARSERS registry."""
        from revenge_bench.traces.parsers import TRACE_PARSERS

        assert "RoboCode" in TRACE_PARSERS

    def test_get_parser_returns_robocode(self):
        """get_parser('RoboCode') should return RoboCodeTraceParser."""
        from revenge_bench.traces.parsers import get_parser

        parser_class = get_parser("RoboCode")
        assert parser_class is RoboCodeTraceParser

    def test_registry_parser_can_parse(self, short_game_path):
        """Parser from registry should be able to parse files."""
        from revenge_bench.traces.parsers import get_parser

        parser_class = get_parser("RoboCode")
        parser = parser_class()
        trace = parser.parse_file(short_game_path)
        assert isinstance(trace, GameTrace)


# =============================================================================
# Tests: Collector Integration
# =============================================================================


class TestCollectorIntegration:
    """Tests for integration with TraceCollector."""

    def test_collector_recognizes_robocode(self):
        """TraceCollector should recognize RoboCode game type."""
        from revenge_bench.traces.collector import TraceCollector

        collector = TraceCollector(game_type="RoboCode")
        assert collector.parser_class.__name__ == "RoboCodeTraceParser"
