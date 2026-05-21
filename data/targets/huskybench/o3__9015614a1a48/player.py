"""
HuskyBench â SimplePlayer (v2)

A very lightweight rule-based poker bot designed to be fast (no Monte-Carlo
simulation) yet stronger than the previous always-check/call behaviour.

Strategy
========
Pre-flop (round_num == 1)
-------------------------
â¢ If nobody has raised and the current bet is 0, raise 2Ã blind (or min_raise)
  with 25 % probability, otherwise check.
â¢ If facing a raise: call when the bet is â¤ 5 % of our stack, else fold.

Post-flop (round_num > 1)
-------------------------
â¢ If the pot is unopened (current_bet == 0): usually check, but bluff-bet
  min_raise 10 % of the time when affordable.
â¢ If facing a bet:
    â Call when the bet is â¤ 10 % of our stack.
    â 10 % of the time bluff-raise (current_bet + min_raise) when affordable.
    â Otherwise fold.

The bot intentionally plays small pots and occasionally applies pressure to
win uncontested pots while keeping variance low.
"""

from __future__ import annotations

import random
from typing import List, Tuple

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient


class SimplePlayer(Bot):
    def __init__(self) -> None:
        super().__init__()
        self.blind_amount: int = 0

    # ------------------------------------------------------------------ #
    # Mandatory lifecycle hooks                                          #
    # ------------------------------------------------------------------ #

    def on_start(
        self,
        starting_chips: int,
        player_hands: List[str],
        blind_amount: int,
        big_blind_player_id: int,
        small_blind_player_id: int,
        all_players: List[int],
    ) -> None:
        # Only store blind amount for later reference.
        self.blind_amount = blind_amount

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int) -> None:
        # Stateless bot â nothing to do each round.
        pass

    # ------------------------------------------------------------------ #
    # Core decision logic                                                #
    # ------------------------------------------------------------------ #

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """
        Decide on an action given the current round_state and stack.
        The bot uses only simple arithmetic and RNG â no heavy computation.
        """
        current_bet: int = round_state.current_bet
        min_raise: int = round_state.min_raise or max(1, self.blind_amount)
        max_raise: int = round_state.max_raise or remaining_chips
        stack: int = remaining_chips

        # Helper: is the current bet within a percentage of our stack?
        def bet_affordable(percentage: float) -> bool:
            return current_bet <= percentage * stack

        # ----------------------------------------------------------------
        # Pre-flop logic
        # ----------------------------------------------------------------
        if round_state.round_num == 1:
            # No bet yet â consider an opening raise.
            if current_bet == 0:
                if random.random() < 0.25 and stack >= min_raise * 2:
                    raise_amt = min(min_raise * 2, max_raise, stack)
                    return PokerAction.RAISE, raise_amt
                return PokerAction.CHECK, 0

            # Facing an open raise
            if bet_affordable(0.05):
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # ----------------------------------------------------------------
        # Post-flop logic
        # ----------------------------------------------------------------
        if current_bet == 0:
            # Optionally bluff bet
            if random.random() < 0.10 and stack >= min_raise:
                raise_amt = min_raise
                return PokerAction.RAISE, raise_amt
            return PokerAction.CHECK, 0

        # There is a bet to us
        if bet_affordable(0.10):
            return PokerAction.CALL, 0

        # Occasional bluff raise if we can afford
        if random.random() < 0.10 and stack >= current_bet + min_raise:
            raise_amt = min(current_bet + min_raise, max_raise, stack)
            return PokerAction.RAISE, raise_amt

        return PokerAction.FOLD, 0

    # ------------------------------------------------------------------ #
    # Round / game end hooks                                             #
    # ------------------------------------------------------------------ #

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int) -> None:
        pass

    def on_end_game(
        self,
        round_state: RoundStateClient,
        player_score: float,
        all_scores: dict,
        active_players_hands: dict,
    ) -> None:
        pass