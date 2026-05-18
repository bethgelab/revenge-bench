"""
BattleSnake Trace Parser

Converts BattleSnake's native JSONL output format to our unified GameTrace format.

Also provides game-specific utility functions:
- normalize_action(): Convert any action format to canonical lowercase string
- actions_equal(): Compare two actions for equality
- actions_distance(): Compute distance between two actions (0.0 = same, 1.0 = different)

================================================================================
CANONICAL ACTION FORMAT:
================================================================================
All actions are normalized to lowercase strings: "up", "down", "left", "right"

Input formats handled by normalize_action():
- "up", "UP", "Up" -> "up"
- {"move": "up"} -> "up"
- None -> None

================================================================================
RAW FIELDS (from game engine output):
================================================================================
File format: JSONL (one JSON object per line)
Command: `battlesnake play -o output.jsonl`

Line 1 - Game metadata:
    - id: str                   Game ID (UUID)
    - ruleset.name: str         "standard", "royale", etc.
    - ruleset.version: str      "cli"
    - ruleset.settings: dict    foodSpawnChance, minimumFood, hazardDamagePerTurn,
                                royale.shrinkEveryNTurns, squad.* settings
    - map: str                  "standard"
    - timeout: int              500 (ms)
    - source: str               ""

Lines 2..N-1 - Turn records:
    - game: dict                Same as line 1 metadata
    - turn: int                 Turn number (0-indexed)
    - board.height: int         Board height (default 11)
    - board.width: int          Board width (default 11)
    - board.snakes: list        List of snake objects
        - id: str               Snake ID (UUID)
        - name: str             Player name
        - latency: str          Response time in ms
        - health: int           0-100
        - body: list[{x,y}]     Body coordinates (head first)
        - head: {x,y}           Head position
        - length: int           Snake length
        - shout: str            Player message (empty string)
        - squad: str            Squad ID (empty for non-squad games)
        - customizations: dict  color, head, tail
    - board.food: list[{x,y}]   Food positions
    - board.hazards: list[{x,y}] Hazard positions
    - you: dict                 Current snake's perspective (same structure as snake)

Last line - Results:
    - winnerId: str|null        Winner's snake ID (null if draw)
    - winnerName: str|null      Winner's name (null if draw)
    - isDraw: bool              True if game ended in draw

================================================================================
INFERRED FIELDS (computed by parser):
================================================================================
    - action: str               "up"|"down"|"left"|"right"
                                INFERRED from position change between turns:
                                - dy = +1 -> "up"
                                - dy = -1 -> "down"
                                - dx = +1 -> "right"
                                - dx = -1 -> "left"
                                Note: Action for turn N is stored in turn N+1's record
                                      (we see the result, then infer what caused it)

    - player_states: dict       Per-player view of game state
                                Built by setting "you" field to each snake's data

    - metadata.timestamp: datetime  Current time (BattleSnake doesn't include timestamp)
    
    - results[].outcome: GameOutcome  WIN/LOSS/DRAW computed from winner info
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
# Action Normalization & Comparison
# =============================================================================

VALID_ACTIONS = ["up", "down", "left", "right"]


def normalize_action(action: Any) -> str | None:
    """
    Normalize BattleSnake action to canonical lowercase string format.

    Canonical format: "up", "down", "left", "right"

    Input formats:
        - "up", "UP", "Up" (any case) -> "up"
        - {"move": "up"} (API response dict) -> "up"
        - None -> None

    Returns:
        Lowercase action string or None if invalid/missing.
    """
    if action is None:
        return None

    # Handle dict format {"move": "up"}
    if isinstance(action, dict):
        action = action.get("move", action)

    # Convert to lowercase string
    if isinstance(action, str):
        normalized = action.lower()
        if normalized in VALID_ACTIONS:
            return normalized

    return None


def actions_equal(a1: Any, a2: Any) -> bool:
    """
    Compare two BattleSnake actions for equality.

    Both actions are normalized before comparison.

    Examples:
        actions_equal("up", "up") -> True
        actions_equal("UP", "up") -> True
        actions_equal({"move": "up"}, "up") -> True
        actions_equal("up", "down") -> False
        actions_equal(None, None) -> True
    """
    n1 = normalize_action(a1)
    n2 = normalize_action(a2)

    # Both None = equal (both invalid/missing)
    if n1 is None and n2 is None:
        return True

    # One None = not equal
    if n1 is None or n2 is None:
        return False

    return n1 == n2


def actions_distance(a1: Any, a2: Any) -> float:
    """
    Compute distance between two BattleSnake actions.

    For discrete directional actions, distance is binary:
    - 0.0 if actions are the same (after normalization)
    - 1.0 if actions differ

    Examples:
        actions_distance("up", "up") -> 0.0
        actions_distance("UP", "up") -> 0.0
        actions_distance({"move": "up"}, "up") -> 0.0
        actions_distance("up", "down") -> 1.0
        actions_distance(None, None) -> 0.0
        actions_distance("up", None) -> 1.0
    """
    return 0.0 if actions_equal(a1, a2) else 1.0


def extract_player_state(turn_data: dict, player_name: str) -> dict | None:
    """
    Extract a player's view of the game state from a turn record.

    Constructs the game_state dict that would be passed to player's move() function,
    with "you" set to the specified player's snake data.

    Args:
        turn_data: Raw turn data from sim_*.jsonl
        player_name: Name of the player whose perspective to extract

    Returns:
        Game state dict with "you" set to player's snake, or None if not found.
    """
    board = turn_data.get("board", {})
    snakes = board.get("snakes", [])

    # Find the player's snake
    player_snake = None
    for snake in snakes:
        if snake.get("name") == player_name:
            player_snake = snake
            break

    if player_snake is None:
        return None

    # Construct the game state from the player's perspective
    return {
        "game": turn_data.get("game", {}),
        "turn": turn_data.get("turn", 0),
        "board": board,
        "you": player_snake,
    }


def extract_player_action(
    turn_data: dict, next_turn_data: dict, player_name: str
) -> str | None:
    """
    Infer a player's action by comparing positions between turns.

    The action is determined by how the snake's head moved:
    - dx = +1 -> "right"
    - dx = -1 -> "left"
    - dy = +1 -> "up"
    - dy = -1 -> "down"

    Args:
        turn_data: Current turn data
        next_turn_data: Next turn data (to see where snake moved)
        player_name: Name of the player

    Returns:
        Action string ("up"/"down"/"left"/"right") or None if cannot determine.
    """
    board = turn_data.get("board", {})
    next_board = next_turn_data.get("board", {})

    # Find player's snake in both turns
    current_head = None
    next_head = None

    for snake in board.get("snakes", []):
        if snake.get("name") == player_name:
            current_head = snake.get("head", {})
            break

    for snake in next_board.get("snakes", []):
        if snake.get("name") == player_name:
            next_head = snake.get("head", {})
            break

    if current_head is None or next_head is None:
        return None

    dx = next_head.get("x", 0) - current_head.get("x", 0)
    dy = next_head.get("y", 0) - current_head.get("y", 0)

    if dx == 1:
        return "right"
    elif dx == -1:
        return "left"
    elif dy == 1:
        return "up"
    elif dy == -1:
        return "down"

    return None


def extract_state_action_pairs(
    sim_file: Path | str, player_name: str
) -> list[tuple[dict, str]]:
    """
    Extract all (state, action) pairs for a player from a simulation file.

    This is the main function for offline evaluation - it reads a sim file and
    returns all the states the player saw and actions they took.

    Args:
        sim_file: Path to sim_*.jsonl file
        player_name: Name of the player to extract data for

    Returns:
        List of (state, action) tuples where:
        - state: The game_state dict the player received (with "you" = player's snake)
        - action: The action the player took ("up"/"down"/"left"/"right")
    """
    import json

    with open(sim_file) as f:
        lines = f.read().strip().split("\n")

    # Parse all turn records (skip metadata and results)
    turns = []
    for line in lines:
        try:
            turn_data = json.loads(line)
            if "board" in turn_data:  # Has board = is a turn record
                turns.append(turn_data)
        except json.JSONDecodeError:
            continue

    # Extract state-action pairs from consecutive turns
    pairs = []
    for i in range(len(turns) - 1):
        turn_data = turns[i]
        next_turn_data = turns[i + 1]

        # Extract player's state (what they saw)
        state = extract_player_state(turn_data, player_name)
        if state is None:
            continue

        # Extract player's action (inferred from position change)
        action = extract_player_action(turn_data, next_turn_data, player_name)
        if action is None:
            continue

        pairs.append((state, action))

    return pairs


# =============================================================================
# Trace Parser
# =============================================================================


class BattleSnakeTraceParser:
    """
    Parser for BattleSnake's native JSONL output format.

    Usage:
        parser = BattleSnakeTraceParser()
        trace = parser.parse_file("game_output.jsonl")

        # Or parse from raw JSONL content
        trace = parser.parse_content(jsonl_content)
    """

    GAME_TYPE = "BattleSnake"

    def __init__(self, infer_actions: bool = True):
        """
        Initialize the parser.

        Args:
            infer_actions: If True, infer actions from position changes between turns.
                          BattleSnake's output doesn't directly include actions taken.
        """
        self.infer_actions = infer_actions

    def parse_file(self, path: str | Path, source: dict | None = None) -> GameTrace:
        """
        Parse a BattleSnake JSONL output file.

        Args:
            path: Path to the JSONL file
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
        Parse JSONL content from BattleSnake.

        Args:
            content: JSONL content as a string
            source: Optional source metadata

        Returns:
            GameTrace object
        """
        lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
        if not lines:
            raise ValueError("Empty trace content")

        records = [json.loads(line) for line in lines]
        return self._parse_records(records, source)

    def parse_records(
        self, records: list[dict], source: dict | None = None
    ) -> GameTrace:
        """
        Parse a list of BattleSnake JSON records.

        Args:
            records: List of parsed JSON objects (one per turn/request)
            source: Optional source metadata

        Returns:
            GameTrace object
        """
        return self._parse_records(records, source)

    def _parse_records(
        self, records: list[dict], source: dict | None = None
    ) -> GameTrace:
        """
        Internal parsing logic.

        BattleSnake JSONL format:
        - Line 1: Game metadata (id, ruleset, map, timeout) - no 'turn' or 'board'
        - Lines 2..N-1: Turn records (game, turn, board, you)
        - Line N: Results (winnerId, winnerName, isDraw)
        """
        if not records:
            raise ValueError("No records to parse")

        # Separate records by type
        game_metadata_record = None
        turn_records = []
        results_record = None

        for record in records:
            if "winnerName" in record or "isDraw" in record:
                # This is the results record (last line)
                results_record = record
            elif "turn" in record and "board" in record:
                # This is a turn record
                turn_records.append(record)
            elif "ruleset" in record and "turn" not in record:
                # This is the game metadata (first line)
                game_metadata_record = record

        # Extract results
        is_draw = results_record.get("isDraw", False) if results_record else False
        winner_name = results_record.get("winnerName") if results_record else None
        results_record.get("winnerId") if results_record else None

        # Extract game metadata - might be in first line or embedded in turn records
        if game_metadata_record:
            game_id = game_metadata_record.get("id", "unknown")
            ruleset = game_metadata_record.get("ruleset", {})
            game_map = game_metadata_record.get("map", "standard")
            timeout = game_metadata_record.get("timeout", 500)
        elif turn_records:
            game_info = turn_records[0].get("game", {})
            game_id = game_info.get("id", "unknown")
            ruleset = game_info.get("ruleset", {})
            game_map = game_info.get("map", "standard")
            timeout = game_info.get("timeout", 500)
        else:
            raise ValueError("No game metadata or turn records found")

        # Build player list from first turn's snakes
        players = []
        if turn_records:
            first_turn = turn_records[0]
            board_info = first_turn.get("board", {})
            for snake in board_info.get("snakes", []):
                players.append(
                    {
                        "id": snake.get("id", ""),
                        "name": snake.get("name", ""),
                    }
                )
            board_width = board_info.get("width", 11)
            board_height = board_info.get("height", 11)
        else:
            board_width = 11
            board_height = 11

        metadata = GameMetadata(
            game_id=game_id,
            game_type=self.GAME_TYPE,
            timestamp=datetime.now(),  # BattleSnake doesn't include timestamp
            players=players,
            config={
                "width": board_width,
                "height": board_height,
                "ruleset": ruleset,
                "map": game_map,
                "timeout": timeout,
            },
            source=source or {},
        )

        # Parse turns (turn_records already filtered above)
        turns = []
        prev_positions: dict[str, tuple[int, int]] = {}  # For inferring actions

        for record in turn_records:
            turn_num = record.get("turn", 0)
            board = record.get("board", {})

            # Build the state (common to all players)
            state = {
                "game": record.get("game", {}),
                "turn": turn_num,
                "board": {
                    "width": board.get("width", 11),
                    "height": board.get("height", 11),
                    "food": board.get("food", []),
                    "hazards": board.get("hazards", []),
                    "snakes": board.get("snakes", []),
                },
            }

            # Build player-specific states (each player sees themselves as "you")
            player_states = {}
            for snake in board.get("snakes", []):
                snake_name = snake.get("name", "")
                player_states[snake_name] = {
                    **state,
                    "you": snake,
                }

            # Infer actions from position changes
            actions = []
            if self.infer_actions and turn_num > 0:
                for snake in board.get("snakes", []):
                    snake_id = snake.get("id", "")
                    snake_name = snake.get("name", "")
                    head = snake.get("head", {})
                    current_pos = (head.get("x", 0), head.get("y", 0))

                    if snake_id in prev_positions:
                        prev_pos = prev_positions[snake_id]
                        action = self._infer_action(prev_pos, current_pos)

                        actions.append(
                            PlayerAction(
                                player_id=snake_id,
                                player_name=snake_name,
                                turn=turn_num - 1,  # Action was taken on previous turn
                                action=action,
                                action_type="move",
                                latency_ms=self._parse_latency(
                                    snake.get("latency", "")
                                ),
                                valid_actions=VALID_ACTIONS.copy(),
                            )
                        )

                        # TODO(battlesnake): We currently *attach* the inferred action for
                        # decision turn (turn_num-1) onto the TurnRecord for `turn_num`.
                        # This is convenient in a single pass, but it means consumers that
                        # assume `TurnRecord(turn=t).actions` corresponds to state at turn t
                        # can be off-by-one. Prefer attaching this action to TurnRecord(t)
                        # (e.g., via buffering / second pass), or ensure consumers use
                        # PlayerAction.turn when pairing state/action.

            # Update positions for next iteration
            for snake in board.get("snakes", []):
                snake_id = snake.get("id", "")
                head = snake.get("head", {})
                prev_positions[snake_id] = (head.get("x", 0), head.get("y", 0))

            turns.append(
                TurnRecord(
                    turn=turn_num,
                    state=state,
                    actions=actions,
                    player_states=player_states,
                )
            )

        # Build results
        results = []
        # Get final board state from last turn record (if available)
        final_board = turn_records[-1].get("board", {}) if turn_records else {}
        final_snakes = {s.get("name", ""): s for s in final_board.get("snakes", [])}

        for player in players:
            player_name = player["name"]
            if player_name == winner_name:
                outcome = GameOutcome.WIN
            elif is_draw:
                outcome = GameOutcome.DRAW
            else:
                outcome = GameOutcome.LOSS

            # Try to get elimination info
            snake_data = final_snakes.get(player_name, {})

            results.append(
                PlayerResult(
                    player_id=player["id"],
                    player_name=player_name,
                    outcome=outcome,
                    elimination_reason=snake_data.get("eliminatedCause"),
                    elimination_turn=snake_data.get("eliminatedOnTurn"),
                )
            )

        return GameTrace(
            metadata=metadata,
            turns=turns,
            results=results,
            winner=winner_name,
            is_draw=is_draw,
        )

    def _infer_action(
        self, prev_pos: tuple[int, int], current_pos: tuple[int, int]
    ) -> str:
        """
        Infer the action taken based on position change.

        BattleSnake coordinates: (0,0) is bottom-left, y increases upward.
        """
        dx = current_pos[0] - prev_pos[0]
        dy = current_pos[1] - prev_pos[1]

        if dx == 1:
            return "right"
        elif dx == -1:
            return "left"
        elif dy == 1:
            return "up"
        elif dy == -1:
            return "down"
        else:
            # No movement or teleportation (shouldn't happen normally)
            return "up"  # Default

    def _parse_latency(self, latency_str: str) -> int | None:
        """Parse latency string to milliseconds."""
        if not latency_str:
            return None
        try:
            return int(latency_str)
        except ValueError:
            return None


def parse_battlesnake_trace(path: str | Path, **kwargs) -> GameTrace:
    """Convenience function to parse a BattleSnake trace file."""
    return BattleSnakeTraceParser(**kwargs).parse_file(path)
