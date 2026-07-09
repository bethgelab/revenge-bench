"""
HuskyBench (Poker) Trace Parser

Converts HuskyBench's native JSON output format to our unified GameTrace format.

Also provides game-specific utility functions:
- normalize_action(): Convert any action format to canonical string
- actions_distance(): Compute distance between two actions
- extract_state_action_pairs(): Extract (state, action) pairs for offline evaluation

================================================================================
CANONICAL ACTION FORMAT:
================================================================================
All actions are normalized to uppercase strings:
    "FOLD", "CHECK", "CALL", "RAISE:<ratio>"

Raise ratio: amount / player_stack at time of action, in (0, 1].
    RAISE:1.0000 — all-in
    RAISE:0.5000 — half-stack raise (default when no context)
    RAISE:0.2500 — quarter-stack raise
    etc.

Input formats handled by normalize_action():
- "FOLD", "fold", "Fold" -> "FOLD"
- "RAISE" (no context) -> "RAISE:0.5000" (default)
- "RAISE:0.75" (already ratio) -> "RAISE:0.7500"
- {"action": "RAISE", "amount": 50} (with player_stack) -> "RAISE:<ratio>"
- None -> None

================================================================================
RAW FIELDS (from game engine output):
================================================================================
File format: Single JSON file per poker hand
Filename pattern: game_log_*.json

Top-level:
    - gameId: str               Unique hand identifier
    - playerNames: dict         Player ID -> player name mapping
    - blinds: dict              {"small": int, "big": int}
    - finalBoard: list[str]     All 5 community cards (e.g. ["Td", "Ts", "Kh", "Jc", "Jh"])
    - playerHands: dict         Player ID -> [card1, card2] hole cards
    - playerMoney: dict
        - initialAmount: int    Starting stack size
        - finalMoney: dict      Player ID -> final stack
        - gameScores: dict      Player ID -> profit/loss this hand
    - rounds: dict              Keyed by round index ("0"=preflop, "1"=flop, "2"=turn, "3"=river)
        - pot: int              Pot size at end of round
        - bets: dict            Player ID -> total bet this round
        - actions: dict         Player ID -> last action type
        - action_sequence: list Action-by-action log
            - player: int       Player ID
            - action: str       "RAISE"|"CALL"|"CHECK"|"FOLD"
            - amount: int       Bet/raise amount
            - timestamp: int    Unix timestamp ms
            - pot_after_action: int
            - total_pot_after_action: int

================================================================================
INFERRED/COMPUTED FIELDS (by parser):
================================================================================
    - Reconstructed player state at each decision point:
        game_id, hand_number, round, position, hole_cards,
        community_cards (sliced from finalBoard by round),
        pot, current_bet, my_stack, opponent_stacks,
        blinds, action_history

    - Raise ratio: amount / player_stack, normalized to (0, 1]

    - metadata.timestamp: datetime  Current time (engine doesn't include one)

    - results[].outcome: GameOutcome  WIN/LOSS computed from gameScores
================================================================================
"""

from __future__ import annotations

import json
import math
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

VALID_ACTIONS = ["FOLD", "CHECK", "CALL", "RAISE"]
ROUND_NAMES = {0: "preflop", 1: "flop", 2: "turn", 3: "river"}
COMMUNITY_CARDS_BY_ROUND = {0: 0, 1: 3, 2: 4, 3: 5}  # How many community cards visible


# =============================================================================
# Action Normalization & Distance
# =============================================================================

# Fallback stack used when a caller doesn't know the actor's chip stack at
# the decision point. HuskyBench games start at 10_000 chips, so this is
# the best uninformed guess.
_DEFAULT_STACK = 10_000


def _log_commitment(ratio: float, stack: float) -> float:
    """Map a raise ratio r in [0, 1] to log1p(r * stack) / log1p(stack).

    Returns a value in [0, 1] for any stack > 0. CHECK and CALL are
    treated as RAISE:0, so their commitment is 0 by construction.

    Mathematical note: log1p(r * stack) == log1p(chips) where chips is the
    original raise amount, so this function is equivalent to operating on
    raw chip amounts. We keep the ratio form for storage readability; the
    metric cancels the normalization.
    """
    return math.log1p(ratio * stack) / math.log1p(stack)


