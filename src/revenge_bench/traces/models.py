"""
Game Trace Data Models

This module defines the generic structure for logging game dynamics.
Each game type implements game-specific state representations while 
conforming to these base interfaces.

Design Principles:
1. **Game-Agnostic Core**: The base models work for any game type
2. **Rich State Capture**: Enough information to replay decisions
3. **JSON-Serializable**: All data can be serialized to JSONL
4. **Action Attribution**: Every action is tied to a player and turn
5. **Extensible**: Game-specific fields via typed state dictionaries
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class GameOutcome(str, Enum):
    """Possible game outcomes."""

    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"
    TIMEOUT = "timeout"
    ERROR = "error"
    ONGOING = "ongoing"


@dataclass
class Coord:
    """2D coordinate for grid-based games."""

    x: int
    y: int

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, d: dict) -> Coord:
        return cls(x=d["x"], y=d["y"])


@dataclass
class PlayerAction:
    """
    An action taken by a player at a specific turn.

    Attributes:
        player_id: Unique identifier for the player in this game
        player_name: Human-readable player name
        turn: The turn number when this action was taken
        action: The action taken (game-specific format)
        action_type: Optional categorization of the action
        latency_ms: Time taken to respond (if available)
        valid_actions: List of all legal actions at this state (optional)
        reasoning: Any explanation/shout from the player (optional)
    """

    player_id: str
    player_name: str
    turn: int
    action: str | list | dict[str, Any]
    action_type: str | None = None
    latency_ms: int | None = None
    valid_actions: list[str | dict] | None = None
    reasoning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "turn": self.turn,
            "action": self.action,
        }
        if self.action_type:
            d["action_type"] = self.action_type
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        if self.valid_actions:
            d["valid_actions"] = self.valid_actions
        if self.reasoning:
            d["reasoning"] = self.reasoning
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlayerAction:
        return cls(
            player_id=d["player_id"],
            player_name=d["player_name"],
            turn=d["turn"],
            action=d["action"],
            action_type=d.get("action_type"),
            latency_ms=d.get("latency_ms"),
            valid_actions=d.get("valid_actions"),
            reasoning=d.get("reasoning"),
        )


@dataclass
class TurnRecord:
    """
    A record of a single turn in the game.

    This captures the state BEFORE actions are taken, plus all actions taken.

    Attributes:
        turn: Turn number (0-indexed typically)
        state: The game state at the start of this turn (game-specific)
        actions: Actions taken by each player this turn
        outcome: Per-player outcomes after this turn (eliminations, etc.)
    """

    turn: int
    state: dict[str, Any]  # Game-specific state (board, positions, etc.)
    actions: list[PlayerAction] = field(default_factory=list)
    player_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Player-specific views of state (e.g., "you" in BattleSnake)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "state": self.state,
            "actions": [a.to_dict() for a in self.actions],
            "player_states": self.player_states,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TurnRecord:
        return cls(
            turn=d["turn"],
            state=d["state"],
            actions=[PlayerAction.from_dict(a) for a in d.get("actions", [])],
            player_states=d.get("player_states", {}),
        )


@dataclass
class GameMetadata:
    """
    Metadata about a game instance.

    Attributes:
        game_id: Unique identifier for this game
        game_type: Type of game (BattleSnake, CoreWar, etc.)
        timestamp: When the game was played
        players: List of player names/IDs
        config: Game configuration (board size, rules variant, etc.)
        source: Where this trace came from (tournament_id, etc.)
    """

    game_id: str
    game_type: str
    timestamp: datetime
    players: list[dict[str, str]]  # [{"id": "...", "name": "..."}]
    config: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "game_type": self.game_type,
            "timestamp": self.timestamp.isoformat(),
            "players": self.players,
            "config": self.config,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GameMetadata:
        return cls(
            game_id=d["game_id"],
            game_type=d["game_type"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            players=d["players"],
            config=d.get("config", {}),
            source=d.get("source", {}),
        )


@dataclass
class PlayerResult:
    """Final result for a single player."""

    player_id: str
    player_name: str
    outcome: GameOutcome
    final_score: float | None = None
    elimination_turn: int | None = None
    elimination_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "outcome": self.outcome.value,
        }
        if self.final_score is not None:
            d["final_score"] = self.final_score
        if self.elimination_turn is not None:
            d["elimination_turn"] = self.elimination_turn
        if self.elimination_reason:
            d["elimination_reason"] = self.elimination_reason
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlayerResult:
        return cls(
            player_id=d["player_id"],
            player_name=d["player_name"],
            outcome=GameOutcome(d["outcome"]),
            final_score=d.get("final_score"),
            elimination_turn=d.get("elimination_turn"),
            elimination_reason=d.get("elimination_reason"),
        )


@dataclass
class GameTrace:
    """
    Complete trace of a game from start to finish.

    This is the top-level container for all game dynamics data.

    Attributes:
        metadata: Game identification and configuration
        turns: Sequence of turn records
        results: Final results for each player
        total_turns: Total number of turns played
        winner: Name of the winner (or None for draw)
        is_draw: Whether the game ended in a draw
    """

    metadata: GameMetadata
    turns: list[TurnRecord] = field(default_factory=list)
    results: list[PlayerResult] = field(default_factory=list)
    winner: str | None = None
    is_draw: bool = False

    @property
    def total_turns(self) -> int:
        return len(self.turns)

    @property
    def game_id(self) -> str:
        return self.metadata.game_id

    @property
    def game_type(self) -> str:
        return self.metadata.game_type

    def add_turn(self, turn: TurnRecord) -> None:
        """Add a turn record to the trace."""
        self.turns.append(turn)

    def get_player_actions(self, player_name: str) -> list[PlayerAction]:
        """Get all actions taken by a specific player."""
        actions = []
        for turn in self.turns:
            for action in turn.actions:
                if action.player_name == player_name:
                    actions.append(action)
        return actions

    def get_state_action_pairs(
        self, player_name: str
    ) -> list[tuple[dict, str | list | dict]]:
        """
        Get (state, action) pairs for a specific player.

        This is the key data for strategy inference:
        - state: The game state when the player made their decision
        - action: What action they chose

        Returns:
            List of (state_dict, action) tuples
        """
        # TODO(battlesnake): BattleSnake inferred actions are currently attached to the
        # TurnRecord for turn t+1, even though PlayerAction.turn == t. That means this
        # convenience method (which pairs state+action from the same TurnRecord) can be
        # off-by-one for BattleSnake. Fix in the BattleSnake trace parser by attaching
        # inferred actions to TurnRecord(t), or add a separate decision-aligned accessor.
        pairs = []
        for turn in self.turns:
            player_state = turn.player_states.get(player_name, turn.state)
            for action in turn.actions:
                if action.player_name == player_name:
                    pairs.append((player_state, action.action))
        return pairs

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "turns": [t.to_dict() for t in self.turns],
            "results": [r.to_dict() for r in self.results],
            "winner": self.winner,
            "is_draw": self.is_draw,
            "total_turns": self.total_turns,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GameTrace:
        return cls(
            metadata=GameMetadata.from_dict(d["metadata"]),
            turns=[TurnRecord.from_dict(t) for t in d.get("turns", [])],
            results=[PlayerResult.from_dict(r) for r in d.get("results", [])],
            winner=d.get("winner"),
            is_draw=d.get("is_draw", False),
        )


# =============================================================================
# Game-Specific State Schemas
# =============================================================================

"""
Each game type defines its state schema. These serve as documentation
and can be used for validation.

