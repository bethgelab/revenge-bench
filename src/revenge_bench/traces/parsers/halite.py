"""
Halite (Original) Trace Parser

Converts Halite I's native .hlt replay format to our unified GameTrace format.

Also provides game-specific utility functions:
- normalize_action(): Convert any action format to canonical dict format
- actions_distance(): Compute normalized distance between actions (0.0 to 1.0)

================================================================================
CANONICAL ACTION FORMAT:
================================================================================
Actions are lists of [row, col, move] triples, one per owned cell:

    [[row, col, move], ...]

Move values:
    0 = STILL  (stay and gain production strength)
    1 = NORTH  (move up, y - 1)
    2 = EAST   (move right, x + 1)
    3 = SOUTH  (move down, y + 1)
    4 = WEST   (move left, x - 1)

Only cells owned by the player are included; unowned cells are omitted.
The list is always sorted by (row, col) for order-independent comparison.

================================================================================
FILE FORMAT:
================================================================================
.hlt files are plain uncompressed JSON with structure:

{
    "version": 11,
    "width": 30,
    "height": 30,
    "num_players": 2,
    "num_frames": 301,
    "player_names": ["BotA", "BotB"],       // 0-indexed; player tags are 1-based
    "productions": [                         // height x width static production values
        [2, 3, 4, ...],                      // row 0
        ...
    ],
    "frames": [                              // num_frames entries (includes final state)
        [                                    // height x width grid
            [[owner, strength], ...],        // row 0; owner=0 neutral, 1/2/... = player tag
            ...
        ],
        ...
    ],
    "moves": [                               // num_frames - 1 entries (no moves for final frame)
        [                                    // height x width grid of move integers
            [0, 1, 0, ...],                  // row 0
            ...
        ],
        ...
    ]
}

Player tags in frames are 1-based (player_names[0] has tag 1, player_names[1] has tag 2, etc.)

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

MOVE_STILL = 0
MOVE_NORTH = 1
MOVE_EAST = 2
MOVE_SOUTH = 3
MOVE_WEST = 4

VALID_MOVES = {MOVE_STILL, MOVE_NORTH, MOVE_EAST, MOVE_SOUTH, MOVE_WEST}

MOVE_NAMES = {
    MOVE_STILL: "o",
    MOVE_NORTH: "n",
    MOVE_EAST: "e",
    MOVE_SOUTH: "s",
    MOVE_WEST: "w",
}

MOVE_FROM_NAME = {v: k for k, v in MOVE_NAMES.items()}


# =============================================================================
# Action Normalization & Comparison
# =============================================================================


def normalize_action(action: Any) -> list[list[int]] | None:
    """
    Normalize a Halite action to canonical [[row, col, move], ...] format,
    sorted by (row, col).

    Input formats:
        - List of [row, col, move] triples (already canonical) -> validated and sorted
        - None -> None

    Returns:
        Sorted list of [row, col, move] triples, or None if invalid.
    """
    if action is None:
        return None

    if not isinstance(action, list):
        return None

    normalized = []
    for item in action:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return None
        row, col, move = item
        if not isinstance(row, int) or not isinstance(col, int):
            return None
        if move not in VALID_MOVES:
            return None
        normalized.append([row, col, move])

    return sorted(normalized)


def actions_distance(a1: Any, a2: Any) -> float:
    """
    Compute normalized distance between two Halite action lists.

    Returns the fraction of cells with different moves (0.0 to 1.0).
    - 0.0: Actions are identical
    - 1.0: Actions are completely different
    - 0.1: 90% of cells have correct moves

    This normalized metric allows averaging across different game states
    with varying numbers of controlled cells.

    Args:
        a1: First action (list of [row, col, move] triples)
        a2: Second action (list of [row, col, move] triples)

    Returns:
        Normalized distance in [0.0, 1.0]

    Examples:
        actions_distance([[0, 5, 1], [2, 3, 0]], [[0, 5, 1], [2, 3, 0]]) -> 0.0
        actions_distance([[0, 5, 1], [2, 3, 0]], [[0, 5, 2], [2, 3, 0]]) -> 0.5
        actions_distance([[0, 5, 1]], [[2, 3, 0]]) -> 1.0 (completely different cells)
        actions_distance([], []) -> 0.0
    """
    n1 = normalize_action(a1)
    n2 = normalize_action(a2)

    # Both None/invalid = equal (distance 0)
    if n1 is None and n2 is None:
        return 0.0

    # One None = completely different (distance 1)
    if n1 is None or n2 is None:
        return 1.0

    # Convert to dicts for efficient lookup: {(row, col): move}
    d1 = {(r, c): m for r, c, m in n1}
    d2 = {(r, c): m for r, c, m in n2}

    # All cells that appear in either action
    all_cells = set(d1.keys()) | set(d2.keys())

    # Empty actions = distance 0
    if not all_cells:
        return 0.0

    # Count cells with mismatched moves (including cells only in one action)
    mismatches = sum(1 for cell in all_cells if d1.get(cell) != d2.get(cell))

    return mismatches / len(all_cells)


def load_hlt_file(file_path: Path | str) -> dict:
    """
    Load a Halite I .hlt replay file (plain uncompressed JSON).

    Args:
        file_path: Path to the .hlt file

    Returns:
        Parsed JSON data as dict
    """
    file_path = Path(file_path)
    return json.loads(file_path.read_bytes())


def extract_player_state(
    frame: list[list[list[int]]],
    turn: int,
    player_tag: int,
    data: dict,
) -> dict:
    """
    Extract the game state from a frame.

    Returns a neutral board representation: all non-neutral cells as a list of
    [r, c, owner, strength, production] lists, sorted by (r, c). Owner is the
    1-based player tag (player_names[0] -> tag 1, etc.); 0 means neutral and
    neutral cells are omitted.

    Args:
        frame: Frame data (height x width grid of [owner, strength])
        turn: Turn index
        player_tag: 1-based player tag of the player being evaluated (kept for
            API compatibility with extract_state_action_pairs; not used to
            filter cells)
        data: Full replay data (for width, height, productions)

    Returns:
        State dict with fields: turn, width, height, cells, player_names.
    """
    width = data.get("width", len(frame[0]) if frame else 0)
    height = data.get("height", len(frame))
    productions = data.get("productions", [])

    cells = []
    for r in range(height):
        for c in range(width):
            owner, strength = frame[r][c]
            if owner != 0:
                prod = productions[r][c] if productions else 0
                cells.append([r, c, owner, strength, prod])

    return {
        "turn": turn,
        "width": width,
        "height": height,
        "cells": cells,  # [[r, c, owner, strength, production], ...] sorted by (r, c)
        "player_names": data.get("player_names", []),
        "player_tag": player_tag,
    }


def extract_state_action_pairs(
    sim_file: Path | str,
    player_name: str,
) -> list[tuple[dict, list[list[int]]]]:
    """
    Extract all (state, action) pairs for a player from a Halite I replay file.

    The action is a sorted list of [row, col, move] triples, one per cell owned
    by the player on that turn.

    Args:
        sim_file: Path to .hlt file
        player_name: Name of the player to extract data for (from player_names list)

    Returns:
        List of (state, action) tuples.
    """
    data = load_hlt_file(sim_file)

    player_names = data.get("player_names", [])
    if player_name not in player_names:
        return []

    # Player tags are 1-based
    player_tag = player_names.index(player_name) + 1

    frames = data.get("frames", [])
    moves = data.get("moves", [])
    height = data.get("height", 0)
    width = data.get("width", 0)

    pairs = []
    # moves has num_frames - 1 entries; frame[i] + moves[i] -> state before move i
    for turn_idx, move_grid in enumerate(moves):
        frame = frames[turn_idx]

        state = extract_player_state(frame, turn_idx, player_tag, data)

        # Extract this player's moves as sorted [row, col, move] triples
        # including STILL (move 0) for all owned cells
        action = sorted(
            [r, c, move_grid[r][c]]
            for r in range(height)
            for c in range(width)
            if frame[r][c][0] == player_tag
        )

        pairs.append((state, action))

    return pairs


# =============================================================================
# Trace Parser
# =============================================================================


class HaliteTraceParser:
    """
    Parser for Halite I's native .hlt replay format.

    Usage:
        parser = HaliteTraceParser()
        trace = parser.parse_file("12345-67890.hlt")
    """

    GAME_TYPE = "Halite"

    def __init__(self):
        pass

    def parse_file(self, path: str | Path, source: dict | None = None) -> GameTrace:
        """
        Parse a Halite I .hlt replay file.

        Args:
            path: Path to the .hlt file
            source: Optional source metadata

        Returns:
            GameTrace object
        """
        path = Path(path)
        data = load_hlt_file(path)

        player_names_list = data.get("player_names", [])
        players = [
            {"id": str(i + 1), "name": name} for i, name in enumerate(player_names_list)
        ]

        metadata = GameMetadata(
            game_id=path.stem,
            game_type=self.GAME_TYPE,
            timestamp=datetime.now(),
            players=players,
            config={
                "width": data.get("width"),
                "height": data.get("height"),
                "num_players": data.get("num_players"),
            },
            source=source or {},
        )

        trace = GameTrace(metadata=metadata)

        frames = data.get("frames", [])
        moves = data.get("moves", [])

        for turn_idx, frame in enumerate(frames):
            # moves has one fewer entry than frames (no moves after final frame)
            move_grid = moves[turn_idx] if turn_idx < len(moves) else None
            turn = self._parse_turn(frame, turn_idx, move_grid, players, data)
            trace.add_turn(turn)

        # Determine winner from final frame cell counts
        if frames:
            final_frame = frames[-1]
            height = data.get("height", len(final_frame))
            width = data.get("width", len(final_frame[0]) if final_frame else 0)

            # Count total strength per player
            strength_by_tag: dict[int, int] = {}
            for r in range(height):
                for c in range(width):
                    owner, strength = final_frame[r][c]
                    if owner != 0:
                        strength_by_tag[owner] = (
                            strength_by_tag.get(owner, 0) + strength
                        )

            if strength_by_tag:
                max_strength = max(strength_by_tag.values())
                winners = [
                    tag for tag, s in strength_by_tag.items() if s == max_strength
                ]
                is_draw = len(winners) > 1

                trace.is_draw = is_draw
                trace.winner = None if is_draw else player_names_list[winners[0] - 1]

                for player in players:
                    tag = int(player["id"])
                    strength = strength_by_tag.get(tag, 0)
                    if is_draw:
                        outcome = GameOutcome.DRAW
                    elif tag in winners:
                        outcome = GameOutcome.WIN
                    else:
                        outcome = GameOutcome.LOSS

                    trace.results.append(
                        PlayerResult(
                            player_id=player["id"],
                            player_name=player["name"],
                            outcome=outcome,
                            final_score=float(strength),
                        )
                    )

        return trace

    def _parse_turn(
        self,
        frame: list,
        turn_idx: int,
        move_grid: list | None,
        players: list[dict],
        data: dict,
    ) -> TurnRecord:
        """Parse a single turn/frame."""
        height = data.get("height", len(frame))
        width = data.get("width", len(frame[0]) if frame else 0)

        state = {
            "cells": frame,
            "turn": turn_idx,
        }

        actions = []
        player_states = {}

        for player in players:
            player_tag = int(player["id"])
            player_name = player["name"]

            player_state = extract_player_state(frame, turn_idx, player_tag, data)
            player_states[player_name] = player_state

            if move_grid is not None:
                # Collect this player's per-cell moves as sorted [row, col, move] triples
                player_moves = sorted(
                    [r, c, move_grid[r][c]]
                    for r in range(height)
                    for c in range(width)
                    if frame[r][c][0] == player_tag
                )

                if player_moves:
                    actions.append(
                        PlayerAction(
                            player_id=player["id"],
                            player_name=player_name,
                            turn=turn_idx,
                            action=player_moves,
                            action_type="moves",
                        )
                    )

        return TurnRecord(
            turn=turn_idx,
            state=state,
            actions=actions,
            player_states=player_states,
        )


def parse_halite_trace(file_path: str | Path, source: dict | None = None) -> GameTrace:
    """
    Convenience function to parse a Halite I replay file.

    Args:
        file_path: Path to .hlt file
        source: Optional source metadata

    Returns:
        GameTrace object
    """
    parser = HaliteTraceParser()
    return parser.parse_file(file_path, source=source)


# =============================================================================
# Subprocess-based offline evaluation
# =============================================================================
#
# Halite bots are compiled binaries that communicate over stdin/stdout using
# the engine's wire protocol.  To evaluate a learner's compiled bot offline
# (without running a full live game), we replay the recorded frames from a
# .hlt file through the bot's stdin and read its moves from stdout.
#
# Wire protocol (as implemented in hlt.h / airesources/C):
#
#   INIT (stdin, sent once at startup):
#     "{player_tag} {width} {height}\n"
#     productions: space-separated ints, row-major (y outer, x inner)
#     initial frame: RLE owner map + strength grid (see encode_frame)
#
#   INIT (stdout, bot responds once):
#     "{bot_name}\n"
#
#   EACH TURN (stdin):
#     frame: RLE owner map + strength grid
#
#   EACH TURN (stdout, bot responds):
#     "{x} {y} {dir} {x} {y} {dir} ...\n"   (only non-STILL owned cells)
#     or just "\n" for all-STILL
#
# Coordinate convention (matches C hlt.h):
#   x = column, y = row   (so frame[row][col] = frame[y][x])
#
# =============================================================================


def encode_productions(data: dict) -> str:
    """
    Encode the production map as a space-separated row-major string.

    The C hlt.h reads productions as:
        for y in range(height):
            for x in range(width):
                production[x][y] = getnextint()

    Args:
        data: Full .hlt replay dict (with "productions", "width", "height")

    Returns:
        Space-separated production values, row-major (y outer, x inner)
    """
    width = data["width"]
    height = data["height"]
    prods = data.get("productions", [])
    tokens = []
    for y in range(height):
        for x in range(width):
            tokens.append(str(prods[y][x] if prods else 0))
    return " ".join(tokens)


def encode_frame(frame: list[list[list[int]]], width: int, height: int) -> str:
    """
    Encode a single frame as the RLE owner map + strength grid expected by
    GetFrame() / __parsemap() in hlt.h.

    Format:
        RLE owner section: alternating "{run} {owner}" pairs covering all
            width*height cells in row-major order (y outer, x inner)
        Strength section: space-separated strength values, row-major

    Args:
        frame: 2D grid, frame[row][col] = [owner, strength]
        width:  map width  (= number of columns)
        height: map height (= number of rows)

    Returns:
        String ready to be written to the bot's stdin
    """
    # --- RLE owner section ---
    rle_parts = []
    run = 0
    current_owner = None
    for y in range(height):
        for x in range(width):
            owner = frame[y][x][0]
            if owner == current_owner:
                run += 1
            else:
                if current_owner is not None:
                    rle_parts.append(f"{run} {current_owner}")
                current_owner = owner
                run = 1
    if current_owner is not None:
        rle_parts.append(f"{run} {current_owner}")

    # --- Strength section ---
    strength_parts = []
    for y in range(height):
        for x in range(width):
            strength_parts.append(str(frame[y][x][1]))

    return " ".join(rle_parts) + " " + " ".join(strength_parts)


def decode_moves(stdout_line: str) -> list[list[int]]:
    """
    Parse a bot's stdout move line into canonical [[row, col, move], ...] format.

    The bot emits: "{x} {y} {dir} {x} {y} {dir} ...\n"
    where x=col, y=row.  STILL moves are omitted.

    Args:
        stdout_line: Raw stdout line from the bot (may be empty for all-STILL)

    Returns:
        Sorted list of [row, col, move] triples (STILL moves NOT included,
        consistent with how extract_state_action_pairs omits STILL).
    """
    tokens = stdout_line.strip().split()
    if not tokens:
        return []

    moves = []
    i = 0
    while i + 2 < len(tokens):
        x = int(tokens[i])  # column
        y = int(tokens[i + 1])  # row
        direction = int(tokens[i + 2])
        if direction != MOVE_STILL:
            moves.append([y, x, direction])  # convert to [row, col, move]
        i += 3

    return sorted(moves)


def query_compiled_bot(
    executable: str | Path,
    hlt_data: dict,
    player_tag: int,
    *,
    timeout: float = 10.0,
) -> list[list[list[int]]]:
    """
    Feed a .hlt replay to a compiled Halite bot via stdin and collect its moves.

    Spawns the bot subprocess, sends the init packet followed by each frame in
    order, and reads one move line per frame from stdout.  The bot receives the
    exact same sequence of frames the recorded player saw, enabling offline
    evaluation of a learner's strategy against a target's recorded game.

    Args:
        executable: Path to the compiled bot binary
        hlt_data:   Parsed .hlt replay dict (from load_hlt_file)
        player_tag: 1-based player tag to impersonate (determines init packet)
        timeout:    Per-turn read timeout in seconds

    Returns:
        List of per-turn move lists.  moves[i] corresponds to frame i (0-indexed).
        Each element is a sorted [[row, col, move], ...] list including STILL
        for all owned cells (consistent with extract_state_action_pairs).
        If the bot times out or crashes, remaining turns get empty lists.
    """
    import subprocess

    width = hlt_data["width"]
    height = hlt_data["height"]
    frames = hlt_data["frames"]
    moves_count = len(hlt_data.get("moves", []))

    # Build init packet: "{player_tag} {width} {height}\n{productions}\n{frame0}\n"
    init = (
        f"{player_tag} {width} {height}\n"
        f"{encode_productions(hlt_data)}\n"
        f"{encode_frame(frames[0], width, height)}\n"
    )

    proc = subprocess.Popen(
        [str(executable)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    try:
        # Send init; read and discard the bot's name response
        proc.stdin.write(init)
        proc.stdin.flush()
        proc.stdout.readline()  # discard "{bot_name}\n"

        result: list[list[list[int]]] = []

        # Feed frames 1..N (frames[0] was part of init; moves[i] = response to frames[i])
        # There are len(moves) move grids, corresponding to frames[0]..frames[N-1]
        for i in range(moves_count):
            # Frame i+1 is what the bot sees *after* having responded to frame i
            # (same as how GetFrame reads the next state each iteration)
            if i + 1 < len(frames):
                proc.stdin.write(f"{encode_frame(frames[i + 1], width, height)}\n")
                proc.stdin.flush()

            # Read the bot's response with timeout
            import select

            ready = select.select([proc.stdout], [], [], timeout)[0]
            if not ready:
                # Bot timed out — fill remaining turns with empty lists
                result.extend([] for _ in range(moves_count - len(result)))
                break

            line = proc.stdout.readline()
            non_still = decode_moves(line)

            # Fill in STILL for all owned cells not explicitly moved
            # (matching extract_state_action_pairs which includes STILL)
            moved = {(m[0], m[1]) for m in non_still}
            frame = frames[i]
            all_moves = list(non_still)
            for r in range(height):
                for c in range(width):
                    if frame[r][c][0] == player_tag and (r, c) not in moved:
                        all_moves.append([r, c, MOVE_STILL])
            result.append(sorted(all_moves))

        return result

    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def eval_bot_against_hlt(
    executable: str | Path,
    hlt_file: Path | str,
    player_name: str,
    *,
    timeout: float = 10.0,
) -> list[tuple[list[list[int]], list[list[int]]]]:
    """
    Evaluate a compiled Halite bot against recorded target moves from a .hlt file.

    Replays the target player's frames through the bot and compares the bot's
    moves to the recorded moves turn by turn.

    Args:
        executable:  Path to the compiled bot binary
        hlt_file:    Path to the .hlt replay file
        player_name: Name of the target player to evaluate against
        timeout:     Per-turn subprocess read timeout in seconds

    Returns:
        List of (bot_moves, target_moves) pairs, one per turn.
        bot_moves and target_moves are each sorted [[row, col, move], ...] lists.
    """
    data = load_hlt_file(hlt_file)

    # Resolve player_name to 1-based tag
    player_names = data.get("player_names", [])
    if player_name not in player_names:
        return []
    player_tag = player_names.index(player_name) + 1

    # Get target's recorded moves from the .hlt file
    frames = data["frames"]
    raw_moves = data.get("moves", [])
    target_move_lists = []
    for i, move_grid in enumerate(raw_moves):
        frame = frames[i]
        target_moves = sorted(
            [row, col, move_grid[row][col]]
            for row in range(data["height"])
            for col in range(data["width"])
            if frame[row][col][0] == player_tag
        )
        target_move_lists.append(target_moves)

    # Query the bot
    bot_move_lists = query_compiled_bot(executable, data, player_tag, timeout=timeout)

    # Pair up (pad with empty if bot produced fewer turns)
    pairs = []
    for i, target in enumerate(target_move_lists):
        bot = bot_move_lists[i] if i < len(bot_move_lists) else []
        pairs.append((bot, target))

    return pairs