def normalize_action(action: Any, player_stack: int | float = 0) -> str | None:
    """
    Normalize a HuskyBench poker action to canonical string format.

    Canonical format:
        "FOLD", "CHECK", "CALL" — non-raise actions
        "RAISE:<ratio>"         — raise as fraction of player's stack, e.g. "RAISE:0.2500"
                                  ratio is in (0, 1]; 1.0 means all-in.

    Input formats:
        - "FOLD", "fold", "Fold"                     -> "FOLD"
        - "CHECK", "CALL"                             -> "CHECK", "CALL"
        - "RAISE" (no context)                        -> "RAISE:0.5000" (default midpoint)
        - "RAISE:0.75" (already ratio string)         -> "RAISE:0.7500"
        - {"action": "RAISE", "amount": 50,
           player_stack=200}                          -> "RAISE:0.2500"
        - None                                        -> None

    Args:
        action: Raw action in any supported format.
        player_stack: Player's stack before the action (used to compute raise ratio).
                      When 0 and action is a plain "RAISE", defaults to 0.5.

    Returns:
        Canonical action string or None if invalid.
    """
    if action is None:
        return None

    # Handle dict format {"action": "RAISE", "amount": 50}
    if isinstance(action, dict):
        action_type = action.get("action", "").upper()
        amount = action.get("amount", 0)

        if action_type == "RAISE":
            if player_stack > 0:
                ratio = min(amount / player_stack, 1.0)
            else:
                ratio = 0.5
            return f"RAISE:{ratio:.4f}"
        if action_type in ("FOLD", "CHECK", "CALL"):
            return action_type
        return None

    if isinstance(action, str):
        upper = action.upper()

        if upper in ("FOLD", "CHECK", "CALL"):
            return upper

        if upper == "RAISE":
            return "RAISE:0.5000"

        # Already in ratio format: "RAISE:0.75"
        if upper.startswith("RAISE:"):
            suffix = upper[6:]  # everything after "RAISE:"
            try:
                ratio = float(suffix)
                return f"RAISE:{ratio:.4f}"
            except ValueError:
                return None  # "RAISE:SMALL", "RAISE:MEDIUM" etc. are no longer valid

        return None

    return None


