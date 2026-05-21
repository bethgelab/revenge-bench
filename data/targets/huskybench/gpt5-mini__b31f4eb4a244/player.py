from typing import List, Tuple, Optional, Dict, Any
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
import re

RANK_ORDER = "23456789TJQKA"
RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER, start=2)}

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards: Optional[List[str]] = None
        self.last_round_state: Optional[RoundStateClient] = None

    def _parse_hand(self, hand_repr) -> List[str]:
        """Try to parse different hand representations into a list of two card strings."""
        if hand_repr is None:
            return []
        if isinstance(hand_repr, (list, tuple)):
            return [str(x) for x in hand_repr]
        if isinstance(hand_repr, dict):
            # If a dict was passed, try to extract by our id if possible, otherwise take values
            if self.id is not None and str(self.id) in hand_repr:
                return self._parse_hand(hand_repr[str(self.id)])
            vals = list(hand_repr.values())
            if vals:
                return self._parse_hand(vals[0])
            return []
        # It's a string - try common separators
        s = str(hand_repr).strip()
        if "," in s:
            parts = [p.strip() for p in s.split(",") if p.strip()]
            if parts:
                return parts
        if " " in s:
            parts = [p.strip() for p in s.split(" ") if p.strip()]
            if parts:
                return parts
        # fallback: regex find card patterns like As, Td, 10h etc.
        full = re.findall(r'(?:10|[2-9TJQKA])[shdc]', s, flags=re.IGNORECASE)
        if full:
            return full
        # last resort: if e.g. "AsKd" (4 or 5 chars), split in half heuristically
        if len(s) in (4,5):
            first = s[:2]
            second = s[2:]
            return [first, second]
        return []

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Attempt to extract my hole cards robustly
        my_hand = []
        try:
            # If player_hands is dict-like, handled in _parse_hand
            if isinstance(player_hands, dict):
                my_hand = self._parse_hand(player_hands)
            elif isinstance(player_hands, list):
                # If we have an all_players list, find our index
                if all_players and self.id in all_players:
                    try:
                        idx = all_players.index(self.id)
                        if idx < len(player_hands):
                            my_hand = self._parse_hand(player_hands[idx])
                        else:
                            # fallback to first
                            my_hand = self._parse_hand(player_hands[0])
                    except ValueError:
                        my_hand = self._parse_hand(player_hands[0])
                else:
                    # If only one hand provided, assume it's ours
                    if len(player_hands) == 1:
                        my_hand = self._parse_hand(player_hands[0])
                    else:
                        # Try to find a hand that looks like two-card list
                        for h in player_hands:
                            parsed = self._parse_hand(h)
                            if len(parsed) == 2:
                                my_hand = parsed
                                break
                        if not my_hand and player_hands:
                            my_hand = self._parse_hand(player_hands[0])
            else:
                my_hand = self._parse_hand(player_hands)
        except Exception:
            my_hand = []

        self.hole_cards = my_hand if my_hand else None
        print("Player on_start. My hole cards:", self.hole_cards)
        print("Blind:", blind_amount, "Big blind id:", big_blind_player_id, "Small blind id:", small_blind_player_id)
        print("All players:", all_players, "My id:", self.id)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int) -> None:
        """Called at the start of each betting round. Store state and log minimal info."""
        self.last_round_state = round_state
        community = getattr(round_state, 'community_cards', []) or []
        print("on_round_start: round_num:", round_state.round_num, "community:", community, "remaining_chips:", remaining_chips)

    def _rank_of(self, card: str) -> Optional[Tuple[str, str]]:
        """Return (rank, suit) for a card like 'As' or '10h' or None if invalid."""
        if not card or len(card) < 2:
            return None
        card = card.strip()
        m = re.match(r'^(10|[2-9TJQKA])([shdc])$', card, flags=re.IGNORECASE)
        if not m:
            return None
        rank = m.group(1).upper()
        suit = m.group(2).lower()
        return rank, suit

    def _is_suited(self, c1: str, c2: str) -> bool:
        r1 = self._rank_of(c1)
        r2 = self._rank_of(c2)
        if not r1 or not r2:
            return False
        return r1[1] == r2[1]

    def _preflop_strength(self, hole: List[str]) -> str:
        """Quick heuristic for preflop strength: strong / medium / weak"""
        if not hole or len(hole) < 2:
            return "weak"
        c1, c2 = hole[0], hole[1]
        r1 = self._rank_of(c1)
        r2 = self._rank_of(c2)
        if r1 is None or r2 is None:
            return "weak"
        v1 = RANK_VALUE.get(r1[0], 0)
        v2 = RANK_VALUE.get(r2[0], 0)
        # pair?
        if r1[0] == r2[0]:
            if v1 >= RANK_VALUE['T']:  # TT+
                return "strong"
            if v1 >= RANK_VALUE['7']:  # 77-99
                return "medium"
            return "weak"
        ranks = {r1[0], r2[0]}
        if "A" in ranks and ("K" in ranks or "Q" in ranks):
            return "strong"
        # suited high cards
        if self._is_suited(c1, c2) and (v1 >= RANK_VALUE['J'] or v2 >= RANK_VALUE['J']):
            return "medium"
        # high card combos
        if v1 >= RANK_VALUE['K'] or v2 >= RANK_VALUE['K']:
            return "medium"
        return "weak"

    def _postflop_evaluation(self, hole: List[str], community: List[str]) -> str:
        """Return 'made', 'draw', or 'weak' based on simple heuristics:
           - 'made' if we pair or improve with community (pair, two-pair, trips, better)
           - 'draw' if we have a flush or straight draw
           - 'weak' otherwise
        """
        if not hole or len(hole) < 2:
            return "weak"
        ranks = []
        suits = []
        for c in (hole + (community or [])):
            rr = self._rank_of(c)
            if rr:
                ranks.append(rr[0])
                suits.append(rr[1])
        # check pair involving our hole cards
        hole_ranks = []
        hole_suits = []
        for c in hole:
            rr = self._rank_of(c)
            if rr:
                hole_ranks.append(rr[0])
                hole_suits.append(rr[1])

        # Made if any hole card rank appears in community -> we have at least a pair
        community_ranks = [self._rank_of(c)[0] for c in (community or []) if self._rank_of(c)]
        if any(hr in community_ranks for hr in hole_ranks):
            return "made"

        # Count suits to detect flush draw: if we hold two of same suit and there are 2 on board -> flush draw (need one more)
        # or if we hold one and board has 3 of that suit -> already made flush (count as made)
        from collections import Counter
        suit_counts = Counter(suits)
        hole_suit_counts = Counter(hole_suits)
        # If any suit count >=5 -> made (rare in short list but safe)
        if any(v >= 5 for v in suit_counts.values()):
            return "made"
        # flush draw: we have two suited hole and board has at least 2 of same suit
        if hole_suit_counts and any(hole_suit_counts[s] >= 2 and suit_counts.get(s, 0) >= 3 for s in hole_suit_counts):
            return "made"
        if hole_suit_counts and any(hole_suit_counts[s] >= 2 and suit_counts.get(s, 0) == 2 for s in hole_suit_counts):
            return "draw"
        # straight draw (very simple): check if we have connected cards with board ranks
        # map ranks to numeric and check runs of 4 (open-ended draw) or 3 (gutshot possibility)
        numeric = sorted({RANK_VALUE.get(r, 0) for r in ranks})
        if len(numeric) >= 4:
            # check if any run of length 4 exists (approximate straight draw)
            for i in range(len(numeric) - 3):
                if numeric[i+3] - numeric[i] == 3:
                    return "draw"
        # otherwise weak
        return "weak"

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. Improved with post-flop evaluation. """
        print("get_action called. Round num:", round_state.round_num, "Round type:", getattr(round_state, 'round', None),
              "Current bet:", round_state.current_bet, "Pot:", round_state.pot)
        # detect if anyone raised already this betting round
        raised = any((a or "").lower() == "raise" for a in (round_state.player_actions or {}).values())

        # Preflop logic (round_num == 1)
        if round_state.round_num == 1:
            strength = self._preflop_strength(self.hole_cards or [])
            print("Preflop strength:", strength, "Hole:", self.hole_cards)
            # Strong: raise when possible (but don't go all-in)
            if strength == "strong":
                amt = round_state.min_raise if round_state.min_raise and round_state.min_raise > 0 else 100
                # If someone already raised, do a re-raise moderate amount
                if raised:
                    return PokerAction.RAISE, min(amt * 2, remaining_chips)
                return PokerAction.RAISE, min(amt, remaining_chips)
            # Medium: call if there's a bet, otherwise check/call small
            if strength == "medium":
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                if round_state.current_bet <= max(1, remaining_chips // 10):
                    return PokerAction.CALL, 0
                if raised and round_state.current_bet > (remaining_chips // 6):
                    return PokerAction.FOLD, 0
                return PokerAction.CALL, 0
            # Weak: fold to raises, otherwise check/call minimally
            if strength == "weak":
                if raised or round_state.current_bet > (remaining_chips // 20):
                    return PokerAction.FOLD, 0
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                return PokerAction.CALL, 0

        # Post-flop: use community cards to evaluate
        community = getattr(round_state, 'community_cards', []) or []
        eval_result = self._postflop_evaluation(self.hole_cards or [], community)
        print("Postflop evaluation:", eval_result, "Hole:", self.hole_cards, "Community:", community)

        # If no bet, try to seize initiative when strong/made
        if round_state.current_bet == 0:
            if eval_result == "made":
                # small aggressive raise to build pot
                amt = round_state.min_raise if round_state.min_raise and round_state.min_raise > 0 else max(2, (round_state.pot or 1)//4)
                return PokerAction.RAISE, min(amt, remaining_chips)
            # check with draws or weak hands
            return PokerAction.CHECK, 0

        # If there's a bet, decide based on evaluation and bet size relative to pot and stack
        bet = round_state.current_bet
        pot = round_state.pot if round_state.pot else 1

        # made hands: call reasonable bets, raise small into small bets
        if eval_result == "made":
            if bet <= max(1, pot // 2):
                # if small relative to pot, call and consider raising small
                if bet <= max(1, pot // 6) and round_state.min_raise:
                    return PokerAction.RAISE, min(round_state.min_raise, remaining_chips)
                return PokerAction.CALL, 0
            # if bet is huge relative to our stack, fold conservatively
            if bet > remaining_chips // 2:
                return PokerAction.FOLD, 0
            return PokerAction.CALL, 0

        # draws: call small-to-medium bets to see next card
        if eval_result == "draw":
            if bet <= max(1, pot // 6) or bet <= max(1, remaining_chips // 20):
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # weak: fold to anything non-trivial, call tiny bets
        if bet <= max(1, pot // 12) or bet <= max(1, remaining_chips // 40):
            return PokerAction.CALL, 0
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        print("Round ended. Remaining chips:", remaining_chips)

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Game ended. Score:", player_score, "All scores:", all_scores)
        print("Active players' hands (showdown):", active_players_hands)