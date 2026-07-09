from typing import List, Tuple, Dict
import random
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient


class SimplePlayer(Bot):
    """
    Lightweight yet competent rule-based poker bot.

    â¢ Pre-flop  : play strong starting hands aggressively, fold trash to big raises.
    â¢ Post-flop : distinguish strong / medium / weak pairs; use pot-odds for draws;
                  semi-bluff occasionally.  All logic is O(1) and keeps total runtime
                  far below the 10-second limit.
    """

    RANK_ORDER = "23456789TJQKA"
    RANK_INDEX = {r: i for i, r in enumerate(RANK_ORDER)}
    STRONG_PAIR_RANKS = set("9TJQKA")  # 99+ pocket pairs
    PREMIUM_NON_PAIR = {
        ("A", "K"), ("A", "Q"), ("A", "J"), ("K", "Q")
    }  # suited/offsuit treated equally

    # ---------- Lifecycle ---------- #
    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.hole_cards: List[str] = []
        self.blind_amount: int = 0

    # ---------- Basic helpers ---------- #
    @staticmethod
    def _ranks(cards: List[str]) -> List[str]:
        return [c[0] for c in cards]

    # ---------- Hand evaluation helpers ---------- #
    def _has_pair_with_hole(self, community: List[str]) -> bool:
        """True if a pair involves at least one of our hole cards (pocket pair counts)."""
        if len(self.hole_cards) < 2:
            return False
        # Pocket pair
        if self.hole_cards[0][0] == self.hole_cards[1][0]:
            return True
        hole_ranks = self._ranks(self.hole_cards)
        return any(card[0] in hole_ranks for card in community)

    def _has_flush_draw(self, community: List[str]) -> bool:
        """
        Detect a flush draw: 4 cards of same suit among hole+community, with at least one
        of those being in our hand (so we have outs).
        """
        suits = [c[1] for c in self.hole_cards + community]
        for s in "shdc":
            if suits.count(s) == 4 and any(c[1] == s for c in self.hole_cards):
                return True
        return False

    def _has_open_ended_straight_draw(self, community: List[str]) -> bool:
        """
        Detect an open-ended straight draw (OESD): four distinct consecutive ranks that
        include at least one hole card.  Ace considered high only.
        """
        cards = self.hole_cards + community
        unique_ranks = sorted({self.RANK_INDEX[c[0]] for c in cards})
        hole_ranks_idx = {self.RANK_INDEX[c[0]] for c in self.hole_cards}

        for i in range(len(unique_ranks) - 3):
            window = unique_ranks[i : i + 4]
            if window[-1] - window[0] == 3 and hole_ranks_idx.intersection(window):
                return True
        return False

    def _is_strong_preflop(self) -> bool:
        """Pocket pair 99+ OR premium two-card combos."""
        a, b = self.hole_cards
        r1, r2 = a[0], b[0]
        # Strong pocket pair
        if r1 == r2 and r1 in self.STRONG_PAIR_RANKS:
            return True
        pair = tuple(sorted((r1, r2), key=self.RANK_ORDER.index, reverse=True))
        return pair in self.PREMIUM_NON_PAIR

    # ---------- New helper: classify pair strength ---------- #
    def _pair_strength(self, community: List[str]) -> str:
        """
        Crude classification of our made pair strength:
            strong : over-pair or top-pair
            medium : 2nd / 3rd pair
            weak   : worse
        """
        if not self._has_pair_with_hole(community):
            return "none"

        board_ranks = [self.RANK_INDEX[c[0]] for c in community] or [0]
        board_high = max(board_ranks)
        board_sorted = sorted(board_ranks, reverse=True)
        board_mid = board_sorted[1] if len(board_sorted) > 1 else board_high

        # Rank of card forming our pair
        if self.hole_cards[0][0] == self.hole_cards[1][0]:
            pair_rank = self.RANK_INDEX[self.hole_cards[0][0]]
        else:
            hole_ranks = {h[0] for h in self.hole_cards}
            pair_rank = max(
                (self.RANK_INDEX[c[0]] for c in community if c[0] in hole_ranks),
                default=-1,
            )

        if pair_rank >= board_high:
            return "strong"
        if pair_rank >= board_mid:
            return "medium"
        return "weak"

    # ---------- Bot interface implementations ---------- #
    def on_start(
        self,
        starting_chips: int,
        player_hands: List[str],
        blind_amount: int,
        big_blind_player_id: int,
        small_blind_player_id: int,
        all_players: List[int],
    ):
        self.hole_cards = player_hands[:2]
        self.blind_amount = blind_amount
        if self.debug:
            print(f"[DEBUG] Hole cards: {self.hole_cards}, blind={blind_amount}")

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass  # nothing to do

    def get_action(
        self, round_state: RoundStateClient, remaining_chips: int
    ) -> Tuple[PokerAction, int]:
        current_bet = round_state.current_bet
        min_raise = round_state.min_raise or self.blind_amount
        community = round_state.community_cards
        pot = round_state.pot

        is_preflop = round_state.round.lower() == "preflop"

        # How much more do we need to invest to stay in the hand?
        my_investment = round_state.player_bets.get(str(self.id), 0)
        to_call = max(0, current_bet - my_investment)

        # ---------- Decision logic ---------- #
        if is_preflop:
            return self._preflop_decision(to_call, min_raise, remaining_chips)
        else:
            return self._postflop_decision(
                to_call, min_raise, remaining_chips, community, pot
            )

    # ---------- Stage-specific decision sub-routines ---------- #
    def _preflop_decision(
        self, to_call: int, min_raise: int, stack: int
    ) -> Tuple[PokerAction, int]:
        strong = self._is_strong_preflop()
        if strong:
            # Be aggressive when first in
            if to_call == 0:
                raise_amt = max(min_raise, self.blind_amount * 2)
                raise_amt = min(raise_amt, stack)
                if raise_amt >= min_raise and stack > raise_amt:
                    return PokerAction.RAISE, raise_amt
            # Otherwise call up to 3 blinds or 15 % of stack
            if to_call <= max(self.blind_amount * 3, int(stack * 0.15)):
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0
        else:
            # Weak hand
            if to_call == 0:
                return PokerAction.CHECK, 0
            if to_call > self.blind_amount:
                return PokerAction.FOLD, 0
            return PokerAction.CALL, 0

    def _postflop_decision(
        self,
        to_call: int,
        min_raise: int,
        stack: int,
        community: List[str],
        pot: int,
    ) -> Tuple[PokerAction, int]:
        have_pair = self._has_pair_with_hole(community)
        have_draw = self._has_flush_draw(community) or self._has_open_ended_straight_draw(
            community
        )

        if have_pair:
            strength = self._pair_strength(community)
            if strength == "strong":
                # Value-bet / raise more aggressively
                if to_call == 0:
                    raise_amt = max(min_raise, int(pot * 0.75))
                    raise_amt = min(raise_amt, stack)
                    if raise_amt >= min_raise:
                        return PokerAction.RAISE, raise_amt
                    return PokerAction.CHECK, 0
                if to_call <= int(stack * 0.4):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            elif strength == "medium":
                if to_call == 0:
                    # Occasional protection bet (30 % frequency)
                    if random.random() < 0.3:
                        raise_amt = min_raise
                        if raise_amt <= stack:
                            return PokerAction.RAISE, raise_amt
                    return PokerAction.CHECK, 0
                if to_call <= int(stack * 0.15):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            else:  # weak pair
                if to_call == 0:
                    return PokerAction.CHECK, 0
                if to_call <= self.blind_amount:
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

        elif have_draw:
            # Semi-bluff logic
            if to_call == 0:
                raise_amt = min_raise  # cheap stab
                if raise_amt <= stack:
                    return PokerAction.RAISE, raise_amt
                return PokerAction.CHECK, 0

            # Pot-odds test: call if to_call / (pot + to_call) â¤ 0.35 (~flush/straight odds)
            if pot + to_call > 0 and (to_call / (pot + to_call)) <= 0.35:
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        else:
            # No made hand or draw â play passively
            if to_call == 0:
                return PokerAction.CHECK, 0
            if to_call <= self.blind_amount:
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(
        self,
        round_state: RoundStateClient,
        player_score: float,
        all_scores: Dict,
        active_players_hands: Dict,
    ):
        if self.debug:
            print(f"[DEBUG] Game over. Score: {player_score}")