def actions_distance(
    a1: Any,
    a2: Any,
    player_stack: int | float | None = None,
) -> float:
    """
    Compute the distance between two HuskyBench poker actions.

    Returns a float in [0, 1] where 0 means identical and 1 means maximally different.

    Rules:
        FOLD                     — distance 1.0 from everything except itself
        CHECK / CALL             — passive; treated as RAISE:0 (zero commitment)
        RAISE:<ratio>            — ratio ∈ (0, 1] fraction of the actor's stack

    Raise distance is log-normalized per the actor's stack S at the decision
    point. Define c(r; S) = log1p(r * S) / log1p(S). Then:
        raise-vs-raise:    |c(r1; S) - c(r2; S)|
        raise-vs-passive:  c(r; S)             (passive == RAISE:0 -> c(0; S) = 0)

    The log scale compresses large raises and separates small ones, so a
    1%-of-stack raise is meaningfully different from CHECK/CALL. Normalizing
    by log1p(S) — rather than a constant — guarantees the [0, 1] range
    holds in every state: an all-in is always distance 1 from CHECK, even
    on a short stack.

    Mathematical aside: log1p(r * S) == log1p(chips). The ratio
    normalization cancels inside the metric, but we keep RAISE:<ratio> as
    the canonical string form for readability.

    Args:
        a1, a2: Action strings in canonical form.
        player_stack: Actor's chip stack at the decision point. Both
            actions must be at the same decision (same state, same stack).
            If None, falls back to 10_000 (HuskyBench's initial stack),
            which is exact for early-hand states and a mild approximation
            for short-stack states.

    Other cases:
        FOLD vs FOLD:              0.0
        FOLD vs anything else:     1.0
        CHECK vs CALL:             0.0  (dead branch: mutually exclusive in a state)
        Either input None/invalid: 1.0

    Examples (stack = 10_000 unless noted):
        actions_distance("FOLD", "FOLD")                          -> 0.0
        actions_distance("FOLD", "CHECK")                         -> 1.0
        actions_distance("CHECK", "CALL")                         -> 0.0
        actions_distance("RAISE:0.25", "CHECK")                   -> ~0.8495
        actions_distance("RAISE:0.25", "RAISE:0.75")              -> ~0.1193
        actions_distance("RAISE:1.0",  "RAISE:0.0")               -> 1.0
        actions_distance("RAISE:0.5",  "FOLD")                    -> 1.0
        actions_distance("RAISE:1.0",  "CHECK", player_stack=100) -> 1.0
        actions_distance(None, "FOLD")                            -> 1.0
    """
    n1 = normalize_action(a1)
    n2 = normalize_action(a2)

    if n1 is None or n2 is None:
        return 1.0

    is_raise1 = n1.startswith("RAISE:")
    is_raise2 = n2.startswith("RAISE:")
    is_fold1 = n1 == "FOLD"
    is_fold2 = n2 == "FOLD"

    # FOLD vs FOLD
    if is_fold1 and is_fold2:
        return 0.0

    # FOLD vs anything else
    if is_fold1 or is_fold2:
        return 1.0

    stack = float(player_stack) if player_stack is not None else float(_DEFAULT_STACK)

    # Both raises
    if is_raise1 and is_raise2:
        return abs(
            _log_commitment(float(n1[6:]), stack)
            - _log_commitment(float(n2[6:]), stack)
        )

    # Raise vs passive (CHECK/CALL treated as RAISE:0)
    if is_raise1:
        return _log_commitment(float(n1[6:]), stack)
    if is_raise2:
        return _log_commitment(float(n2[6:]), stack)

    # Both passive (CHECK vs CALL — dead branch in same-state comparison)
    return 0.0


# =============================================================================
# State Reconstruction
# =============================================================================


