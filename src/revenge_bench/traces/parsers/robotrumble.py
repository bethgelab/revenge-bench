"""
RobotRumble Trace Parser

Converts RobotRumble's native JSON output format to our unified GameTrace format.

Also provides game-specific utility functions:
- normalize_action(): Convert any action format to canonical dict
- actions_equal(): Compare two actions for equality

================================================================================
CANONICAL ACTION FORMAT:
================================================================================
All actions are normalized to dict format:
    {"type": "Move"|"Attack", "direction": "North"|"South"|"East"|"West"}
    
Or None for errors/no-ops.

Input formats handled by normalize_action():
- {"type": "Move", "direction": "North"} -> same
- {"Ok": {"type": "Move", "direction": "North"}} -> unwrapped
- {"Err": {...}} -> None
- "Move:North" (string from trace) -> {"type": "Move", "direction": "North"}
- ("Move", "North") (tuple) -> {"type": "Move", "direction": "North"}
- None -> None

================================================================================
RAW FIELDS (from game engine output):
================================================================================
File format: Single JSON file
Command: `rumblebot run term --raw`

Top-level:
    - winner: str|null          "Red"|"Blue"|null (null means tie)
    - errors: dict              Runtime errors by team (usually empty)
    - turns: list               List of turn records

Turn record:
    - state.turn: int           Turn number (1-indexed)
    - state.objs: dict          All game objects keyed by ID
        For Terrain (walls):
            - id: str           Object ID
            - coords: [x, y]    Position
            - obj_type: str     "Terrain"
            - type: str         "Wall"
        For Units (robots):
            - id: str           Unit ID
            - coords: [x, y]    Position
            - obj_type: str     "Unit"
            - type: str         "Soldier"
            - team: str         "Red"|"Blue"
            - health: int       Remaining health (typically 1-5)

    - robot_actions: dict       Actions keyed by unit ID
        Success: {"Ok": {"type": "Move"|"Attack", "direction": "North"|"South"|"East"|"West"}}
        Success (no-op): {"Ok": null}
        Error: {"Err": {"RuntimeError": {"summary": str, "details": str, "loc": null}}}

    - logs: dict                Debug logs per team {"Red": [], "Blue": []}
    - debug_inspect_tables: dict  Debug info (usually empty)
    - debug_locate_queries: dict  Debug queries per team

================================================================================
INFERRED/COMPUTED FIELDS (by parser):
================================================================================
    - action: dict              Formatted as {"unit_id": str, "action": str}
                                action string formats:
                                - "Move:North", "Move:South", "Move:East", "Move:West"
                                - "Attack:North", "Attack:South", "Attack:East", "Attack:West"
                                - "wait" (for null Ok actions)
                                - "error:<summary>" (for Err actions)
                                NOT INFERRED - directly from robot_actions

    - player_names: dict        Maps team to player name (optional, from constructor)
                                Default: {"Blue": "Blue", "Red": "Red"}

    - board_size: (w, h)        INFERRED from wall positions (max coords + 1)

    - initial_units_*: int      COUNTED from first turn's state.objs

    - player_states: dict       Per-player view built from state.objs
                                - team: str
                                - my_units: list of own team's units
                                - enemy_units: list of opponent's units
                                - all_objs: full state.objs

    - metadata.game_id: str     From source param or default "robotrumble-game"
    - metadata.timestamp: datetime  Current time (RobotRumble doesn't include timestamp)
    
    - results[].outcome: GameOutcome  WIN/LOSS/DRAW computed from winner

Key differences from BattleSnake:
    - Single JSON file (not JSONL)
    - Actions are EXPLICITLY recorded per unit (not inferred from positions)
    - Two teams (Red, Blue) with multiple units, not named individual players
    - Units can die mid-game, player actions are per-unit not per-player
================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from revenge_bench.traces.models import (
    GameMetadata,
    GameOutcome,
    GameTrace,
    PlayerAction,
    PlayerResult,
    TurnRecord,
)

# =============================================================================
# Constants
# =============================================================================

VALID_DIRECTIONS = ["North", "South", "East", "West"]
VALID_ACTION_TYPES = ["Move", "Attack"]
TEAMS = ["Blue", "Red"]


# =============================================================================
# Action Normalization & Comparison
# =============================================================================


def normalize_action(action: Any) -> dict | None:
    """
    Normalize RobotRumble action to canonical dict format.

    Canonical format: {"type": "Move"|"Attack", "direction": "North"|"South"|"East"|"West"}

    Input formats:
        - {"type": "Move", "direction": "North"} -> same
        - {"Ok": {"type": "Move", "direction": "North"}} -> unwrapped
        - {"Err": {...}} -> None (error)
        - {"Ok": null} -> None (no-op)
        - "Move:North" (string from trace) -> {"type": "Move", "direction": "North"}
        - ("Move", "North") (tuple) -> {"type": "Move", "direction": "North"}
        - None -> None

    Returns:
        Dict with type and direction, or None for errors/no-ops/invalid.
    """
    if action is None:
        return None

    # Handle {"Ok": {...}} wrapper from traces
    if isinstance(action, dict) and "Ok" in action:
        action = action["Ok"]
        if action is None:
            return None  # {"Ok": null} = no-op

    # Handle {"Err": ...} - robot had error
    if isinstance(action, dict) and "Err" in action:
        return None

    # Standard dict format
    if isinstance(action, dict) and "type" in action:
        action_type = action.get("type", "")
        direction = action.get("direction", "")
        if action_type in VALID_ACTION_TYPES and direction in VALID_DIRECTIONS:
            return {"type": action_type, "direction": direction}
        return None

    # String format "Move:North" or "Move North"
    if isinstance(action, str):
        # Handle "Move:North" format
        if ":" in action:
            parts = action.split(":")
        else:
            parts = action.split()

        if len(parts) == 2:
            action_type, direction = parts
            if action_type in VALID_ACTION_TYPES and direction in VALID_DIRECTIONS:
                return {"type": action_type, "direction": direction}

    # Tuple format ("Move", "North")
    if isinstance(action, (tuple, list)) and len(action) == 2:
        action_type, direction = action
        if action_type in VALID_ACTION_TYPES and direction in VALID_DIRECTIONS:
            return {"type": action_type, "direction": direction}

    return None


def actions_equal(a1: Any, a2: Any) -> bool:
    """
    Compare two RobotRumble actions for equality.

    Both actions are normalized before comparison.

    Examples:
        actions_equal({"type": "Move", "direction": "North"},
                      {"type": "Move", "direction": "North"}) -> True
        actions_equal({"Ok": {"type": "Move", "direction": "North"}},
                      {"type": "Move", "direction": "North"}) -> True
        actions_equal("Move:North", {"type": "Move", "direction": "North"}) -> True
        actions_equal(None, None) -> True (both errors)
        actions_equal(None, {"type": "Move", "direction": "North"}) -> False
    """
    n1 = normalize_action(a1)
    n2 = normalize_action(a2)

    # Both None = equal (both errored/no-op)
    if n1 is None and n2 is None:
        return True

    # One None = not equal
    if n1 is None or n2 is None:
        return False

    return n1["type"] == n2["type"] and n1["direction"] == n2["direction"]


def _single_action_distance(a1: Any, a2: Any) -> float:
    """
    Compute distance between two single RobotRumble actions.

    Scoring:
    - Both None → 0.0 (both errored/no-op)
    - One None, one not → 1.0
    - Same type + same direction → 0.0 (perfect match)
    - Same type + different direction → 0.5 (right behavior, wrong direction)
    - Different type → 1.0 (completely wrong, e.g. Attack vs Move)

    Args:
        a1: First action (any format accepted by normalize_action)
        a2: Second action (any format accepted by normalize_action)

    Returns:
        Float between 0.0 and 1.0.
    """
    n1 = normalize_action(a1)
    n2 = normalize_action(a2)

    if n1 is None and n2 is None:
        return 0.0
    if n1 is None or n2 is None:
        return 1.0
    if n1["type"] == n2["type"] and n1["direction"] == n2["direction"]:
        return 0.0
    if n1["type"] == n2["type"]:
        return 0.5  # right behavior, wrong direction
    return 1.0


def actions_distance(a1: Any, a2: Any) -> float:
    """
    Compute distance between two RobotRumble actions.

    Handles both single actions and multi-unit action lists.

    For single actions (dict, str, tuple, None): delegates to _single_action_distance.

    For multi-unit lists (list[{"unit_id": str, "action": ...}]):
    - Builds unit_id → action maps from both lists
    - Computes _single_action_distance per unit
    - Missing unit_id in one list → 1.0 penalty
    - Returns average across all units (0.0 to 1.0)

    Args:
        a1: First action(s) — single action or list of per-unit action dicts
        a2: Second action(s) — single action or list of per-unit action dicts

    Returns:
        Float between 0.0 and 1.0.
    """
    # Both lists → multi-unit comparison
    if isinstance(a1, list) and isinstance(a2, list):
        map1 = {
            entry["unit_id"]: entry.get("action")
            for entry in a1
            if isinstance(entry, dict) and "unit_id" in entry
        }
        map2 = {
            entry["unit_id"]: entry.get("action")
            for entry in a2
            if isinstance(entry, dict) and "unit_id" in entry
        }

        all_ids = set(map1.keys()) | set(map2.keys())
        if not all_ids:
            return 0.0

        total = sum(
            _single_action_distance(map1.get(uid), map2.get(uid)) for uid in all_ids
        )
        return total / len(all_ids)

    # Fallback: single-action comparison
    return _single_action_distance(a1, a2)


def compute_state_distance(s1: dict, s2: dict, team: str = "Blue") -> float:
    """
    Compute distance between two RobotRumble states.

    Uses average Manhattan distance for all units of the specified team.

    Args:
        s1: First state (with "objs" dict of units)
        s2: Second state (with "objs" dict of units)
        team: Which team to compare ("Blue" or "Red")

    Returns:
        Average Manhattan distance across all team units.
        Units that died get a penalty of 10.
    """
    objs1 = s1.get("objs", {})
    objs2 = s2.get("objs", {})

    total_distance = 0
    units_compared = 0

    for unit_id, obj1 in objs1.items():
        # Skip terrain
        if obj1.get("obj_type") == "Terrain":
            continue
        # Skip other team
        if obj1.get("team") != team:
            continue

        if unit_id not in objs2:
            # Unit died or doesn't exist - penalize
            total_distance += 10
            units_compared += 1
            continue

        obj2 = objs2[unit_id]
        coords1 = obj1.get("coords", [0, 0])
        coords2 = obj2.get("coords", [0, 0])

        dist = abs(coords1[0] - coords2[0]) + abs(coords1[1] - coords2[1])
        total_distance += dist
        units_compared += 1

    return total_distance / max(units_compared, 1)


# =============================================================================
# Inverse Strategy: State-Action Extraction
# =============================================================================


def extract_player_state(turn_data: dict, player_name: str) -> dict | None:
    """
    Extract a player's view of the game state from a turn record.

    Constructs the game_state dict that would be passed to a player's move() function,
    with units separated into "my_units" and "enemy_units" based on the player's team.

    Args:
        turn_data: Raw turn data from the trace (one entry from "turns" list)
        player_name: Team name ("Blue" or "Red") or custom player name

    Returns:
        Game state dict from the player's perspective, or None if team not found.
    """
    state_data = turn_data.get("state", {})
    objs = state_data.get("objs", {})
    turn_num = state_data.get("turn", 0)

    # Determine team: player_name can be "Blue"/"Red" directly
    team = player_name if player_name in TEAMS else None
    if team is None:
        return None

    enemy_team = "Red" if team == "Blue" else "Blue"

    # Separate units by team
    my_units = []
    enemy_units = []
    walls = []
    for obj in objs.values():
        if obj.get("obj_type") == "Unit":
            if obj.get("team") == team:
                my_units.append(obj)
            elif obj.get("team") == enemy_team:
                enemy_units.append(obj)
        elif obj.get("obj_type") == "Terrain":
            walls.append(obj)

    return {
        "turn": turn_num,
        "team": team,
        "my_units": my_units,
        "enemy_units": enemy_units,
        "walls": walls,
        "all_objs": objs,
    }


def extract_player_action(turn_data: dict, player_name: str) -> list[dict] | None:
    """
    Extract a player's actions from a turn record.

    Returns a list of per-unit action dicts, sorted by unit ID for deterministic
    comparison. Each dict contains the unit_id and the normalized action.

    Args:
        turn_data: Raw turn data from the trace
        player_name: Team name ("Blue" or "Red")

    Returns:
        Sorted list of {"unit_id": str, "action": dict|None} dicts,
        or None if team not found.
    """
    state_data = turn_data.get("state", {})
    objs = state_data.get("objs", {})
    robot_actions = turn_data.get("robot_actions", {})

    team = player_name if player_name in TEAMS else None
    if team is None:
        return None

    actions = []
    for unit_id, action_result in robot_actions.items():
        obj = objs.get(unit_id, {})
        if obj.get("obj_type") != "Unit":
            continue
        if obj.get("team") != team:
            continue

        normalized = normalize_action(action_result)
        actions.append({"unit_id": unit_id, "action": normalized})

    # Sort by unit_id for deterministic ordering
    return sorted(actions, key=lambda a: a["unit_id"])


def extract_state_action_pairs(
    sim_file: Path | str, player_name: str
) -> list[tuple[dict, list[dict]]]:
    """
    Extract all (state, action) pairs for a player from a RobotRumble trace file.

    This is the main function for offline evaluation - it reads a sim file and
    returns all the states the player saw and the actions they took.

    RobotRumble has multi-unit actions: each turn's action is a list of
    per-unit action dicts sorted by unit_id.

    Args:
        sim_file: Path to sim_*.json file
        player_name: Team name ("Blue" or "Red")

    Returns:
        List of (state, actions) tuples where:
        - state: The game_state dict from the player's perspective
        - actions: Sorted list of {"unit_id": str, "action": dict|None} dicts
    """
    sim_file = Path(sim_file)
    with open(sim_file, encoding="utf-8") as f:
        data = json.load(f)

    turns = data.get("turns", [])
    if not turns:
        return []

    pairs = []
    for turn_data in turns:
        state = extract_player_state(turn_data, player_name)
        if state is None:
            continue

        actions = extract_player_action(turn_data, player_name)
        if actions is None or len(actions) == 0:
            continue

        # Skip turns where ALL actions are None (e.g. the final turn where
        # the engine records {"Ok": null} for every unit because the game
        # ended before actions were executed).
        if all(a.get("action") is None for a in actions):
            continue

        pairs.append((state, actions))

    return pairs


def build_probe_trace_payload(
    simulations: list[tuple[str, dict]],
    probe_id: int,
    *,
    probe_team: str = "Blue",
    target_team: str = "Red",
) -> dict[str, Any]:
    """Build the interventionist probe trace payload from raw simulations.

    This mirrors ``InverseStrategyInterventionist._parse_robotrumble_probe_traces``:
    the probe bot is Blue, the target is Red, and each pair records both actions
    plus the target-observed state.
    """
    all_pairs: list[dict[str, Any]] = []
    per_simulation: list[dict[str, Any]] = []

    for sim_name, data in simulations:
        turns = data.get("turns", [])
        sim_pairs = []

        for turn_data in turns:
            turn_num = turn_data.get("turn", 0)

            target_state = extract_player_state(turn_data, target_team)
            probe_state = extract_player_state(turn_data, probe_team)
            if target_state is None or probe_state is None:
                continue

            target_action = extract_player_action(turn_data, target_team)
            probe_action = extract_player_action(turn_data, probe_team)
            if target_action is None or probe_action is None:
                continue

            distance = actions_distance(probe_action, target_action)
            pair = {
                "turn": turn_num,
                "probe_action": probe_action,
                "target_action": target_action,
                "distance": distance,
                "target_state": target_state,
            }
            sim_pairs.append(pair)
            all_pairs.append(pair)

        per_simulation.append(
            {
                "file": Path(sim_name).name,
                "num_turns": len(sim_pairs),
            }
        )

    return {
        "probe_id": probe_id,
        "description": "probe (Blue) vs target (Red) - showing what each did in same state",
        "total_turns": len(all_pairs),
        "num_simulations": len(per_simulation),
        "per_simulation": per_simulation,
        "pairs": all_pairs,
    }


# =============================================================================
# Trace Parser
# =============================================================================


class RobotRumbleTraceParser:
    """
    Parser for RobotRumble's native JSON output format.

    Usage:
        parser = RobotRumbleTraceParser()
        trace = parser.parse_file("game_output.json")

        # Or parse from raw JSON content
        trace = parser.parse_content(json_content)
    """

    GAME_TYPE = "RobotRumble"

    def __init__(self, player_names: dict[str, str] | None = None):
        """
        Initialize the parser.

        Args:
            player_names: Optional mapping of team names to player names.
                         e.g., {"Blue": "gemini-2.5-pro", "Red": "gpt5-mini"}
                         If not provided, teams are used as player names.
        """
        self.player_names = player_names or {}

    def parse_file(self, path: str | Path, source: dict | None = None) -> GameTrace:
        """
        Parse a RobotRumble JSON output file.

        Args:
            path: Path to the JSON file
            source: Optional source metadata (tournament_id, etc.)

        Returns:
            GameTrace object
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return self.parse_content(content, source=source)

    def parse_content(self, content: str, source: dict | None = None) -> GameTrace:
        """
        Parse JSON content from RobotRumble.

        Args:
            content: JSON content as a string
            source: Optional source metadata

        Returns:
            GameTrace object
        """
        data = json.loads(content)
        return self._parse_data(data, source)

    def parse_data(self, data: dict, source: dict | None = None) -> GameTrace:
        """
        Parse a RobotRumble data dictionary directly.

        Args:
            data: Parsed JSON data
            source: Optional source metadata

        Returns:
            GameTrace object
        """
        return self._parse_data(data, source)

    def _parse_data(self, data: dict, source: dict | None = None) -> GameTrace:
        """Internal parsing logic."""

        # Extract results
        winner_team = data.get("winner")  # "Red", "Blue", or null
        is_draw = winner_team is None
        winner_name = self._get_player_name(winner_team) if winner_team else None

        # Get turns
        turn_records = data.get("turns", [])
        if not turn_records:
            raise ValueError("No turns found in RobotRumble data")

        # Extract game info from first turn
        first_turn = turn_records[0]
        first_state = first_turn.get("state", {})

        # Determine board size from wall positions
        board_width, board_height = self._infer_board_size(first_state.get("objs", {}))

        # Get initial unit counts per team
        initial_units = self._get_units_by_team(first_state.get("objs", {}))

        # Build player list
        players = [
            {"id": "Blue", "name": self._get_player_name("Blue")},
            {"id": "Red", "name": self._get_player_name("Red")},
        ]

        # Generate a game ID (RobotRumble doesn't include one)
        game_id = (
            source.get("game_id", "robotrumble-game") if source else "robotrumble-game"
        )

        metadata = GameMetadata(
            game_id=game_id,
            game_type=self.GAME_TYPE,
            timestamp=datetime.now(),
            players=players,
            config={
                "width": board_width,
                "height": board_height,
                "initial_units_blue": len(initial_units.get("Blue", [])),
                "initial_units_red": len(initial_units.get("Red", [])),
            },
            source=source or {},
        )

        # Parse turns
        turns = []
        for turn_data in turn_records:
            turn_record = self._parse_turn(turn_data)
            turns.append(turn_record)

        # Build results
        results = []
        for team in TEAMS:
            player_name = self._get_player_name(team)
            if team == winner_team:
                outcome = GameOutcome.WIN
            elif is_draw:
                outcome = GameOutcome.DRAW
            else:
                outcome = GameOutcome.LOSS

            results.append(
                PlayerResult(
                    player_id=team,
                    player_name=player_name,
                    outcome=outcome,
                )
            )

        return GameTrace(
            metadata=metadata,
            turns=turns,
            results=results,
            winner=winner_name,
            is_draw=is_draw,
        )

    def _parse_turn(self, turn_data: dict) -> TurnRecord:
        """Parse a single turn record."""
        state_data = turn_data.get("state", {})
        turn_num = state_data.get("turn", 0)
        robot_actions = turn_data.get("robot_actions", {})

        # Get units by team for this turn
        units_by_team = self._get_units_by_team(state_data.get("objs", {}))

        # Build state
        state = {
            "turn": turn_num,
            "objs": state_data.get("objs", {}),
            "units": {
                "Blue": units_by_team.get("Blue", []),
                "Red": units_by_team.get("Red", []),
            },
        }

        # Build player-specific states (each team's view)
        player_states = {}
        for team in TEAMS:
            player_name = self._get_player_name(team)
            team_units = units_by_team.get(team, [])
            enemy_team = "Red" if team == "Blue" else "Blue"
            enemy_units = units_by_team.get(enemy_team, [])

            player_states[player_name] = {
                "turn": turn_num,
                "team": team,
                "my_units": team_units,
                "enemy_units": enemy_units,
                "all_objs": state_data.get("objs", {}),
            }

        # Parse actions
        actions = []
        for unit_id, action_result in robot_actions.items():
            # Skip terrain/wall objects
            obj = state_data.get("objs", {}).get(unit_id, {})
            if obj.get("obj_type") != "Unit":
                continue

            team = obj.get("team")
            if not team:
                continue

            player_name = self._get_player_name(team)

            # Parse action
            if "Ok" in action_result:
                action_data = action_result["Ok"]
                if action_data is None:
                    # Null action (no-op)
                    action_str = "wait"
                else:
                    action_type = action_data.get("type", "")
                    direction = action_data.get("direction", "")
                    action_str = (
                        f"{action_type}:{direction}" if direction else action_type
                    )
            elif "Err" in action_result:
                # Error action
                error = action_result["Err"]
                action_str = (
                    f"error:{error.get('RuntimeError', {}).get('summary', 'unknown')}"
                )
            else:
                action_str = "unknown"

            actions.append(
                PlayerAction(
                    player_id=team,
                    player_name=player_name,
                    turn=turn_num,
                    action={"unit_id": unit_id, "action": action_str},
                    action_type="unit_action",
                    valid_actions=self._get_valid_actions(),
                )
            )

        return TurnRecord(
            turn=turn_num,
            state=state,
            actions=actions,
            player_states=player_states,
        )

    def _get_player_name(self, team: str) -> str:
        """Get player name for a team."""
        return self.player_names.get(team, team)

    def _get_units_by_team(self, objs: dict) -> dict[str, list[dict]]:
        """Extract units grouped by team."""
        units = {"Blue": [], "Red": []}
        for obj in objs.values():
            if obj.get("obj_type") == "Unit":
                team = obj.get("team")
                if team in units:
                    units[team].append(obj)
        return units

    def _infer_board_size(self, objs: dict) -> tuple[int, int]:
        """Infer board size from wall positions."""
        max_x = 0
        max_y = 0
        for obj in objs.values():
            if obj.get("obj_type") == "Terrain":
                coords = obj.get("coords", [0, 0])
                max_x = max(max_x, coords[0])
                max_y = max(max_y, coords[1])
        return max_x + 1, max_y + 1

    def _get_valid_actions(self) -> list[str]:
        """Get list of valid action strings."""
        actions = ["wait"]
        for action_type in VALID_ACTION_TYPES:
            for direction in VALID_DIRECTIONS:
                actions.append(f"{action_type}:{direction}")
        return actions


def parse_robotrumble_trace(path: str | Path, **kwargs) -> GameTrace:
    """Convenience function to parse a RobotRumble trace file."""
    return RobotRumbleTraceParser(**kwargs).parse_file(path)
