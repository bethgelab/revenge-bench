from typing import List, Tuple, Optional
import random
import eval7

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient


class SimplePlayer(Bot):
    """
    A Monte-Carlo poker bot with pot-odds logic and a few
    round-specific tweaks:

    â¢ Pre-flop: raise more aggressively with equity > 0.65.
    â¢ Post-flop/turn: original behaviour.
    â¢ River: value-bet / shove with equity > 0.9.
    """

    def __init__(self, simulations: int = 100):
        super().__init__()
        self.simulations = simulations
        self.hole_cards: List[str] = []
        self._cached_strength: Optional[float] = None
        self._cached_board_len: int = -1

    # ---------------------------------------------------------------------
    # Helper functions
    # ---------------------------------------------------------------------
    @staticmethod
    def _cards_from_str(card_strs: List[str]) -> List[eval7.Card]:
        """Convert ['Ah', 'Ks'] -> [eval7.Card('Ah'), eval7.Card('Ks')]"""
        return [eval7.Card(c) for c in card_strs]

    def estimate_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """
        Monte-Carlo estimate of win probability against ONE opponent.
        Returns a value in [0,1].
        """
        deck = eval7.Deck()
        used_cards = self._cards_from_str(hole_cards + community_cards)
        for card in used_cards:
            deck.cards.remove(card)

        wins, ties = 0, 0
        required_board = 5 - len(community_cards)

        for _ in range(self.simulations):
            deck.shuffle()

            draw = deck.peek(required_board + 2)  # draw board + opp hole
            opp_hole = draw[:2]
            board_draw = draw[2:]

            our_hand = self._cards_from_str(hole_cards) + self._cards_from_str(community_cards) + board_draw
            opp_hand = opp_hole + self._cards_from_str(community_cards) + board_draw

            our_score = eval7.evaluate(our_hand)
            opp_score = eval7.evaluate(opp_hand)

            if our_score > opp_score:
                wins += 1
            elif our_score == opp_score:
                ties += 1
            # losses are implicit

        return (wins + ties * 0.5) / self.simulations

    # ---------------------------------------------------------------------
    # Bot interface
    # ---------------------------------------------------------------------
    def on_start(
        self,
        starting_chips: int,
        player_hands: List[str],
        blind_amount: int,
        big_blind_player_id: int,
        small_blind_player_id: int,
        all_players: List[int],
    ):
        self.hole_cards = player_hands
        self._cached_strength = None
        self._cached_board_len = -1

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self._cached_strength = None
        self._cached_board_len = -1

    # ---------------------------------------------------------------------
    # Decision logic
    # ---------------------------------------------------------------------
    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        board_len = len(round_state.community_cards)
        if self._cached_strength is None or board_len != self._cached_board_len:
            self._cached_strength = self.estimate_strength(self.hole_cards, round_state.community_cards)
            self._cached_board_len = board_len
        strength = self._cached_strength

        # Heads-up game â one opponent
        num_opponents = 1
        strength = strength ** num_opponents  # keep hook for future multi-opponent games

        my_bet = 0
        if round_state.player_bets:
            my_bet = round_state.player_bets.get(self.id, round_state.player_bets.get(str(self.id), 0))

        amount_to_call = max(round_state.current_bet - my_bet, 0)
        can_check = amount_to_call == 0
        pot_size = max(round_state.pot, 1)
        can_raise = round_state.min_raise > 0

        pot_odds = amount_to_call / (pot_size + amount_to_call) if amount_to_call > 0 else 0

        # ----------------------------------------------------------
        # PRE-FLOP adjustments (round_state.round == 'preflop')
        # ----------------------------------------------------------
        if round_state.round == 'preflop' and can_raise and remaining_chips >= round_state.min_raise:
            # Tight-aggressive: raise with solid equity
            if strength > 0.65 and random.random() < 0.9:
                desired = max(round_state.min_raise, int(pot_size * 0.75))
                raise_amount = min(desired, round_state.max_raise, remaining_chips)
                return PokerAction.RAISE, raise_amount

        # ----------------------------------------------------------
        # If we can check
        # ----------------------------------------------------------
        if can_check:
            # RIVER: strong hand â go for max value
            if round_state.round == 'river' and strength > 0.9 and can_raise:
                raise_amount = min(round_state.max_raise, remaining_chips)
                if raise_amount >= round_state.min_raise:
                    return PokerAction.RAISE, raise_amount

            # Value-bet strong hands
            if strength > 0.75 and can_raise and remaining_chips >= round_state.min_raise:
                desired = max(round_state.min_raise, int(pot_size * 0.5))
                raise_amount = min(desired, round_state.max_raise, remaining_chips)
                return PokerAction.RAISE, raise_amount

            # Semi-bluff sometimes with medium hands
            if strength > 0.55 and can_raise and random.random() < 0.15 and remaining_chips >= round_state.min_raise:
                return PokerAction.RAISE, round_state.min_raise

            return PokerAction.CHECK, 0

        # ----------------------------------------------------------
        # We are facing a bet
        # ----------------------------------------------------------
        margin = 0.02  # minimal edge to justify a call
        if strength >= pot_odds + margin:
            # Aggressive raise if we crush the pot odds
            if can_raise and strength - (pot_odds + margin) > 0.25 and remaining_chips - amount_to_call >= round_state.min_raise:
                desired = max(round_state.min_raise, int(pot_size))
                raise_amount = min(desired, round_state.max_raise, remaining_chips - amount_to_call)
                if raise_amount >= round_state.min_raise:
                    return PokerAction.RAISE, raise_amount

            return PokerAction.CALL, 0

        # Not profitable â fold
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(
        self,
        round_state: RoundStateClient,
        player_score: float,
        all_scores: dict,
        active_players_hands: dict,
    ):
        pass