def _reconstruct_state_at_action(
    hand_data: dict,
    action_idx: int,
    round_idx: int,
    player_id: str,
    player_name: str,
    hand_number: int = 0,
) -> dict:
    """
    Reconstruct the game state visible to a player at a specific action point.

    Args:
        hand_data: Full hand JSON data.
        action_idx: Index into the round's action_sequence.
        round_idx: Betting round (0=preflop, 1=flop, 2=turn, 3=river).
        player_id: The player's ID (as string).
        player_name: The player's display name.
        hand_number: Which hand in the simulation.

    Returns:
        Reconstructed state dict from the player's perspective.
    """
    player_names = hand_data.get("playerNames", {})
    blinds = hand_data.get("blinds", {"small": 5, "big": 10})
    final_board = hand_data.get("finalBoard", [])
    player_hands = hand_data.get("playerHands", {})
    player_money = hand_data.get("playerMoney", {})
    initial_amount = player_money.get("initialAmount", 10000)

    # Community cards visible at this round
    num_visible = COMMUNITY_CARDS_BY_ROUND.get(round_idx, 0)
    community_cards = final_board[:num_visible]

    # Hole cards for this player
    hole_cards = player_hands.get(str(player_id), [])

    # Determine position from player order in action_sequence
    # The first player to act preflop is typically the small blind
    all_player_ids = list(player_names.keys())
    if str(player_id) == all_player_ids[0]:
        position = "small_blind"
    else:
        position = "big_blind"

    # Build action history and compute pot/stacks from all actions up to this point
    action_history = []
    cumulative_bets = {pid: 0 for pid in player_names}
    pot = 0

    # Process all previous rounds fully
    for prev_round_idx in range(round_idx):
        round_key = str(prev_round_idx)
        round_data = hand_data.get("rounds", {}).get(round_key, {})
        for seq_action in round_data.get("action_sequence", []):
            acting_pid = str(seq_action.get("player", ""))
            action_type = seq_action.get("action", "")
            amount = seq_action.get("amount", 0)

            if acting_pid == str(player_id):
                label = "you"
            else:
                label = "opponent"

            action_history.append(
                {
                    "player": label,
                    "action": action_type,
                    "amount": amount,
                }
            )

            cumulative_bets[acting_pid] = cumulative_bets.get(acting_pid, 0) + amount

    # Process current round up to (but not including) the current action
    current_round_key = str(round_idx)
    current_round_data = hand_data.get("rounds", {}).get(current_round_key, {})
    current_sequence = current_round_data.get("action_sequence", [])

    for i in range(action_idx):
        seq_action = current_sequence[i]
        acting_pid = str(seq_action.get("player", ""))
        action_type = seq_action.get("action", "")
        amount = seq_action.get("amount", 0)

        if acting_pid == str(player_id):
            label = "you"
        else:
            label = "opponent"

        action_history.append(
            {
                "player": label,
                "action": action_type,
                "amount": amount,
            }
        )

        cumulative_bets[acting_pid] = cumulative_bets.get(acting_pid, 0) + amount

    # Compute pot and stacks
    pot = sum(cumulative_bets.values())
    my_stack = initial_amount - cumulative_bets.get(str(player_id), 0)
    opponent_stacks = [
        initial_amount - cumulative_bets.get(pid, 0)
        for pid in player_names
        if pid != str(player_id)
    ]

    # Compute current bet to call
    # NOTE: In preflop, blind-posting is already recorded as RAISE actions in
    # action_sequence, so we must NOT add blinds again.
    max_bet_this_round = 0
    my_bet_this_round = 0
    round_bets = {}
    for i in range(action_idx):
        seq_action = current_sequence[i]
        acting_pid = str(seq_action.get("player", ""))
        amount = seq_action.get("amount", 0)
        round_bets[acting_pid] = round_bets.get(acting_pid, 0) + amount

    max_bet_this_round = max(round_bets.values()) if round_bets else 0
    my_bet_this_round = round_bets.get(str(player_id), 0)
    current_bet = max(0, max_bet_this_round - my_bet_this_round)

    return {
        "game_id": hand_data.get("gameId", ""),
        "hand_number": hand_number,
        "round": ROUND_NAMES.get(round_idx, f"round_{round_idx}"),
        "position": position,
        "hole_cards": hole_cards,
        "community_cards": community_cards,
        "pot": pot,
        "current_bet": current_bet,
        "my_stack": my_stack,
        "opponent_stacks": opponent_stacks,
        "blinds": blinds,
        "action_history": action_history,
    }


# =============================================================================
# State-Action Pair Extraction (for offline evaluation)
# =============================================================================


