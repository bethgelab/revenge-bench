from typing import List, Tuple, Dict
from collections import Counter
import random

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

RANK_ORDER = "23456789TJQKA"
RANK_TO_INT = {r: i for i, r in enumerate(RANK_ORDER)}


def card_rank(card: str) -> str:
    return card[0]


def card_suit(card: str) -> str:
    return card[1]


def canonical_hand(hand: List[str]) -> str:
    """Return canonical starting hand code like 'AKs','QJo','88'."""
    assert len(hand) == 2
    r1, r2 = sorted([card_rank(c) for c in hand], key=lambda r: RANK_TO_INT[r], reverse=True)
    suited = card_suit(hand[0]) == card_suit(hand[1])
    if r1 == r2:
        return f"{r1}{r2}"
    return f"{r1}{r2}{'s' if suited else 'o'}"


# Pre-flop hand tiers (very rough)
STRONG_HANDS = {
    "AA", "KK", "QQ", "JJ", "TT",
    "AKs", "AQs", "AJs", "KQs", "AKo",
}
MEDIUM_HANDS = {
    "99", "88", "77", "66", "55",
    "ATs", "KJs", "QJs", "KQo", "AQo", "AJo",
    "KTs", "QTs", "JTs",
    "A9s", "QJo", "T9s", "98s", "87s",
}