The state dict in TurnRecord should conform to the game's schema.
"""


BATTLESNAKE_STATE_SCHEMA = {
    "description": "BattleSnake game state",
    "fields": {
        "board": {
            "width": "int - Board width",
            "height": "int - Board height",
            "food": "list[Coord] - Food locations",
            "hazards": "list[Coord] - Hazard locations",
            "snakes": "list[Snake] - All snakes on the board",
        },
        "game": {
            "id": "str - Game ID",
            "ruleset": "dict - Game rules",
            "timeout": "int - Move timeout in ms",
        },
    },
    "snake_fields": {
        "id": "str - Snake ID",
        "name": "str - Snake name",
        "health": "int - Current health (0-100)",
        "body": "list[Coord] - Body segments, head first",
        "head": "Coord - Head position",
        "length": "int - Total length",
        "latency": "str - Response latency",
    },
    "action_format": "str - One of: 'up', 'down', 'left', 'right'",
    "valid_actions": ["up", "down", "left", "right"],
}


COREWAR_STATE_SCHEMA = {
    "description": "CoreWar game state",
    "fields": {
        "memory": "list[Instruction] - The memory array (circular)",
        "warriors": "list[Warrior] - Active warriors",
        "cycle": "int - Current cycle number",
    },
    "warrior_fields": {
        "id": "str - Warrior ID",
        "name": "str - Warrior name",
        "processes": "list[int] - Process queue (instruction pointers)",
        "alive": "bool - Whether warrior is still alive",
    },
    "action_format": "Instruction execution is deterministic based on memory state",
    "note": "CoreWar is largely deterministic - the 'action' is the program itself",
}


HALITE_STATE_SCHEMA = {
    "description": "Halite game state",
    "fields": {
        "turn": "int - Current turn",
        "map": {
            "width": "int",
            "height": "int",
            "cells": "list[list[int]] - Halite amount at each cell",
        },
        "players": "list[Player] - All players",
    },
    "player_fields": {
        "id": "str - Player ID",
        "halite": "int - Stored halite",
        "ships": "dict[ship_id, Ship] - Player's ships",
        "shipyard": "Coord | None - Shipyard location",
        "dropoffs": "list[Coord] - Dropoff locations",
    },
    "ship_fields": {
        "id": "str - Ship ID",
        "position": "Coord - Current position",
        "halite": "int - Carried halite",
    },
    "action_format": "dict - {ship_id: 'move_direction' | 'collect' | 'convert', ...}",
    "valid_ship_actions": ["n", "s", "e", "w", "o", "collect", "convert"],
}


ROBOCODE_STATE_SCHEMA = {
    "description": "RoboCode game state",
    "note": "RoboCode is event-driven, not turn-based. State captured at tick intervals.",
    "fields": {
        "tick": "int - Current game tick",
        "robots": "list[Robot] - All robots in the arena",
        "bullets": "list[Bullet] - Active bullets",
    },
    "robot_fields": {
        "name": "str - Robot name",
        "x": "float - X position",
        "y": "float - Y position",
        "heading": "float - Body heading in degrees",
        "gun_heading": "float - Gun heading",
        "radar_heading": "float - Radar heading",
        "energy": "float - Current energy",
        "velocity": "float - Current velocity",
        "gun_heat": "float - Gun heat (can't fire if > 0)",
    },
    "action_format": "Complex - multiple concurrent actions (move, turn, fire, scan)",
}


ROBOTRUMBLE_STATE_SCHEMA = {
    "description": "Robot Rumble game state",
    "fields": {
        "turn": "int - Current turn",
        "grid": {
            "width": "int",
            "height": "int",
        },
        "robots": "dict[team, list[Robot]] - Robots by team",
    },
    "robot_fields": {
        "id": "int - Robot ID",
        "team": "str - Team name",
        "coords": "Coord - Current position",
        "health": "int - Current health",
    },
    "action_format": "dict - {'type': 'move'|'attack', 'direction': Coord}",
}


HUSKYBENCH_STATE_SCHEMA = {
    "description": "HuskyBench (Poker) game state - reconstructed player view at each decision point",
    "fields": {
        "game_id": "str - Unique hand identifier",
        "hand_number": "int - Which hand in the simulation",
        "round": "str - 'preflop', 'flop', 'turn', 'river'",
        "position": "str - 'small_blind', 'big_blind'",
        "hole_cards": "list[str] - Player's private cards (e.g. ['7h', '9s'])",
        "community_cards": "list[str] - Visible community cards (sliced by round)",
        "pot": "int - Current pot size",
        "current_bet": "int - Amount needed to call",
        "my_stack": "int - Player's remaining chips",
        "opponent_stacks": "list[int] - Opponents' remaining chips",
        "blinds": "dict - {'small': int, 'big': int}",
        "action_history": "list[dict] - Previous actions: {'player': 'you'|'opponent', 'action': str, 'amount': int}",
    },
    "action_format": "str - 'FOLD', 'CHECK', 'CALL', or 'RAISE:<ratio>' where ratio = amount/player_stack in (0, 1]",
    "valid_actions": ["FOLD", "CHECK", "CALL", "RAISE:<ratio>"],
    "raise_ratio": {
        "description": "Raise as fraction of player's stack committed",
        "range": "(0, 1] — 1.0 means all-in",
        "format": "RAISE:0.2500 (4 decimal places)",
    },
}


# Registry of state schemas
STATE_SCHEMAS = {
    "BattleSnake": BATTLESNAKE_STATE_SCHEMA,
    "CoreWar": COREWAR_STATE_SCHEMA,
    "Halite": HALITE_STATE_SCHEMA,
    "RoboCode": ROBOCODE_STATE_SCHEMA,
    "RobotRumble": ROBOTRUMBLE_STATE_SCHEMA,
    "HuskyBench": HUSKYBENCH_STATE_SCHEMA,
}