def extract_state_action_pairs(
    sim_file: Path | str, player_name: str
) -> list[tuple[dict, str]]:
    """
    Extract all (state, action) pairs for a player from a HuskyBench game log.

    Each individual action the player takes becomes one pair. The state is
    reconstructed to only contain information visible at that decision point
    (no future community cards, no opponent hole cards).

    Args:
        sim_file: Path to game_log_*.json file.
        player_name: Player selector to extract data for. Supported selectors:
            - Display name from ``playerNames`` (e.g. ``"target"``)
            - Raw ``playerNames`` key / action-sequence ID (e.g. ``"1309437543"``)
            - Connected client ID from logs (e.g. ``"1309437544"``), which is
              mapped to anonymized names like ``"player1309437544"`` when present.

    Returns:
        List of (state, action) tuples where:
        - state: Reconstructed game state from the player's perspective
        - action: Canonical action string ("FOLD", "CHECK", "CALL", "RAISE:0.2500", etc.)
    """
    with open(sim_file) as f:
        hand_data = json.load(f)

    player_names = hand_data.get("playerNames", {})

    # Resolve this player's internal action-sequence ID.
    selector = str(player_name)
    player_id = None

    # 1) Exact match on internal player ID key.
    if selector in player_names:
        player_id = selector

    # 2) Exact match on display name.
    if player_id is None:
        for pid, name in player_names.items():
            if name == selector:
                player_id = pid
                break

    # 3) Connected client ID fallback used by HuskyBench logs.
    #    In anonymized traces, playerNames can look like:
    #    {"1309437543": "player1309437544"} where connected_id == 1309437544.
    if player_id is None and selector.isdigit():
        connected_name = f"player{selector}"
        for pid, name in player_names.items():
            if name == connected_name:
                player_id = pid
                break

    # 4) Off-by-one fallback (some formats encode connected_id-1 as action ID key).
    if player_id is None and selector.isdigit():
        maybe_internal = str(int(selector) - 1)
        if maybe_internal in player_names:
            player_id = maybe_internal

    if player_id is None:
        return []

    pairs = []
    rounds = hand_data.get("rounds", {})

    for round_key in sorted(rounds.keys(), key=int):
        round_idx = int(round_key)
        round_data = rounds[round_key]
        action_sequence = round_data.get("action_sequence", [])

        for action_idx, seq_action in enumerate(action_sequence):
            acting_pid = str(seq_action.get("player", ""))

            if acting_pid != str(player_id):
                continue

            # Reconstruct state at this decision point
            state = _reconstruct_state_at_action(
                hand_data=hand_data,
                action_idx=action_idx,
                round_idx=round_idx,
                player_id=player_id,
                player_name=player_name,
            )

            # Normalize the action using stack-relative ratio for raises
            raw_action = seq_action.get("action", "")
            amount = seq_action.get("amount", 0)
            my_stack = state["my_stack"]

            if raw_action.upper() == "RAISE":
                action = normalize_action(
                    {"action": raw_action, "amount": amount},
                    player_stack=my_stack,
                )
            else:
                action = normalize_action(raw_action)

            if action is None:
                continue

            pairs.append((state, action))

    return pairs


# =============================================================================
# Trace Parser
# =============================================================================


