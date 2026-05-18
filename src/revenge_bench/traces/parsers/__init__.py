"""
Game-specific trace parsers.

Each game has its own output format from the game engine.
These parsers convert native formats to our unified GameTrace format.

Also provides game-specific utility functions for action/state handling:
- normalize_action(): Convert to canonical format
- actions_equal(): Compare two actions (BattleSnake, RobotRumble)
- actions_distance(): Compute normalized distance between actions (Halite, Halite3)
"""

from revenge_bench.traces.parsers.battlesnake import (
    VALID_ACTIONS as BATTLESNAKE_VALID_ACTIONS,
)
from revenge_bench.traces.parsers.battlesnake import (
    BattleSnakeTraceParser,
    parse_battlesnake_trace,
)
from revenge_bench.traces.parsers.battlesnake import (
    actions_equal as battlesnake_actions_equal,
)
from revenge_bench.traces.parsers.battlesnake import (
    # Action/state utilities
    normalize_action as battlesnake_normalize_action,
)
from revenge_bench.traces.parsers.halite import (
    MOVE_NAMES as HALITE_MOVE_NAMES,
)
from revenge_bench.traces.parsers.halite import (
    VALID_MOVES as HALITE_VALID_MOVES,
)
from revenge_bench.traces.parsers.halite import (
    HaliteTraceParser,
    parse_halite_trace,
)
from revenge_bench.traces.parsers.halite import (
    actions_distance as halite_actions_distance,
)
from revenge_bench.traces.parsers.halite import (
    # Action/state utilities
    normalize_action as halite_normalize_action,
)
from revenge_bench.traces.parsers.halite3 import (
    VALID_ACTION_TYPES as HALITE3_VALID_ACTION_TYPES,
)
from revenge_bench.traces.parsers.halite3 import (
    VALID_DIRECTIONS as HALITE3_VALID_DIRECTIONS,
)
from revenge_bench.traces.parsers.halite3 import (
    Halite3TraceParser,
    parse_halite3_trace,
)
from revenge_bench.traces.parsers.halite3 import (
    actions_distance as halite3_actions_distance,
)
from revenge_bench.traces.parsers.halite3 import (
    # Action/state utilities
    normalize_action as halite3_normalize_action,
)
from revenge_bench.traces.parsers.huskybench import (
    VALID_ACTIONS as HUSKYBENCH_VALID_ACTIONS,
)
from revenge_bench.traces.parsers.huskybench import (
    HuskyBenchTraceParser,
    parse_huskybench_trace,
)
from revenge_bench.traces.parsers.huskybench import (
    actions_distance as huskybench_actions_distance,
)
from revenge_bench.traces.parsers.huskybench import (
    # Action/state utilities
    normalize_action as huskybench_normalize_action,
)
from revenge_bench.traces.parsers.robocode import (
    ACTION_COMPONENTS as ROBOCODE_ACTION_COMPONENTS,
)
from revenge_bench.traces.parsers.robocode import (
    RoboCodeTraceParser,
    parse_robocode_trace,
)
from revenge_bench.traces.parsers.robocode import (
    actions_distance as robocode_actions_distance,
)
from revenge_bench.traces.parsers.robocode import (
    # Action/state utilities
    normalize_action as robocode_normalize_action,
)
from revenge_bench.traces.parsers.robotrumble import (
    TEAMS as ROBOTRUMBLE_TEAMS,
)
from revenge_bench.traces.parsers.robotrumble import (
    VALID_ACTION_TYPES as ROBOTRUMBLE_VALID_ACTION_TYPES,
)
from revenge_bench.traces.parsers.robotrumble import (
    VALID_DIRECTIONS as ROBOTRUMBLE_VALID_DIRECTIONS,
)
from revenge_bench.traces.parsers.robotrumble import (
    RobotRumbleTraceParser,
    parse_robotrumble_trace,
)
from revenge_bench.traces.parsers.robotrumble import (
    actions_distance as robotrumble_actions_distance,
)
from revenge_bench.traces.parsers.robotrumble import (
    actions_equal as robotrumble_actions_equal,
)
from revenge_bench.traces.parsers.robotrumble import (
    compute_state_distance as robotrumble_state_distance,
)
from revenge_bench.traces.parsers.robotrumble import (
    extract_state_action_pairs as robotrumble_extract_state_action_pairs,
)
from revenge_bench.traces.parsers.robotrumble import (
    # Action/state utilities
    normalize_action as robotrumble_normalize_action,
)

__all__ = [
    # BattleSnake
    "BattleSnakeTraceParser",
    "parse_battlesnake_trace",
    "battlesnake_normalize_action",
    "battlesnake_actions_equal",
    "BATTLESNAKE_VALID_ACTIONS",
    # RobotRumble
    "RobotRumbleTraceParser",
    "parse_robotrumble_trace",
    "robotrumble_normalize_action",
    "robotrumble_actions_equal",
    "robotrumble_actions_distance",
    "robotrumble_state_distance",
    "robotrumble_extract_state_action_pairs",
    "ROBOTRUMBLE_VALID_DIRECTIONS",
    "ROBOTRUMBLE_VALID_ACTION_TYPES",
    "ROBOTRUMBLE_TEAMS",
    # Halite (original)
    "HaliteTraceParser",
    "parse_halite_trace",
    "halite_normalize_action",
    "halite_actions_distance",
    "HALITE_VALID_MOVES",
    "HALITE_MOVE_NAMES",
    # Halite3
    "Halite3TraceParser",
    "parse_halite3_trace",
    "halite3_normalize_action",
    "halite3_actions_distance",
    "HALITE3_VALID_DIRECTIONS",
    "HALITE3_VALID_ACTION_TYPES",
    # HuskyBench
    "HuskyBenchTraceParser",
    "parse_huskybench_trace",
    "huskybench_normalize_action",
    "huskybench_actions_distance",
    "HUSKYBENCH_VALID_ACTIONS",
    # RoboCode
    "RoboCodeTraceParser",
    "parse_robocode_trace",
    "robocode_normalize_action",
    "robocode_actions_distance",
    "ROBOCODE_ACTION_COMPONENTS",
    # Registry
    "TRACE_PARSERS",
    "get_parser",
]


# Registry of parsers by game type
TRACE_PARSERS = {
    "BattleSnake": BattleSnakeTraceParser,
    "RobotRumble": RobotRumbleTraceParser,
    "Halite": HaliteTraceParser,
    "Halite3": Halite3TraceParser,
    "HuskyBench": HuskyBenchTraceParser,
    "RoboCode": RoboCodeTraceParser,
}


def get_parser(game_type: str):
    """Get the trace parser for a game type."""
    if game_type not in TRACE_PARSERS:
        raise ValueError(f"No trace parser for game type: {game_type}")
    return TRACE_PARSERS[game_type]