class SimplePlayer(Bot):
    """
    Heuristic rule-based Texas Hold'em bot.

    Improvements over baseline:
        â¢ Adds minimal post-flop hand evaluator:
            â Categorises hand as STRONG (â¥2-pair, flush, trips+),
              MEDIUM (top/2nd pair), DRAW (flush/OESD),
              or WEAK.
        â¢ Bets/raises with strong, semi-bluffs draws, folds weak
          facing aggression.
        â¢ Adds occasional bluff/steal when checked to.
    """

    # ---------- Helper evaluation ---------- #
    @staticmethod
    def _rank_counts(cards: List[str]) -> Counter:
        return Counter(card_rank(c) for c in cards)

    @staticmethod
    def _suit_counts(cards: List[str]) -> Counter:
        return Counter(card_suit(c) for c in cards)

    def _has_flush(self, cards: List[str]) -> bool:
        return max(self._suit_counts(cards).values()) >= 5

    def _has_flush_draw(self, cards: List[str]) -> bool:
        return max(self._suit_counts(cards).values()) == 4

    def _is_straight(self, ranks: List[int]) -> bool:
        """Given sorted unique ints low->high (<=7 cards) determine straight."""
        if len(ranks) < 5:
            return False
        # wheel straight handling (A-5)
        if set([12, 0, 1, 2, 3]).issubset(ranks):
            return True
        for i in range(len(ranks) - 4):
            if ranks[i + 4] - ranks[i] == 4:
                return True
        return False

    def _has_straight(self, cards: List[str]) -> bool:
        ranks = sorted({RANK_TO_INT[card_rank(c)] for c in cards})
        return self._is_straight(ranks)

    def _has_straight_draw(self, cards: List[str]) -> bool:
        """Very loose OESD check: 4-card open-ended sequence."""
        ranks = sorted({RANK_TO_INT[card_rank(c)] for c in cards})
        if len(ranks) < 4:
            return False
        # wheel draw (A234)
        if set([12, 0, 1, 2]).issubset(ranks):
            return True
        for i in range(len(ranks) - 3):
            if ranks[i + 3] - ranks[i] == 3:
                return True
        return False

    def _hand_category(self, community: List[str]) -> str:
        """
        Categorise combined hand into:
            'strong'  â â¥2 pair, trips+, or made flush/straight
            'medium'  â any pair (top/2nd) or good draws
            'draw'    â flush/straight draw with no pair
            'weak'    â nothing
        """
        cards = self.hole_cards + community
        cnt = self._rank_counts(cards)
        max_same = max(cnt.values())
        pair = max_same >= 2
        two_pair = len([v for v in cnt.values() if v >= 2]) >= 2
        trips_plus = max_same >= 3
        flush = self._has_flush(cards)
        straight = self._has_straight(cards)
        strong = flush or straight or trips_plus or two_pair
        if strong:
            return "strong"
        # draws
        flush_draw = self._has_flush_draw(cards)
        straight_draw = self._has_straight_draw(cards)
        if pair:
            return "medium"
        if flush_draw or straight_draw:
            return "draw"
        return "weak"

    # ---------- Bot callbacks -------------- #
    def __init__(self):
        super().__init__()
        self.starting_hand_code: str = ""
        self.hole_cards: List[str] = []

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
        self.starting_hand_code = canonical_hand(player_hands)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        # No per-round reset required
        pass

    # ---------- Decision logic ------------- #
    def get_action(
        self, round_state: RoundStateClient, remaining_chips: int
    ) -> Tuple[PokerAction, int]:
        # Shortcut variables
        current_bet = round_state.current_bet
        min_raise = round_state.min_raise or 0
        pot = round_state.pot
        our_contribution = round_state.player_bets.get(str(self.id), 0)
        to_call = current_bet - our_contribution

        # Did someone raise/bet already this street?
        someone_raised = any(
            act.lower() == "raise" or act.lower() == "bet"
            for act in round_state.player_actions.values()
        )

        # ---------- Pre-flop ----------
        if round_state.round.lower() == "preflop":
            # Strong: raise (3bb) if unopened, else call
            if self.starting_hand_code in STRONG_HANDS:
                if current_bet == 0:
                    raise_amount = max(min_raise, 3 * min_raise)
                    raise_amount = min(raise_amount, remaining_chips)
                    return PokerAction.RAISE, raise_amount
                else:
                    return (PokerAction.CALL, 0) if to_call <= remaining_chips else (PokerAction.ALL_IN, 0)
            # Medium: limp/call small, occasionally raise as steal
            elif self.starting_hand_code in MEDIUM_HANDS:
                if current_bet == 0:
                    # 15% chance to open raise
                    if random.random() < 0.15:
                        raise_amount = max(min_raise, 2 * min_raise)
                        return PokerAction.RAISE, min(raise_amount, remaining_chips)
                    return PokerAction.CHECK, 0
                else:
                    if to_call <= remaining_chips * 0.05:
                        return PokerAction.CALL, 0
                    return PokerAction.FOLD, 0
            # Weak: fold to aggression, otherwise check
            else:
                return (PokerAction.CHECK, 0) if current_bet == 0 else (PokerAction.FOLD, 0)

        # ---------- Post-flop ----------
        category = self._hand_category(round_state.community_cards)

        # When no bet to us
        if current_bet == 0:
            if category == "strong":
                # Value bet ~60% pot
                bet = max(min_raise, int(pot * 0.6))
                bet = min(bet, remaining_chips)
                # Ensure we actually raise at least min_raise
                return PokerAction.RAISE, bet if bet > 0 else 0
            elif category == "draw" and random.random() < 0.25:
                # Semi-bluff draws 25% of the time (1/2 pot)
                bet = max(min_raise, int(pot * 0.5))
                bet = min(bet, remaining_chips)
                return PokerAction.RAISE, bet if bet > 0 else 0
            elif category == "medium" and random.random() < 0.1:
                # Occasional protection bet
                bet = max(min_raise, int(pot * 0.4))
                bet = min(bet, remaining_chips)
                return PokerAction.RAISE, bet if bet > 0 else 0
            else:
                return PokerAction.CHECK, 0

        # Facing a bet
        else:
            # Pot odds rough call threshold
            pot_odds = to_call / (pot + to_call) if pot + to_call > 0 else 1

            if category == "strong":
                # Re-raise half the time; otherwise call
                if random.random() < 0.5 and remaining_chips > to_call + min_raise:
                    raise_amount = to_call + max(min_raise, int(pot * 0.75))
                    raise_amount = min(raise_amount, remaining_chips)
                    return PokerAction.RAISE, raise_amount
                else:
                    return PokerAction.CALL, 0

            elif category == "draw":
                # Call if we have decent odds (<35% of pot) else fold
                if pot_odds < 0.35 and to_call <= remaining_chips * 0.25:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0

            elif category == "medium":
                # Small bets call; big bets fold
                if to_call <= int(pot * 0.25):
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:  # weak
                return PokerAction.FOLD, 0

    # ---------- Event hooks --------------- #
    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(
        self,
        round_state: RoundStateClient,
        player_score: float,
        all_scores: Dict[int, float],
        active_players_hands: Dict[int, List[str]],
    ):
        pass