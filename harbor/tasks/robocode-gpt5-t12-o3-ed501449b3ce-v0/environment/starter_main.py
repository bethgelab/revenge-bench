"""Starter baseline for RoboCode strategy recovery.

This file is pre-seeded so evaluation works from Round 0.
Edit the move() function to match the target's behavior.
"""
import math


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _normalize_angle(deg):
    """Normalize angle to [-180, 180) degrees."""
    return (deg + 180) % 360 - 180


def _abs_bearing_to_enemy(state):
    """Compute absolute bearing (degrees, clockwise from North) from my pos to enemy."""
    dx = state["enemy_x"] - state["my_x"]
    dy = state["enemy_y"] - state["my_y"]
    return math.degrees(math.atan2(dx, dy)) % 360


def move(state):
    """Given the current game state, return a 5-component action dict.

    Key geometric relationships:
      abs_bearing    = atan2(enemy_x - my_x, enemy_y - my_y)  [clockwise from North]
      gun_offset     = normalize(abs_bearing - my_gun_heading)
      radar_offset   = normalize(abs_bearing - my_radar_heading)
      body_offset    = normalize(abs_bearing - my_heading) = enemy_bearing
    """
    distance = state.get("enemy_distance", 0.0)

    # If no enemy visible, stay still
    if distance <= 0:
        return {
            "velocity": 0.0,
            "turn_body": 0.0,
            "turn_gun": 0.0,
            "turn_radar": 0.0,
            "fire_power": 0.0,
        }

    abs_bearing = _abs_bearing_to_enemy(state)

    # Gun: turn toward enemy
    gun_offset = _normalize_angle(abs_bearing - state["my_gun_heading"])
    turn_gun = _clamp(gun_offset, -20.0, 20.0)

    # Radar: turn toward enemy (2x overshoot for radar lock)
    radar_offset = _normalize_angle(abs_bearing - state["my_radar_heading"])
    turn_radar = _clamp(2.0 * radar_offset, -45.0, 45.0)

    # Body: turn toward enemy
    body_offset = state["enemy_bearing"]  # already relative to heading
    turn_body = _clamp(body_offset, -10.0, 10.0)

    # Movement: approach enemy
    velocity = 8.0 if distance > 150 else -2.0

    # Firing: when gun is cool
    gun_heat = state.get("my_gun_heat", 1.0)
    if gun_heat <= 0:
        fire_power = 3.0 if distance < 200 else 2.0 if distance < 400 else 1.0
    else:
        fire_power = 0.0

    return {
        "velocity": _clamp(velocity, -8.0, 8.0),
        "turn_body": turn_body,
        "turn_gun": turn_gun,
        "turn_radar": turn_radar,
        "fire_power": _clamp(fire_power, 0.0, 3.0),
    }
