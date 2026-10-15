from typing import List, Tuple, Optional
import random

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

RANK_ORDER = "23456789TJQKA"
RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER, start=2)}
VALUE_RANK = {v: r for r, v in RANK_VALUE.items()}


class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_hand_raw = None  # raw representation received in on_start
        self.my_hole_cards = None  # parsed as list like ['Ah', 'Kd']

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int,
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Try to determine our hand from the provided player_hands.
        self.my_hand_raw = None
        try:
            if player_hands is None:
                self.my_hand_raw = None
            elif isinstance(player_hands, list):
                if self.id is not None and 0 <= self.id < len(player_hands):
                    self.my_hand_raw = player_hands[self.id]
                else:
                    if len(player_hands) == 2 and all(isinstance(x, str) and len(x) <= 3 for x in player_hands):
                        self.my_hand_raw = player_hands
                    else:
                        self.my_hand_raw = player_hands[0] if player_hands else None
            else:
                self.my_hand_raw = player_hands
        except Exception:
            self.my_hand_raw = None

        self.my_hole_cards = self._parse_hand(self.my_hand_raw)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """
        Strategy improvements:
        - Add small randomized aggression to avoid being fully predictable.
        - Slightly reduce tolerance to call large bets with draws.
        - Keep core structure from previous rounds to avoid regressions.
        """

        hole = self.my_hole_cards or []

        # Helpers
        def rank_value(card: str) -> int:
            if not card:
                return 0
            s = str(card).strip().upper()
            # Handle '10' as 'T'
            if s.startswith('10'):
                r = 'T'
            else:
                r = s[0] if len(s) > 0 else ''
            return RANK_VALUE.get(r, 0)

        def suit(card: str) -> str:
            if not card:
                return ''
            s = str(card).strip()
            # Suit is expected to be the last character (handles '10h')
            return s[-1].upper() if len(s) >= 1 else ''

        def is_pair(c: List[str]) -> bool:
            return len(c) == 2 and c[0][0].upper() == c[1][0].upper()

        def is_suited(c: List[str]) -> bool:
            return len(c) == 2 and len(c[0]) > 1 and len(c[1]) > 1 and c[0][1].upper() == c[1][1].upper()

        # Preflop evaluation
        pair = is_pair(hole)
        suited = is_suited(hole)
        ranks = [rank_value(c) for c in hole] if len(hole) == 2 else []
        high_cards = sum(1 for r in ranks if r >= RANK_VALUE.get('T'))  # T or better

        current_bet = getattr(round_state, "current_bet", 0) or 0
        min_raise = max(1, getattr(round_state, "min_raise", 1) or 1)

        # Utility to pick raise amount in a conservative range
        def pick_raise(multiplier: float = 0.1, min_mult: int = 1):
            amt = max(min_raise, int(max(min_mult, remaining_chips * multiplier)))
            if amt > remaining_chips:
                amt = remaining_chips
            return amt

        # Board analysis utility
        def analyze_board(hole_cards: List[str], community: List[str]):
            info = {
                "has_pair_with_board": False,
                "top_pair": False,
                "two_pair_or_better": False,
                "trips_or_better": False,
                "flush_made": False,
                "flush_draw": False,
            }
            if not community or len(community) == 0:
                return info
            all_cards = list(community) + hole_cards

            # Count ranks and suits
            ranks_count = {}
            suits_count = {}
            # Helper to normalize rank char
            def rch(card):
                if not card:
                    return None
                x = card[0].upper()
                return 'T' if x == '1' else x

            for c in all_cards:
                if not c:
                    continue
                r = rch(c)
                s = suit(c)
                ranks_count[r] = ranks_count.get(r, 0) + 1
                suits_count[s] = suits_count.get(s, 0) + 1

            # made hands
            max_rank_count = max(ranks_count.values()) if ranks_count else 0
            if max_rank_count >= 4:
                info["trips_or_better"] = True
            elif max_rank_count == 3:
                info["trips_or_better"] = True
            # two pair detection: at least two ranks with count >=2
            pairs = sum(1 for v in ranks_count.values() if v >= 2)
            if pairs >= 2:
                info["two_pair_or_better"] = True
            if any(v >= 2 for v in ranks_count.values()):
                # Do we have a pair involving our hole cards?
                for hc in hole_cards:
                    hr = rch(hc)
                    if ranks_count.get(hr, 0) >= 2:
                        info["has_pair_with_board"] = True
                # top pair heuristic: check if our highest hole card matches highest rank on board
                board_ranks = [rch(c) for c in community if c]
                if board_ranks:
                    top_on_board = max(board_ranks, key=lambda x: RANK_VALUE.get(x, 0))
                    for hc in hole_cards:
                        if rch(hc) == top_on_board:
                            info["top_pair"] = True

            # flush made or draw
            for s, cnt in suits_count.items():
                # count suits in hole + community separately for draw detection
                hole_suits = sum(1 for hc in hole_cards if suit(hc) == s)
                community_suits = sum(1 for cc in community if suit(cc) == s)
                if (hole_suits + community_suits) >= 5:
                    info["flush_made"] = True
                # flush draw: 4 of same suit total and at least one in hole
                if (hole_suits + community_suits) == 4 and hole_suits >= 1:
                    info["flush_draw"] = True

            return info

        community = getattr(round_state, "community_cards", None) or []

        # Preflop behavior
        if not community:
            # If no info on hand, be conservative
            if not hole or len(hole) < 2:
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                if current_bet <= max(1, int(remaining_chips * 0.02)):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            pr = rank_value(hole[0]) if pair else None

            if pair:
                pr = rank_value(hole[0])
                # Premium pairs: QQ+
                if pr >= RANK_VALUE.get('Q'):
                    amt = pick_raise(multiplier=0.22, min_mult=2)
                    return PokerAction.RAISE, amt
                # Medium pairs: 99-JJ - sometimes 3-bet or raise depending on stack
                if pr >= RANK_VALUE.get('9'):
                    # Occasionally mix with a small additional raise to be less predictable
                    if random.random() < 0.2:
                        return PokerAction.RAISE, pick_raise(multiplier=0.18, min_mult=2)
                    return PokerAction.RAISE, pick_raise(multiplier=0.12, min_mult=1)
                # Small pocket pairs: sometimes limp/call to set mine when cheap
                if current_bet == 0:
                    if random.random() < 0.12:
                        return PokerAction.RAISE, pick_raise(multiplier=0.06, min_mult=1)
                    return PokerAction.CHECK, 0
                if current_bet <= max(1, int(remaining_chips * 0.02)):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            # Strong broadway combos and AK/AQ
            if len(ranks) == 2:
                ranks_sorted = sorted(ranks, reverse=True)
                # If we have AK (both), strongly raise
                if set(ranks_sorted) == {RANK_VALUE['A'], RANK_VALUE['K']}:
                    return PokerAction.RAISE, pick_raise(multiplier=0.25, min_mult=2)
                # AQ or KQ suited/aggressive
                if RANK_VALUE['A'] in ranks_sorted and max(ranks_sorted) >= RANK_VALUE['Q']:
                    # With some small randomness occasionally take a larger sizing
                    if random.random() < 0.15:
                        return PokerAction.RAISE, pick_raise(multiplier=0.22, min_mult=2)
                    return PokerAction.RAISE, pick_raise(multiplier=0.15, min_mult=1)
                # High broadway suited connectors
                if high_cards >= 2:
                    if suited:
                        return PokerAction.RAISE, pick_raise(multiplier=0.1, min_mult=1)
                    # sometimes call if both high but unsuited
                    if current_bet == 0:
                        return PokerAction.CHECK, 0
                    if current_bet <= max(1, int(remaining_chips * 0.03)):
                        return PokerAction.CALL, 0
                    return PokerAction.FOLD, 0

            # Suited Aces or connectors with a high card
            if suited and max(ranks) >= RANK_VALUE.get('T'):
                if current_bet == 0:
                    # occasionally open with a small raise to pick up blinds
                    if random.random() < 0.1:
                        return PokerAction.RAISE, pick_raise(multiplier=0.08, min_mult=1)
                    return PokerAction.CHECK, 0
                if current_bet <= max(1, int(remaining_chips * 0.03)):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            # Default: check when no bet, otherwise fold/call based on cheapness
            if current_bet == 0:
                return PokerAction.CHECK, 0
            if current_bet <= max(1, int(remaining_chips * 0.03)):
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Postflop
        info = analyze_board(hole, community)

        # No bet to call: take initiative with strong made hands or small bet with draws (semi-bluff)
        if current_bet == 0:
            # With very strong hands, bet for value
            if info["trips_or_better"] or info["two_pair_or_better"] or info["flush_made"]:
                # small scaling based on stack to avoid overcommitting
                return PokerAction.RAISE, pick_raise(multiplier=0.16, min_mult=2)
            # Top pair or pair with board: sometimes bet for value to avoid being checked behind
            if info["top_pair"] or info["has_pair_with_board"]:
                if random.random() < 0.35:
                    return PokerAction.RAISE, pick_raise(multiplier=0.06, min_mult=1)
                return PokerAction.CHECK, 0
            # Semi-bluff small raise with flush draw opportunities to take pot down
            if info["flush_draw"]:
                if random.random() < 0.6:
                    return PokerAction.RAISE, pick_raise(multiplier=0.06, min_mult=1)
                return PokerAction.CHECK, 0
            # Occasional small bluff to mix strategy (rare)
            if random.random() < 0.04:
                return PokerAction.RAISE, pick_raise(multiplier=0.05, min_mult=1)
            return PokerAction.CHECK, 0

        # There is a bet to call postflop
        to_call = current_bet

        # Made hands behavior: call/raise depending on bet size
        if info["trips_or_better"] or info["two_pair_or_better"] or info["flush_made"]:
            if to_call <= max(1, int(remaining_chips * 0.35)):
                return PokerAction.CALL, 0
            if to_call <= int(remaining_chips * 0.6):
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Top pair or pair with board: be more cautious but call small bets
        if info["top_pair"] or info["has_pair_with_board"]:
            if to_call <= max(1, int(remaining_chips * 0.12)):
                return PokerAction.CALL, 0
            # use suit + small randomness to occasionally float
            if to_call <= max(1, int(remaining_chips * 0.22)) and suited and random.random() < 0.4:
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Draws: call small bets; semi-bluff raise if bet is small
        if info["flush_draw"]:
            # tighten the calling threshold slightly to avoid over-calling
            if to_call <= max(1, int(remaining_chips * 0.10)):
                # If bet is very small, sometimes raise to represent strength
                if to_call <= max(1, int(remaining_chips * 0.025)) and random.random() < 0.35:
                    return PokerAction.RAISE, pick_raise(multiplier=0.06, min_mult=1)
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Default fold to bets; sometimes call very small probes
        if to_call <= max(1, int(remaining_chips * 0.02)) and random.random() < 0.25:
            return PokerAction.CALL, 0
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass

    @staticmethod
    def _parse_hand(raw) -> Optional[List[str]]:
        if raw is None:
            return None
        try:
            cards = None
            if isinstance(raw, list):
                parts = [str(x).strip() for x in raw if x is not None]
                cards = parts[:2] if len(parts) >= 2 else parts
            else:
                s = str(raw).strip()
                if ',' in s:
                    parts = [p.strip() for p in s.split(',') if p.strip()]
                    cards = parts[:2] if len(parts) >= 2 else parts
                elif ' ' in s:
                    parts = [p.strip() for p in s.split() if p.strip()]
                    cards = parts[:2] if len(parts) >= 2 else parts
                else:
                    import re as _re
                    tokens = _re.findall(r"(10|[2-9TJQKA])([cdhsCDHS])", s)
                    if tokens:
                        cards = [t[0] + t[1] for t in tokens][:2]
                    elif len(s) == 4:
                        cards = [s[:2], s[2:4]]
                    else:
                        parts = [s[i:i+2] for i in range(0, len(s), 2)]
                        cards = parts[:2] if len(parts) >= 2 else parts
            if not cards:
                return None
            def norm(c):
                c = str(c).strip()
                if not c:
                    return c
                # Normalize '10' to 'T'
                if c.lower().startswith('10'):
                    return 'T' + c[-1].upper()
                if len(c) == 2:
                    return c[0].upper() + c[1].upper()
                if len(c) >= 3:
                    return ('T' + c[-1].upper())
                return c.upper()
            result = [norm(x) for x in cards]
            return result if result else None
        except Exception:
            return None