class HuskyBenchTraceParser:
    """
    Parser for HuskyBench's native JSON output format (one file per poker hand).

    Usage:
        parser = HuskyBenchTraceParser()
        trace = parser.parse_file("game_log_0_abc123.json")
    """

    GAME_TYPE = "HuskyBench"

    def __init__(self, player_names: dict[str, str] | None = None):
        """
        Initialize the parser.

        Args:
            player_names: Optional mapping of player IDs to display names.
                         If not provided, uses names from the game log.
        """
        self.player_names = player_names or {}

    def parse_file(self, path: str | Path, source: dict | None = None) -> GameTrace:
        """Parse a HuskyBench JSON game log file."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return self.parse_content(content, source=source)

    def parse_content(self, content: str, source: dict | None = None) -> GameTrace:
        """Parse JSON content from HuskyBench."""
        data = json.loads(content)
        return self._parse_data(data, source)

    def parse_data(self, data: dict, source: dict | None = None) -> GameTrace:
        """Parse a HuskyBench data dictionary directly."""
        return self._parse_data(data, source)

    def _parse_data(self, data: dict, source: dict | None = None) -> GameTrace:
        """Internal parsing logic."""
        game_id = data.get("gameId", "unknown")
        player_names_map = data.get("playerNames", {})
        blinds = data.get("blinds", {"small": 5, "big": 10})
        player_money = data.get("playerMoney", {})
        game_scores = player_money.get("gameScores", {})
        final_money = player_money.get("finalMoney", {})
        rounds_data = data.get("rounds", {})

        # Override player names if provided
        for pid, name in self.player_names.items():
            if pid in player_names_map:
                player_names_map[pid] = name

        # Build player list
        players = [{"id": pid, "name": name} for pid, name in player_names_map.items()]

        # Determine winner by highest gameScore
        is_draw = False
        winner_name = None
        if game_scores:
            max_score = max(game_scores.values())
            winners = [pid for pid, s in game_scores.items() if s == max_score]
            if len(winners) == 1:
                winner_name = player_names_map.get(winners[0])
            elif max_score == 0:
                is_draw = True
            else:
                is_draw = True

        metadata = GameMetadata(
            game_id=game_id,
            game_type=self.GAME_TYPE,
            timestamp=datetime.now(),
            players=players,
            config={
                "blinds": blinds,
            },
            source=source or {},
        )

        # Parse each betting round as a turn
        turns = []
        for round_key in sorted(rounds_data.keys(), key=int):
            round_idx = int(round_key)
            round_data = rounds_data[round_key]
            turn_record = self._parse_round(
                data, round_idx, round_data, player_names_map
            )
            turns.append(turn_record)

        # Build results
        results = []
        for pid, name in player_names_map.items():
            game_scores.get(pid, 0)
            if name == winner_name:
                outcome = GameOutcome.WIN
            elif is_draw:
                outcome = GameOutcome.DRAW
            else:
                outcome = GameOutcome.LOSS

            results.append(
                PlayerResult(
                    player_id=pid,
                    player_name=name,
                    outcome=outcome,
                    final_score=float(final_money.get(pid, 0)),
                )
            )

        return GameTrace(
            metadata=metadata,
            turns=turns,
            results=results,
            winner=winner_name,
            is_draw=is_draw,
        )

    def _parse_round(
        self,
        hand_data: dict,
        round_idx: int,
        round_data: dict,
        player_names_map: dict,
    ) -> TurnRecord:
        """Parse a single betting round into a TurnRecord."""
        final_board = hand_data.get("finalBoard", [])
        num_visible = COMMUNITY_CARDS_BY_ROUND.get(round_idx, 0)
        community_cards = final_board[:num_visible]

        state = {
            "round": ROUND_NAMES.get(round_idx, f"round_{round_idx}"),
            "round_index": round_idx,
            "community_cards": community_cards,
            "pot": round_data.get("pot", 0),
            "bets": round_data.get("bets", {}),
        }

        # Build per-player states
        player_states = {}
        for pid, name in player_names_map.items():
            player_hands = hand_data.get("playerHands", {})
            player_states[name] = {
                "round": ROUND_NAMES.get(round_idx, f"round_{round_idx}"),
                "hole_cards": player_hands.get(pid, []),
                "community_cards": community_cards,
                "pot": round_data.get("pot", 0),
            }

        # Parse actions from action_sequence
        initial_amount = hand_data.get("playerMoney", {}).get("initialAmount", 10000)
        # Track cumulative bets within this round to approximate stack at each action
        cumulative_round_bets: dict[str, int | float] = {}
        actions = []
        action_sequence = round_data.get("action_sequence", [])
        for seq_action in action_sequence:
            acting_pid = str(seq_action.get("player", ""))
            name = player_names_map.get(acting_pid, acting_pid)
            raw_action = seq_action.get("action", "")
            amount = seq_action.get("amount", 0)

            # Approximate stack before this action using round bets seen so far
            spent_this_round = cumulative_round_bets.get(acting_pid, 0)
            round_bets_summary = round_data.get("bets", {})
            total_spent = round_bets_summary.get(acting_pid, spent_this_round)
            player_stack = initial_amount - total_spent

            canonical = (
                normalize_action(raw_action, player_stack=player_stack)
                if raw_action.upper() == "RAISE"
                else normalize_action(raw_action)
            )

            cumulative_round_bets[acting_pid] = spent_this_round + amount

            actions.append(
                PlayerAction(
                    player_id=acting_pid,
                    player_name=name,
                    turn=round_idx,
                    action=canonical or raw_action.upper(),
                    action_type="bet",
                    valid_actions=VALID_ACTIONS.copy(),
                )
            )

        return TurnRecord(
            turn=round_idx,
            state=state,
            actions=actions,
            player_states=player_states,
        )


def parse_huskybench_trace(path: str | Path, **kwargs) -> GameTrace:
    """Convenience function to parse a HuskyBench trace file."""
    return HuskyBenchTraceParser(**kwargs).parse_file(path)
