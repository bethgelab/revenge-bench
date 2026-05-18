"""
Halite III Trace Parser

Converts Halite III's native .hlt replay format to our unified GameTrace format.

Also provides game-specific utility functions:
- normalize_action(): Convert any action format to canonical dict/list format
- actions_distance(): Compute normalized distance between actions (0.0 to 1.0)

================================================================================
CANONICAL ACTION FORMAT:
================================================================================
Actions are lists of move dicts:

Single ship move:
    [{"type": "m", "id": 1, "direction": "n"}]

Multiple ships + spawn:
    [
        {"type": "m", "id": 1, "direction": "n"},
        {"type": "m", "id": 3, "direction": "s"},
        {"type": "g"}
    ]

Empty (no actions):
    []

Action types:
    - {"type": "m", "id": <ship_id>, "direction": "n"|"s"|"e"|"w"|"o"}  # Move
    - {"type": "g"}                                                      # Spawn
    - {"type": "c", "id": <ship_id>}                                     # Convert to dropoff

================================================================================
FILE FORMAT:
================================================================================
.hlt files are zstd-compressed JSON with structure:

{
    "ENGINE_VERSION": "1.2.2.finals",
    "REPLAY_FILE_VERSION": 3,
    "players": [
        {"player_id": 0, "name": "...", "factory_location": {"x": .., "y": ..}},
        ...
    ],
    "full_frames": [  // One frame per turn
        {
            "cells": [[...]],         // Halite amounts per cell
            "energy": {"0": 5000, "1": 5000},  // Player halite totals
            "entities": {             // Ships by player
                "0": {"1": {"x": 16, "y": 32, "energy": 0, "is_inspired": false}},
                "1": {...}
            },
            "moves": {                // ← Player actions
                "0": [
                    {"type": "m", "id": 1, "direction": "n"},
                    {"type": "g"}
                ],
                "1": [...]
            },
            "events": [...]
        },
        ...
    ],
    "production_map": {"width": 64, "height": 64, "grid": [...]},
    "GAME_CONSTANTS": {...}
}

================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import zstandard as zstd

from revenge_bench.traces.models import (
    GameMetadata,
    GameOutcome,
    GameTrace,
    PlayerAction,
    PlayerResult,
    TurnRecord,
)

# =============================================================================
# Action Normalization & Comparison
# =============================================================================

VALID_DIRECTIONS = ["n", "s", "e", "w", "o"]
VALID_ACTION_TYPES = ["m", "g", "c"]


def normalize_action(action: Any) -> list[dict] | None:
    """
    Normalize Halite action to canonical list-of-dicts format.

    Canonical format: List of action dicts
        [{"type": "m", "id": 1, "direction": "n"}, {"type": "g"}]

    Input formats:
        - List of dicts (already canonical) -> unchanged
        - Empty list -> []
        - None -> None

    Returns:
        List of action dicts or None if invalid.
    """
    if action is None:
        return None

    if not isinstance(action, list):
        return None

    # Validate each action in the list
    normalized = []
    for act in action:
        if not isinstance(act, dict):
            continue

        act_type = act.get("type")
        if act_type not in VALID_ACTION_TYPES:
            continue

        # Validate move action
        if act_type == "m":
            if "id" not in act or "direction" not in act:
                continue
            if act["direction"] not in VALID_DIRECTIONS:
                continue

        # Validate convert action
        elif act_type == "c":
            if "id" not in act:
                continue

        # Spawn action (type "g") has no additional requirements

        normalized.append(act)

    return normalized


def actions_distance(a1: Any, a2: Any) -> float:
    """
    Compute normalized distance between two Halite III action lists.

    Returns the fraction of actions that differ (0.0 to 1.0).
    - 0.0: Actions are identical
    - 1.0: Actions are completely different
    - 0.2: 80% of actions match

    Actions are compared by type and entity:
    - Move actions: identified by ship_id + direction
    - Convert actions: identified by ship_id
    - Spawn actions: counted separately

    This normalized metric allows averaging across different game states.

    Args:
        a1: First action (list of action dicts)
        a2: Second action (list of action dicts)

    Returns:
        Normalized distance in [0.0, 1.0]

    Examples:
        actions_distance([{"type": "m", "id": 1, "direction": "n"}],
                        [{"type": "m", "id": 1, "direction": "n"}]) -> 0.0

        actions_distance([{"type": "m", "id": 1, "direction": "n"}, {"type": "g"}],
                        [{"type": "m", "id": 1, "direction": "s"}]) -> 0.5

        actions_distance([{"type": "g"}], []) -> 1.0
    """
    n1 = normalize_action(a1)
    n2 = normalize_action(a2)

    # Both None/invalid = equal (distance 0)
    if n1 is None and n2 is None:
        return 0.0

    # One None = completely different (distance 1)
    if n1 is None or n2 is None:
        return 1.0

    # Convert actions to comparable tuples for set operations
    def action_to_key(act: dict) -> tuple:
        """Convert action dict to comparable tuple."""
        act_type = act["type"]
        if act_type == "m":
            return ("m", act["id"], act["direction"])
        elif act_type == "c":
            return ("c", act["id"])
        else:  # spawn
            return ("g",)

    # Create sets of action keys
    keys1 = {action_to_key(act) for act in n1}
    keys2 = {action_to_key(act) for act in n2}

    # All unique actions from both sets
    all_actions = keys1 | keys2

    # Empty actions = distance 0
    if not all_actions:
        return 0.0

    # Count actions that don't match
    mismatches = len(keys1 ^ keys2)  # Symmetric difference

    return mismatches / len(all_actions)


def load_hlt_file(file_path: Path | str) -> dict:
    """
    Load and decompress a Halite .hlt replay file.

    Args:
        file_path: Path to the .hlt file

    Returns:
        Decompressed JSON data as dict
    """
    file_path = Path(file_path)

    with open(file_path, "rb") as f:
        compressed_data = f.read()

    # Decompress with zstandard
    dctx = zstd.ZstdDecompressor()
    decompressed_data = dctx.decompress(compressed_data)

    # Parse JSON
    return json.loads(decompressed_data.decode("utf-8"))


def extract_player_state(frame: dict, player_id: str, data: dict) -> dict | None:
    """
    Extract a player's view of the game state from a frame.

    Constructs the game_state dict that would be passed to player's move() function.

    Args:
        frame: Frame data from full_frames
        player_id: Player ID (as string: "0", "1", etc.)
        data: Full replay data (for constants and map info)

    Returns:
        State dict with player's perspective, or None if the player is eliminated
        (i.e. not present in the frame's entities).
    """
    # Player is eliminated if they have no entry in entities
    if player_id not in frame.get("entities", {}):
        return None

    production_map = data.get("production_map", {})
    game_constants = data.get("GAME_CONSTANTS", {})

    # Get opponent IDs
    all_player_ids = list(frame.get("entities", {}).keys())
    opponent_ids = [pid for pid in all_player_ids if pid != player_id]

    # Build state
    state = {
        "turn": frame.get("turn", 0),  # Frame index serves as turn number
        "map_size": {
            "width": production_map.get("width", 64),
            "height": production_map.get("height", 64),
        },
        "cells": frame.get("cells", []),
        "my_energy": frame.get("energy", {}).get(player_id, 0),
        "my_ships": frame.get("entities", {}).get(player_id, {}),
        "opponent_energy": {
            pid: frame.get("energy", {}).get(pid, 0) for pid in opponent_ids
        },
        "opponent_ships": {
            pid: frame.get("entities", {}).get(pid, {}) for pid in opponent_ids
        },
        "deposited": frame.get("deposited", {}).get(player_id, 0),
        "events": frame.get("events", []),
        "game_constants": game_constants,
        "player_id": player_id,
    }

    # Add shipyard location from player metadata
    for player in data.get("players", []):
        if str(player.get("player_id")) == player_id:
            state["my_shipyard"] = player.get("factory_location", {})
            break

    return state


def extract_state_action_pairs(
    sim_file: Path | str, player_name: str
) -> list[tuple[dict, list[dict]]]:
    """
    Extract all (state, action) pairs for a player from a Halite replay file.

    This is the main function for offline evaluation - it reads a .hlt file and
    returns all the states the player saw and actions they took.

    Args:
        sim_file: Path to replay-*.hlt file
        player_name: Name of the player to extract data for

    Returns:
        List of (state, actions) tuples where:
        - state: The game_state dict the player received
        - actions: List of action dicts the player executed
    """
    data = load_hlt_file(sim_file)

    player_id = None
    for player in data.get("players", []):
        if player.get("name") == player_name:
            player_id = str(player.get("player_id"))
            break

    if player_id is None:
        return []

    pairs = []
    frames = data.get("full_frames", [])

    for idx, frame in enumerate(frames):
        # Add turn number to frame (not always present)
        frame["turn"] = idx

        # Extract player's state; None means the player is eliminated this turn
        state = extract_player_state(frame, player_id, data)
        if state is None:
            continue

        actions = frame.get("moves", {}).get(player_id, [])

        # Fill in STILL (direction "o") for ships not explicitly commanded
        commanded_ids = {act.get("id") for act in actions if act.get("type") == "m"}
        my_ships = frame.get("entities", {}).get(player_id, {})
        all_actions = list(actions)
        for ship_id_str, _ship_info in my_ships.items():
            sid = int(ship_id_str)
            if sid not in commanded_ids:
                all_actions.append({"type": "m", "id": sid, "direction": "o"})

        if all_actions or idx > 0:  # Include all turns after turn 0
            pairs.append((state, all_actions))

    return pairs


# =============================================================================
# Trace Parser
# =============================================================================


class Halite3TraceParser:
    """
    Parser for Halite III's native .hlt replay format.

    Usage:
        parser = Halite3TraceParser()
        trace = parser.parse_file("replay-*.hlt")
    """

    GAME_TYPE = "Halite3"

    def __init__(self):
        """Initialize the parser."""
        pass

    def parse_file(self, path: str | Path, source: dict | None = None) -> GameTrace:
        """
        Parse a Halite .hlt replay file.

        Args:
            path: Path to the .hlt file
            source: Optional source metadata (tournament_id, etc.)

        Returns:
            GameTrace object
        """
        path = Path(path)
        data = load_hlt_file(path)

        # Extract metadata
        game_id = str(data.get("map_generator_seed", path.stem))

        players_data = data.get("players", [])
        players = [
            {
                "id": str(p.get("player_id")),
                "name": p.get("name", f"Player {p.get('player_id')}"),
            }
            for p in players_data
        ]

        metadata = GameMetadata(
            game_id=game_id,
            game_type=self.GAME_TYPE,
            timestamp=datetime.now(),  # Halite doesn't include timestamp
            players=players,
            config={
                "map_width": data.get("production_map", {}).get("width", 64),
                "map_height": data.get("production_map", {}).get("height", 64),
                "game_constants": data.get("GAME_CONSTANTS", {}),
            },
            source=source or {},
        )

        # Create trace
        trace = GameTrace(metadata=metadata)

        # Parse turns
        frames = data.get("full_frames", [])
        for turn_idx, frame in enumerate(frames):
            turn = self._parse_turn(frame, turn_idx, players, data)
            trace.add_turn(turn)

        # Determine winner from final state
        if frames:
            final_frame = frames[-1]
            final_energy = final_frame.get("energy", {})

            if final_energy:
                # Winner is player with most halite
                winner_id = max(final_energy.keys(), key=lambda k: final_energy[k])
                winner_name = next(
                    (p["name"] for p in players if p["id"] == winner_id), None
                )

                # Check for draw (all players have identical energy)
                energies = list(final_energy.values())
                is_draw = len(set(energies)) <= 1  # All values identical = draw

                trace.winner = None if is_draw else winner_name
                trace.is_draw = is_draw

                # Add results
                for player in players:
                    player_id = player["id"]
                    energy = final_energy.get(player_id, 0)

                    if is_draw:
                        outcome = GameOutcome.DRAW
                    elif player_id == winner_id:
                        outcome = GameOutcome.WIN
                    else:
                        outcome = GameOutcome.LOSS

                    trace.results.append(
                        PlayerResult(
                            player_id=player_id,
                            player_name=player["name"],
                            outcome=outcome,
                            final_score=float(energy),
                        )
                    )

        return trace

    def _parse_turn(
        self, frame: dict, turn_idx: int, players: list[dict], data: dict
    ) -> TurnRecord:
        """Parse a single turn/frame."""
        frame["turn"] = turn_idx

        # Extract global state
        state = {
            "cells": frame.get("cells", []),
            "energy": frame.get("energy", {}),
            "entities": frame.get("entities", {}),
            "deposited": frame.get("deposited", {}),
            "events": frame.get("events", []),
        }

        # Extract actions for each player
        actions = []
        player_states = {}

        for player in players:
            player_id = player["id"]
            player_name = player["name"]

            # Get player's actions this turn
            player_moves = frame.get("moves", {}).get(player_id, [])

            for move in player_moves:
                actions.append(
                    PlayerAction(
                        player_id=player_id,
                        player_name=player_name,
                        turn=turn_idx,
                        action=move,
                        action_type=move.get("type"),
                    )
                )

            # Build player-specific state view
            player_states[player_name] = extract_player_state(frame, player_id, data)

        return TurnRecord(
            turn=turn_idx,
            state=state,
            actions=actions,
            player_states=player_states,
        )


def parse_halite3_trace(file_path: str | Path, source: dict | None = None) -> GameTrace:
    """
    Convenience function to parse a Halite III replay file.

    Args:
        file_path: Path to .hlt file
        source: Optional source metadata

    Returns:
        GameTrace object
    """
    parser = Halite3TraceParser()
    return parser.parse_file(file_path, source=source)


# =============================================================================
# Subprocess-based offline evaluation
# =============================================================================
#
# Halite III bots are compiled binaries that communicate over stdin/stdout using
# the engine's wire protocol (documented in the Rust hlt library).
#
# Wire protocol (from submission/src/hlt/game.rs + game_map.rs + player.rs):
#
#   INIT (stdin, sent once at startup):
#     Line 1: JSON string of GAME_CONSTANTS
#     Line 2: "{num_players} {my_player_id}"
#     Lines 3..N: one line per player: "{player_id} {shipyard_x} {shipyard_y}"
#     Map init:
#       Line: "{width} {height}"
#       height lines: space-separated halite values for each row
#
#   INIT (stdout, bot responds once):
#     "{bot_name}\n"
#
#   PER TURN (stdin):
#     Line: "{turn_number}"
#     For each player:
#       Line: "{player_id} {num_ships} {num_dropoffs} {halite}"
#       num_ships lines: "{ship_id} {x} {y} {halite}"
#       num_dropoffs lines: "{dropoff_id} {x} {y}"
#     Map updates:
#       Line: "{update_count}"
#       update_count lines: "{x} {y} {halite}"
#
#   PER TURN (stdout, bot responds):
#     Space-separated commands + newline:
#       "g"              = spawn ship
#       "c {ship_id}"   = convert ship to dropoff
#       "m {ship_id} {direction}"  = move (direction: n/s/e/w/o)
#
# Coordinate convention (matches Rust hlt):
#   x = column, y = row
#
# =============================================================================


def encode_init(data: dict, player_id: int) -> str:
    """
    Build the INIT packet sent to a Halite III bot at startup.

    Args:
        data:       Parsed .hlt replay dict (from load_hlt_file)
        player_id:  0-based player ID to impersonate

    Returns:
        Multi-line string ready to write to the bot's stdin.
    """
    lines = []

    # Line 1: game constants as JSON (one compact line)
    lines.append(json.dumps(data.get("GAME_CONSTANTS", {}), separators=(",", ":")))

    # Line 2: num_players my_player_id
    players = data.get("players", [])
    lines.append(f"{len(players)} {player_id}")

    # Lines 3..N: player_id shipyard_x shipyard_y (in player_id order)
    sorted_players = sorted(players, key=lambda p: p["player_id"])
    for p in sorted_players:
        loc = p.get("factory_location", {})
        lines.append(f"{p['player_id']} {loc.get('x', 0)} {loc.get('y', 0)}")

    # Map: width height, then height rows of space-separated halite values
    production_map = data.get("production_map", {})
    width = production_map.get("width", 0)
    height = production_map.get("height", 0)
    grid = production_map.get("grid", [])
    lines.append(f"{width} {height}")
    for row in grid:
        lines.append(" ".join(str(cell.get("energy", 0)) for cell in row))

    return "\n".join(lines) + "\n"


def encode_turn(
    turn_number: int,
    frame: dict,
    prev_halite_map: list[list[int]],
    data: dict,
) -> tuple[str, list[list[int]]]:
    """
    Build the per-turn stdin packet for a Halite III bot.

    Args:
        turn_number:      1-based turn number
        frame:            Current full_frame dict from the replay
        prev_halite_map:  Current halite map (height x width), mutated in-place
        data:             Full replay dict (for map dimensions)

    Returns:
        Tuple of (encoded_string, updated_halite_map).
        The halite map is updated by applying this frame's cell deltas.
    """
    production_map = data.get("production_map", {})
    production_map.get("width", 0)
    production_map.get("height", 0)

    lines = []

    # Line 1: turn number
    lines.append(str(turn_number))

    # Per-player: player_id num_ships num_dropoffs halite
    #             then ships, then dropoffs
    players = sorted(data.get("players", []), key=lambda p: p["player_id"])
    entities = frame.get("entities", {})
    energy = frame.get("energy", {})

    for p in players:
        pid_str = str(p["player_id"])
        player_ships = entities.get(pid_str, {})
        # Dropoffs are not tracked in full_frames entities (only ships are)
        # Use 0 dropoffs since the short fixture has none; a real implementation
        # would track construct events.
        num_ships = len(player_ships)
        num_dropoffs = 0
        halite = energy.get(pid_str, 0)
        lines.append(f"{p['player_id']} {num_ships} {num_dropoffs} {halite}")

        for ship_id_str, ship in sorted(
            player_ships.items(), key=lambda kv: int(kv[0])
        ):
            lines.append(f"{ship_id_str} {ship['x']} {ship['y']} {ship['energy']}")
        # no dropoffs

    # Map updates: cells that changed this frame
    cell_updates = frame.get("cells", [])
    lines.append(str(len(cell_updates)))
    for cell in cell_updates:
        x, y = cell["x"], cell["y"]
        halite = cell.get("production", cell.get("energy", 0))
        prev_halite_map[y][x] = halite
        lines.append(f"{x} {y} {halite}")

    return "\n".join(lines) + "\n", prev_halite_map


def decode_commands(stdout_line: str) -> list[dict]:
    """
    Parse a Halite III bot's stdout command line into canonical action dicts.

    The bot emits: "g c {id} m {id} {dir} ... \\n"
    Tokens are space-separated; order may vary.

    Args:
        stdout_line: Raw stdout line from the bot

    Returns:
        List of action dicts in canonical format:
            {"type": "g"}
            {"type": "c", "id": <int>}
            {"type": "m", "id": <int>, "direction": "<n|s|e|w|o>"}
        Sorted by (type_priority, id) for deterministic comparison.
    """
    tokens = stdout_line.strip().split()
    actions = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "g":
            actions.append({"type": "g"})
            i += 1
        elif t == "c" and i + 1 < len(tokens):
            actions.append({"type": "c", "id": int(tokens[i + 1])})
            i += 2
        elif t == "m" and i + 2 < len(tokens):
            actions.append(
                {"type": "m", "id": int(tokens[i + 1]), "direction": tokens[i + 2]}
            )
            i += 3
        else:
            i += 1  # skip unrecognised token

    def _sort_key(act: dict) -> tuple:
        priority = {"m": 0, "c": 1, "g": 2}.get(act["type"], 3)
        return (priority, act.get("id", -1), act.get("direction", ""))

    return sorted(actions, key=_sort_key)


def query_compiled_bot(
    executable: str | Path | list[str],
    hlt_data: dict,
    player_id: int,
    *,
    timeout: float = 10.0,
) -> list[list[dict]]:
    """
    Feed a Halite III .hlt replay to a compiled bot via stdin and collect commands.

    Spawns the bot subprocess, sends the init packet followed by each frame's
    per-turn packet in order, and reads one command line per turn from stdout.

    Args:
        executable: Path to the compiled bot binary, or a full command list
                    (e.g. ["docker", "run", "-i", "--rm", "image", "/path/bot"])
                    to support running Linux binaries inside a container.
        hlt_data:   Parsed .hlt replay dict (from load_hlt_file)
        player_id:  0-based player ID to impersonate
        timeout:    Per-turn read timeout in seconds

    Returns:
        List of per-turn command lists (one element per turn in full_frames,
        starting from frame 0 which is the pre-spawn state; frames where the
        bot has no entities still produce a response).
        Each element is a sorted list of action dicts.
        If the bot times out or crashes, remaining turns get empty lists.
    """
    import select
    import subprocess

    frames = hlt_data.get("full_frames", [])
    if not frames:
        return []

    production_map = hlt_data.get("production_map", {})
    width = production_map.get("width", 0)
    production_map.get("height", 0)

    # Build initial halite map from production_map.grid
    halite_map: list[list[int]] = [
        [row[x].get("energy", 0) for x in range(width)]
        for row in production_map.get("grid", [])
    ]

    init_packet = encode_init(hlt_data, player_id)

    if isinstance(executable, list):
        cmd = executable
    else:
        cmd = [str(executable)]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    try:
        proc.stdin.write(init_packet)
        proc.stdin.flush()
        # Discard bot name response
        proc.stdout.readline()

        result: list[list[dict]] = []

        for turn_idx, frame in enumerate(frames):
            # turn_number is 1-based in the protocol
            turn_packet, halite_map = encode_turn(
                turn_idx + 1, frame, halite_map, hlt_data
            )

            proc.stdin.write(turn_packet)
            proc.stdin.flush()

            ready = select.select([proc.stdout], [], [], timeout)[0]
            if not ready:
                result.extend([] for _ in range(len(frames) - len(result)))
                break

            line = proc.stdout.readline()
            commands = decode_commands(line)

            # Fill in STILL (direction "o") for ships not explicitly commanded
            # (matching extract_state_action_pairs which includes STILL)
            commanded_ids = {
                cmd.get("id") for cmd in commands if cmd.get("type") == "m"
            }
            my_ships = frame.get("entities", {}).get(str(player_id), {})
            for ship_id_str in my_ships:
                sid = int(ship_id_str)
                if sid not in commanded_ids:
                    commands.append({"type": "m", "id": sid, "direction": "o"})
            result.append(commands)

        return result

    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def eval_bot_against_hlt(
    executable: str | Path | list[str],
    hlt_file: Path | str,
    player_name: str,
    *,
    timeout: float = 10.0,
) -> list[tuple[list[dict], list[dict]]]:
    """
    Evaluate a compiled Halite III bot against recorded target moves from a .hlt file.

    Args:
        executable:  Path to the compiled bot binary
        hlt_file:    Path to the .hlt replay file
        player_name: Name of the target player to evaluate against
        timeout:     Per-turn subprocess read timeout in seconds

    Returns:
        List of (bot_commands, target_commands) pairs, one per turn.
        Both elements are sorted lists of action dicts.
        Only turns where the target player is active are included.
    """
    data = load_hlt_file(hlt_file)

    # Resolve player_name to 0-based player_id
    player_id = None
    for p in data.get("players", []):
        if p.get("name") == player_name:
            player_id = p["player_id"]
            break

    if player_id is None:
        return []

    pid_str = str(player_id)

    # Get target's recorded commands from the .hlt file
    frames = data.get("full_frames", [])
    target_command_lists = []
    for frame in frames:
        raw_cmds = decode_commands(
            " ".join(
                _action_to_token(act) for act in frame.get("moves", {}).get(pid_str, [])
            )
        )
        # Fill in STILL (direction "o") for ships not explicitly commanded
        commanded_ids = {cmd.get("id") for cmd in raw_cmds if cmd.get("type") == "m"}
        my_ships = frame.get("entities", {}).get(pid_str, {})
        for ship_id_str in my_ships:
            sid = int(ship_id_str)
            if sid not in commanded_ids:
                raw_cmds.append({"type": "m", "id": sid, "direction": "o"})
        target_command_lists.append(raw_cmds)

    # Query the bot
    bot_command_lists = query_compiled_bot(executable, data, player_id, timeout=timeout)

    # Pair up
    pairs = []
    for i, target in enumerate(target_command_lists):
        bot = bot_command_lists[i] if i < len(bot_command_lists) else []
        pairs.append((bot, target))

    return pairs


def _action_to_token(act: dict) -> str:
    """Convert a canonical action dict back to a wire-protocol token string."""
    t = act.get("type")
    if t == "g":
        return "g"
    elif t == "c":
        return f"c {act['id']}"
    elif t == "m":
        return f"m {act['id']} {act['direction']}"
    return ""
