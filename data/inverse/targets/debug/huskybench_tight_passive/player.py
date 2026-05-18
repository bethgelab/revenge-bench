from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

# Card rank values for hand strength estimation
RANK_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}


def _parse_card(card_str):
    """Parse a card string like '7h' into (rank_value, suit)."""
    rank = card_str[:-1]
    suit = card_str[-1]
    return RANK_VALUES.get(rank, 0), suit


def _hand_strength(hole_cards, community_cards):
    """
    Estimate hand strength as a score from 0.0 to 1.0.

    Simple heuristic based on:
    - High cards (A, K, Q, J)
    - Pairs (hole pair, or pair with board)
    - Suited cards
    - Connectedness (close ranks)

    NOTE: This function is identical to tight_passive/main.py._hand_strength().
    Any changes here must be mirrored there (and vice versa).
    """
    if not hole_cards or len(hole_cards) < 2:
        return 0.0

    r1, s1 = _parse_card(hole_cards[0])
    r2, s2 = _parse_card(hole_cards[1])

    score = 0.0

    # High card bonus
    for r in (r1, r2):
        if r >= 14:
            score += 0.25
        elif r >= 13:
            score += 0.20
        elif r >= 12:
            score += 0.15
        elif r >= 11:
            score += 0.10
        elif r >= 10:
            score += 0.05

    # Pocket pair bonus
    if r1 == r2:
        score += 0.30
        if r1 >= 11:
            score += 0.15

    # Suited bonus
    if s1 == s2:
        score += 0.05

    # Connectedness bonus
    gap = abs(r1 - r2)
    if gap == 1:
        score += 0.05
    elif gap == 2:
        score += 0.02

    # Board interaction
    all_ranks = [r1, r2]
    all_suits = [s1, s2]
    for card in community_cards:
        cr, cs = _parse_card(card)
        all_ranks.append(cr)
        all_suits.append(cs)

    if community_cards:
        board_ranks = [_parse_card(c)[0] for c in community_cards]
        for hr in (r1, r2):
            if hr in board_ranks:
                score += 0.20
                if hr >= 11:
                    score += 0.10

        from collections import Counter
        rank_counts = Counter(all_ranks)
        pairs = sum(1 for c in rank_counts.values() if c == 2)
        trips = sum(1 for c in rank_counts.values() if c >= 3)
        if trips > 0:
            score += 0.30
        elif pairs >= 2:
            score += 0.15

        suit_counts = Counter(all_suits)
        max_suit = max(suit_counts.values())
        if max_suit >= 5:
            score += 0.35
        elif max_suit == 4:
            score += 0.10

    return min(score, 1.0)


class SimplePlayer(Bot):
    """Tight-passive poker strategy implemented as a HuskyBench Bot.

    Decision thresholds (same as tight_passive/main.py):
    - strength < 0.15: CHECK if free, else FOLD
    - strength < 0.30: CHECK if free, else FOLD
    - strength < 0.50: CHECK if free, else CALL
    - strength < 0.70: RAISE ~0.3x pot  (ratio = 0.3 * pot / stack)
    - strength < 0.85: RAISE ~1.0x pot  (ratio = pot / stack)
    - strength >= 0.85: RAISE ~2.0x pot  (ratio = 2.0 * pot / stack)

    The engine receives raw (PokerAction.RAISE, amount) tuples.
    The trace parser converts these to canonical RAISE:<ratio> format
    (ratio = amount / player_stack) for offline evaluation.
    """

    def __init__(self):
        super().__init__()
        self.my_hand = []
        self.blind_amount = 10
        self.total_pot = 0

    def on_start(self, starting_chips: int, player_hands: List[str],
                 blind_amount: int, big_blind_player_id: int,
                 small_blind_player_id: int, all_players: List[int]):
        self.my_hand = player_hands
        self.blind_amount = blind_amount
        # Initialize with blinds (big + small); pot is always >= this
        self.total_pot = blind_amount + blind_amount // 2

    def _update_total_pot(self, round_state: RoundStateClient):
        """Track total pot across streets.

        round_state.pot only reflects the current street (resets to 0 on
        flop/turn/river) and side_pots may not be populated on the client.
        We seed total_pot with blinds in on_start() and keep a running max
        from round_state.pot (which is positive when bets occur on the
        current street).
        """
        self.total_pot = max(self.total_pot, round_state.pot)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self._update_total_pot(round_state)

    def get_action(self, round_state: RoundStateClient,
                   remaining_chips: int) -> Tuple[PokerAction, int]:
        self._update_total_pot(round_state)
        effective_pot = max(self.total_pot, self.blind_amount)

        strength = _hand_strength(self.my_hand, round_state.community_cards)
        can_check = round_state.current_bet == 0

        if strength < 0.15:
            return (PokerAction.CHECK, 0) if can_check else (PokerAction.FOLD, 0)
        elif strength < 0.30:
            return (PokerAction.CHECK, 0) if can_check else (PokerAction.FOLD, 0)
        elif strength < 0.50:
            return (PokerAction.CHECK, 0) if can_check else (PokerAction.CALL, 0)
        else:
            return self._raise_action(strength, effective_pot, round_state, can_check)

    def _raise_action(self, strength, effective_pot, round_state, can_check):
        """Compute a raise action, falling back to CHECK/CALL if not possible."""
        if strength < 0.70:
            target_amount = max(int(effective_pot * 0.3), 1)
        elif strength < 0.85:
            target_amount = max(effective_pot, 1)
        else:
            target_amount = max(int(effective_pot * 2.0), 1)

        # Clamp to engine limits; max_raise == 0 means raising is not possible
        amount = max(target_amount, round_state.min_raise)
        if round_state.max_raise > 0:
            amount = min(amount, round_state.max_raise)
        elif amount <= 0:
            return (PokerAction.CHECK, 0) if can_check else (PokerAction.CALL, 0)

        return PokerAction.RAISE, amount

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float,
                    all_scores: dict, active_players_hands: dict):
        pass
