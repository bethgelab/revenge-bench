from typing import List, Tuple
import random
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

# ----------------- Simple utility helpers ----------------- #

RANK_ORDER = "23456789TJQKA"
RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER, start=2)}

def card_rank(card: str) -> str:
    # Card like "As" or "Td"
    return card[0]

def card_suit(card: str) -> str:
    return card[1]

def preflop_strength(cards: List[str]) -> int:
    """
    Very rough strength categorisation:
    returns 3 (premium), 2 (strong), 1 (medium), 0 (weak)
    """
    r1, r2 = card_rank(cards[0]), card_rank(cards[1])
    s1, s2 = card_suit(cards[0]), card_suit(cards[1])
    pair = r1 == r2
    suited = s1 == s2
    high1 = RANK_VALUE[r1] >= RANK_VALUE['T']
    high2 = RANK_VALUE[r2] >= RANK_VALUE['T']

    # Pocket premiums or AK
    if pair and RANK_VALUE[r1] >= RANK_VALUE['J']:
        return 3
    if {r1, r2} == {'A', 'K'}:
        return 3 if suited else 2
    if pair and RANK_VALUE[r1] >= RANK_VALUE['9']:
        return 2
    # suited broadway combos
    if suited and high1 and high2:
        return 2
    # any two high cards
    if high1 and high2:
        return 1
    # small pair
    if pair:
        return 1
    return 0

# ----------------- Very light post-flop hand helper ----------------- #

def have_pair_or_better(hole_cards: List[str], community_cards: List[str]) -> bool:
    """
    Detects if we have at least a pair that includes one of our hole cards.
    Extremely cheap: counts ranks only.
    """
    ranks = [card_rank(c) for c in hole_cards + community_cards]
    for r in set(ranks):
        if ranks.count(r) >= 2 and any(card_rank(h) == r for h in hole_cards):
            return True
    return False

# ----------------- Player class ----------------- #

class SimplePlayer(Bot):
    """
    Very small-footprint bot with a handful of heuristic rules.

    â¢ Pre-flop: plays a tight-aggressive range, willing to 3-bet premium hands.
    â¢ Post-flop: fit-or-fold. It will call small bets for favourable pot-odds
      and occasionally bluff when checked to.
    """

    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []

    # ------------ Game lifecycle callbacks ------------ #

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int,
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.hole_cards = player_hands  # store private cards

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass  # no-op

    # ----------------- Decision helpers ----------------- #

    def _preflop_action(self, round_state: RoundStateClient, to_call: int, min_raise: int,
                        max_raise: int, remaining_chips: int, someone_raised: bool) -> Tuple[PokerAction, int]:
        strength = preflop_strength(self.hole_cards)

        # No bet to us
        if to_call == 0:
            # Open raise with good hands
            if strength >= 2 and not someone_raised:
                raise_amount = min(max(min_raise * 2, min_raise), max_raise, remaining_chips)
                if raise_amount >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.RAISE, raise_amount
            # 5 % random steal attempt
            if random.random() < 0.05:
                raise_amount = min(min_raise, remaining_chips)
                return (PokerAction.RAISE if raise_amount < remaining_chips else PokerAction.ALL_IN,
                        raise_amount)
            return PokerAction.CHECK, 0

        # Facing a bet
        if strength >= 1 and to_call <= remaining_chips * 0.5:
            # Occasionally 3-bet with premiums
            if strength == 3 and random.random() < 0.35 and remaining_chips > to_call + min_raise:
                raise_amount = min(to_call + min_raise, max_raise, remaining_chips)
                if raise_amount >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.RAISE, raise_amount
            return PokerAction.CALL, 0
        return PokerAction.FOLD, 0

    def _postflop_action(self, round_state: RoundStateClient, to_call: int, min_raise: int,
                         max_raise: int, remaining_chips: int) -> Tuple[PokerAction, int]:
        made_hand = have_pair_or_better(self.hole_cards, round_state.community_cards)

        # If no bet, decide whether to bet/bluff
        if to_call == 0:
            # Value bet or bluff
            if made_hand and random.random() < 0.4:
                raise_amount = min(min_raise, remaining_chips)
                return (PokerAction.RAISE if raise_amount < remaining_chips else PokerAction.ALL_IN,
                        raise_amount)
            if not made_hand and random.random() < 0.06:
                raise_amount = min(min_raise, remaining_chips)
                return (PokerAction.RAISE if raise_amount < remaining_chips else PokerAction.ALL_IN,
                        raise_amount)
            return PokerAction.CHECK, 0

        pot = round_state.pot
        pot_odds = to_call / (pot + to_call) if pot + to_call > 0 else 1.0

        # If we have a made hand, be willing to continue more often
        if made_hand and to_call <= remaining_chips * 0.5:
            # Small chance to raise for value
            if random.random() < 0.25 and remaining_chips > to_call + min_raise:
                raise_amount = min(to_call + min_raise, max_raise, remaining_chips)
                if raise_amount >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.RAISE, raise_amount
            return PokerAction.CALL, 0

        # Call cheap bets relative to pot and stack
        if pot_odds < 0.20 and to_call <= remaining_chips * 0.1:
            return PokerAction.CALL, 0

        # Short-stacked desperation shove
        if remaining_chips < min_raise * 8 and random.random() < 0.15:
            return PokerAction.ALL_IN, remaining_chips

        return PokerAction.FOLD, 0

    # ----------------- Public decision API ----------------- #

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        my_id_key = str(self.id) if self.id is not None else None
        my_bet = round_state.player_bets.get(my_id_key, 0)

        current_bet = round_state.current_bet
        to_call = max(0, current_bet - my_bet)
        min_raise = round_state.min_raise
        max_raise = round_state.max_raise

        # Has anyone raised this betting round?
        someone_raised = any(action == "Raise" for action in round_state.player_actions.values())

        street = round_state.round.lower()

        if street == "preflop":
            return self._preflop_action(round_state, to_call, min_raise, max_raise,
                                        remaining_chips, someone_raised)
        else:
            return self._postflop_action(round_state, to_call, min_raise, max_raise, remaining_chips)

    # ----------------- End callbacks ----------------- #

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict,
                    active_players_hands: dict):
        pass