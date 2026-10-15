from typing import List, Tuple, Optional, Any, Sequence
try:
    from .bot import Bot
    from .type.poker_action import PokerAction
    from .type.round_state import RoundStateClient
except Exception:
    from bot import Bot
    from type.poker_action import PokerAction
    from type.round_state import RoundStateClient
import random
import time
import os

# Seed randomness for small bluffs
random.seed(int(time.time()) & 0xFFFF)

VERBOSE = bool(os.getenv("VERBOSE", ""))

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand: Optional[List[str]] = None

    def on_start(self, starting_chips: int, player_hands: Any, blind_amount: int,
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Resolve our hand from a variety of possible formats
        self.hand = None
        try:
            if isinstance(player_hands, dict):
                self.hand = player_hands.get(str(self.id)) or player_hands.get(self.id)
            elif isinstance(player_hands, list) and isinstance(self.id, int) and 0 <= self.id < len(player_hands):
                self.hand = player_hands[self.id]
            elif isinstance(player_hands, list) and len(player_hands) > 0:
                first = player_hands[0]
                if isinstance(first, (list, tuple)):
                    self.hand = first
                else:
                    self.hand = player_hands
        except Exception:
            self.hand = None

        if VERBOSE:
            print("on_start: starting_chips=", starting_chips, "resolved_hand=", self.hand)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        if VERBOSE:
            print("on_round_start: round=", getattr(round_state, "round_num", None), "rem=", remaining_chips)

    # --- helpers for card parsing and simple evaluation ---
    def _rank_from_card(self, card: str) -> Optional[str]:
        if not card or not isinstance(card, str):
            return None
        card = card.upper().strip()
        if card.startswith("10"):
            return "T"
        rank = card[0]
        if rank == "1":
            return "T"
        return rank

    def _suit_from_card(self, card: str) -> Optional[str]:
        if not card or not isinstance(card, str):
            return None
        card = card.upper().strip()
        return card[-1] if len(card) >= 2 else None

    def _rank_value(self, rank: Optional[str]) -> int:
        order = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
        if not rank:
            return 0
        return order.get(rank.upper(), 0)

    def _is_pair(self, hand: Sequence[str]) -> bool:
        if not hand or len(hand) < 2:
            return False
        r0 = self._rank_from_card(hand[0])
        r1 = self._rank_from_card(hand[1])
        return r0 is not None and r0 == r1

    def _is_suited(self, hand: Sequence[str]) -> bool:
        if not hand or len(hand) < 2:
            return False
        s0 = self._suit_from_card(hand[0])
        s1 = self._suit_from_card(hand[1])
        return s0 is not None and s0 == s1

    def _is_connector(self, hand: Sequence[str]) -> bool:
        if not hand or len(hand) < 2:
            return False
        v0 = self._rank_value(self._rank_from_card(hand[0]))
        v1 = self._rank_value(self._rank_from_card(hand[1]))
        if v0 == 0 or v1 == 0:
            return False
        return abs(v0 - v1) == 1

    def _has_premium(self, hand: Sequence[str]) -> bool:
        if not hand or len(hand) < 2:
            return False
        premium = {"A", "K", "Q", "J", "T"}
        r0 = self._rank_from_card(hand[0])
        r1 = self._rank_from_card(hand[1])
        if (r0 in premium) and (r1 in premium):
            return True
        if self._is_suited(hand) and ({r0, r1} & {"A", "K", "Q"}):
            return True
        return (r0 in premium) or (r1 in premium)

    def _hand_high_card_value(self, hand: Sequence[str]) -> int:
        # Return numeric value of our highest hole card
        if not hand or len(hand) < 2:
            return 0
        return max(self._rank_value(self._rank_from_card(hand[0])), self._rank_value(self._rank_from_card(hand[1])))

    # get community cards from round_state defensively (various engine versions)
    def _community_cards(self, round_state: RoundStateClient) -> List[str]:
        for attr in ("community_cards", "community", "board", "community_cards_list"):
            cards = getattr(round_state, attr, None)
            if cards:
                return list(cards)
        # fallback: some engines embed in a dict
        try:
            if hasattr(round_state, "round_info") and isinstance(round_state.round_info, dict):
                return list(round_state.round_info.get("community_cards", []))
        except Exception:
            pass
        return []

    def _board_rank_counts(self, community: Sequence[str]) -> dict:
        counts = {}
        for c in community:
            r = self._rank_from_card(c)
            if r:
                counts[r] = counts.get(r, 0) + 1
        return counts

    def _hand_pairs_board(self, hand: Sequence[str], community: Sequence[str]) -> bool:
        # True if our hole pairs any community card rank
        if not hand:
            return False
        ranks = {self._rank_from_card(c) for c in community if self._rank_from_card(c)}
        return any(self._rank_from_card(h) in ranks for h in hand)

    def _board_is_paired(self, community: Sequence[str]) -> bool:
        # True if any rank appears >=2 on the board (paired board)
        counts = self._board_rank_counts(community)
        return any(v >= 2 for v in counts.values())

    def _has_overcard_vs_board(self, hand: Sequence[str], community: Sequence[str]) -> bool:
        # True if we hold at least one card higher than all community ranks (no pair)
        if not hand:
            return False
        board_vals = [self._rank_value(self._rank_from_card(c)) for c in community if self._rank_from_card(c)]
        if not board_vals:
            return False
        top_board = max(board_vals)
        return any(self._rank_value(self._rank_from_card(h)) > top_board for h in hand) and not self._hand_pairs_board(hand, community)

    # --- decision logic ---
    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        if VERBOSE:
            print("get_action: round", getattr(round_state, "round_num", None))

        # Detect if any raises occurred
        try:
            raised = any(("raise" in str(a).lower()) for a in round_state.player_actions.values())
        except Exception:
            raised = False

        hand = self.hand if isinstance(self.hand, (list, tuple)) else None

        # Base bluff chance smaller and tuned by stack-to-pot
        bluff_chance = 0.045  # dynamic bluff chance (slightly reduced)
        try:
            pot = getattr(round_state, "pot", 0) or 0
            # Reduce bluffing when low on chips
            if remaining_chips < 50:
                bluff_chance *= 0.35
            else:
                # Scale bluff chance mildly by stack-to-pot ratio, capped
                ratio = min(2.0, float(remaining_chips) / (pot + 1))
                bluff_chance = min(0.18, bluff_chance * (1.0 + (ratio - 1) * 0.6))
        except Exception:
            pass

        # If extremely short stacked, avoid bluffing and avoid risky calls
        short_stack = remaining_chips <= 10

        # Preflop logic (round_num == 1)
        if getattr(round_state, "round_num", 1) == 1:
            # Strong: pocket pair
            if hand and self._is_pair(hand):
                min_raise = getattr(round_state, "min_raise", None) or 20
                amount = min(min_raise * 3, remaining_chips)
                if VERBOSE:
                    print("Preflop: pocket pair -> RAISE", amount)
                return PokerAction.RAISE, max(1, int(amount))
            
            # Premium cards, be more conservative if there's already a raise
            if hand and self._has_premium(hand):
                min_raise = getattr(round_state, "min_raise", None) or 20
                r0 = self._rank_from_card(hand[0])
                r1 = self._rank_from_card(hand[1])
                both_premium = (r0 in {"A","K","Q","J","T"}) and (r1 in {"A","K","Q","J","T"})
                # treat Ace with strong kicker as effectively two premiums
                if not both_premium:
                    kicker_val = max(self._rank_value(r0), self._rank_value(r1))
                    if (r0 == "A" or r1 == "A") and kicker_val >= 10:
                        both_premium = True

                pocket = self._is_pair(hand)
                suited = self._is_suited(hand)
                if not raised:
                    # Only raise preflop automatically for pocket pairs or two premium cards.
                    if pocket or both_premium:
                        multiplier = 3 if pocket else (2 if both_premium else 1)
                        if suited and not pocket:
                            multiplier += 1
                        amount = min(min_raise * multiplier, remaining_chips)
                        if VERBOSE:
                            print("Preflop: premium and no raise -> RAISE", amount, "multiplier=", multiplier)
                        return PokerAction.RAISE, max(1, int(amount))
                    # Single premium card or weaker: prefer to check or make a small open-raise rarely
                    if getattr(round_state, "current_bet", 0) == 0:
                        if not short_stack and random.random() < 0.12:
                            amount = min(int(min_raise * 1.0), remaining_chips)
                            if VERBOSE:
                                print("Preflop: single premium -> small RAISE", amount)
                            return PokerAction.RAISE, max(1, int(amount))
                        return PokerAction.CHECK, 0
                else:
                    # If raised: be willing to call larger bets when our hand is clearly strong (pocket or two premiums)
                    current_bet = getattr(round_state, "current_bet", 0) or 0
                    strong = pocket or both_premium
                    call_threshold_frac = 0.25 if strong else 0.08
                    call_threshold_abs = 80 if strong else 35
                    if current_bet <= remaining_chips * call_threshold_frac or current_bet <= call_threshold_abs:
                        if VERBOSE:
                            print("Preflop: premium and raised -> CALL small")
                        return PokerAction.CALL, 0
                    if VERBOSE:
                        print("Preflop: premium but bet large -> FOLD")
                    return PokerAction.FOLD, 0
            
            # Suited connectors: try small raise when no one has raised
            if hand and self._is_suited(hand) and self._is_connector(hand) and not raised:
                min_raise = getattr(round_state, "min_raise", None) or 20
                amount = min(int(min_raise * 2.0), remaining_chips)
                if VERBOSE:
                    print("Preflop: suited connector -> RAISE modest", amount)
                return PokerAction.RAISE, max(1, int(amount))
            
            # Small random bluff only when nobody has bet yet and not short-stacked
            if hand and not raised and getattr(round_state, "current_bet", 0) == 0 and (not short_stack) and random.random() < bluff_chance:
                min_raise = getattr(round_state, "min_raise", None) or 20
                amount = min(int(min_raise * 1.6), remaining_chips)
                if VERBOSE:
                    print("Preflop: bluff -> RAISE", amount)
                return PokerAction.RAISE, max(1, int(amount))
            
            # Default preflop: check if possible, else call small bets, else fold
            if getattr(round_state, "current_bet", 0) == 0:
                return PokerAction.CHECK, 0
        
        community = self._community_cards(round_state)
        board_paired = self._board_is_paired(community)
        hand_pairs_board = self._hand_pairs_board(hand, community) if hand else False
        has_overcard = self._has_overcard_vs_board(hand, community) if hand else False

        current_bet = getattr(round_state, "current_bet", 0) or 0

        # If no bet, prefer to check (and occasionally bet small when strong)
        if current_bet == 0:
            # If we have top pair or board is paired (strong possibilities), make a small value bet sometimes to extract value
            if (hand_pairs_board or board_paired or (hand and self._has_premium(hand))) and random.random() < 0.6 and not short_stack:
                min_raise = getattr(round_state, "min_raise", None) or 20
                amount = min(int(min_raise * 2.0), remaining_chips)
                if VERBOSE:
                    print("Postflop: strong-ish and unchecked -> RAISE small", amount)
                return PokerAction.RAISE, max(1, amount)
            return PokerAction.CHECK, 0

        # Small bets: call defensively
        if current_bet <= remaining_chips * 0.05 or current_bet <= 12:
            # If we only have overcards (no pair) be more cautious and avoid calling even small ones unless cheap
            if has_overcard and current_bet > max(1, int(remaining_chips * 0.02)):
                if VERBOSE:
                    print("Postflop: only overcards and bet not tiny -> FOLD")
                return PokerAction.FOLD, 0
            return PokerAction.CALL, 0

        # If we have a decent hand postflop, be willing to call or raise a bit
        if hand_pairs_board or board_paired or (hand and self._has_premium(hand)):
            # If the bet is moderate, call; if it's moderate and we have a clear pair, try a small raise
            if current_bet <= remaining_chips * 0.10 or current_bet <= 50:
                # if we have pair on board, try to raise small to charge draws
                if hand_pairs_board and (getattr(round_state, "min_raise", None) or 20) and random.random() < 0.6 and not short_stack:
                    min_raise = getattr(round_state, "min_raise", None) or 20
                    amount = min(int(min_raise * 2.0), remaining_chips)
                    if VERBOSE:
                        print("Postflop: pair on board -> RAISE small", amount)
                    return PokerAction.RAISE, max(1, amount)
                return PokerAction.CALL, 0
            # Bet is large relative to stack: be cautious and fold unless very strong
            if hand_pairs_board and board_paired:
                # paired board + our pairing card is pretty strong: call larger bets
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Default: fold to large bets, call tiny ones
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        if VERBOSE:
            print("on_end_round: remaining_chips=", remaining_chips)

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        if VERBOSE:
            print("on_end_game: score=", player_score, "all_scores=", all_scores)