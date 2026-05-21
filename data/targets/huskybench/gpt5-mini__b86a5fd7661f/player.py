from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
import random

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []
        # seed for variability across matches but reproducible within a run
        random.seed()

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Save our hole cards for decision making
        self.hole_cards = player_hands.copy() if player_hands else []
        if hasattr(self, "id"):
            print(f"[on_start] My id: {self.id}, starting chips: {starting_chips}, hole: {self.hole_cards}, blind: {blind_amount}")
        else:
            print(f"[on_start] starting chips: {starting_chips}, hole: {self.hole_cards}, blind: {blind_amount}")

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        # Round start hook - could reset per-round memory if needed
        print("[on_round_start] Round:", round_state.round, "Round num:", round_state.round_num, "Pot:", round_state.pot)

    def _rank_value(self, r: str) -> int:
        order = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
        return order.get(r.upper(), 0)

    def _parse_card(self, card: str):
        # card like "As" or "Td"
        if not card or len(card) < 2:
            return None, None
        rank = card[0].upper()
        suit = card[1].lower()
        return rank, suit

    def _is_pair(self, cards: List[str]) -> bool:
        if len(cards) < 2:
            return False
        r1, _ = self._parse_card(cards[0])
        r2, _ = self._parse_card(cards[1])
        return r1 == r2

    def _is_suited(self, cards: List[str]) -> bool:
        if len(cards) < 2:
            return False
        _, s1 = self._parse_card(cards[0])
        _, s2 = self._parse_card(cards[1])
        return s1 == s2

    def _is_connected(self, cards: List[str]) -> bool:
        if len(cards) < 2:
            return False
        r1, _ = self._parse_card(cards[0])
        r2, _ = self._parse_card(cards[1])
        v1, v2 = self._rank_value(r1), self._rank_value(r2)
        # treat A-2 as connected for wheel potential
        diff = abs(v1 - v2)
        return diff == 1 or (set([r1, r2]) == set(['A','2']))

    def _strong_preflop(self) -> int:
        # Returns a strength score for preflop (higher is stronger)
        if len(self.hole_cards) < 2:
            return 0
        r1, _ = self._parse_card(self.hole_cards[0])
        r2, _ = self._parse_card(self.hole_cards[1])
        v1, v2 = self._rank_value(r1), self._rank_value(r2)
        high = max(v1, v2)
        low = min(v1, v2)
        score = 0

        # Pocket pairs: scale by rank
        if r1 == r2:
            score += 50 + high * 1.5  # pocket pairs get a big boost, larger for high pairs

        # High cards (A, K, Q, J)
        if high >= 14:  # Ace
            score += 22
        if high >= 13:
            score += 12
        if high >= 12:
            score += 6
        if high >= 11:
            score += 2

        # Suited combinations add value
        if self._is_suited(self.hole_cards):
            score += 6
            # suited broadways extra
            if (r1 == 'A' and v2 >= 11) or (r2 == 'A' and v1 >= 11):
                score += 8

        # Strong offsuit combos (AK, AQ, AJ)
        if (high == 14 and low >= 11) or (high == 13 and low >= 12):
            score += 14

        # Connectedness helps (including wheel)
        if self._is_connected(self.hole_cards):
            score += 4

        # Slight boost for being close to top of deck
        score += (high - 10) * 0.5

        # add limited randomness so identical hands don't always act the same
        score += random.uniform(-1.5, 1.5)
        return score

    def _has_pair_with_board(self, community: List[str]) -> bool:
        # Simplified check: do we have a pair using hole cards and/or board?
        ranks = []
        for c in (community or []):
            r, _ = self._parse_card(c)
            if r:
                ranks.append(r)
        for h in (self.hole_cards or []):
            r, _ = self._parse_card(h)
            if r:
                ranks.append(r)
        # if any rank appears at least twice we have at least a pair
        from collections import Counter
        cnt = Counter(ranks)
        for v in cnt.values():
            if v >= 2:
                return True
        return False

    def _has_flush_draw(self, community: List[str]) -> bool:
        # Do we have 4 of a suit across hole+community (one card to flush)
        suits = []
        for c in (community or []):
            _, s = self._parse_card(c)
            suits.append(s)
        for h in (self.hole_cards or []):
            _, s = self._parse_card(h)
            suits.append(s)
        from collections import Counter
        cnt = Counter(suits)
        # flush draw: 4 to a suit (one more gives flush)
        for v in cnt.values():
            if v >= 4:
                return True
        return False

    def _has_open_ended_straight_draw(self, community: List[str]) -> bool:
        # Very simplified: check if there are 4 cards that can form a sequence when combined with hole cards
        # We'll evaluate ranks numerically and look for near-sequences length >=4
        ranks = set()
        for c in (community or []):
            r, _ = self._parse_card(c)
            if r:
                ranks.add(self._rank_value(r))
        for h in (self.hole_cards or []):
            r, _ = self._parse_card(h)
            if r:
                ranks.add(self._rank_value(r))
        if not ranks:
            return False
        # check runs of length 4 (open ended draws)
        vals = sorted(ranks)
        consec = 1
        for i in range(1, len(vals)):
            if vals[i] == vals[i-1] + 1:
                consec += 1
                if consec >= 4:
                    return True
            elif vals[i] == vals[i-1]:
                continue
            else:
                consec = 1
        # special case for A-2-3-4 wheel draw
        if {14,2,3,4}.issubset(ranks):
            return True
        return False

    def _estimate_equity(self, paired: bool, flush_draw: bool, straight_draw: bool, round_state: RoundStateClient) -> float:
        # Rough, conservative equity estimator based on simple features.
        # Values tuned to avoid overcalling.
        base = 0.12  # baseline
        if paired or self._is_pair(self.hole_cards):
            base = 0.45
        # draws move equity up modestly
        if flush_draw:
            base += 0.18
        if straight_draw:
            base += 0.12
        # board interaction: if both draws exist, add a bit more
        if flush_draw and straight_draw:
            base += 0.08
        # preflop strength fallback (normalized)
        if round_state.round_num == 1:
            s = self._strong_preflop()
            # map to 0.09-0.48 roughly
            pre = 0.09 + min(0.39, max(0.0, (s / 120.0) * 0.39))
            base = pre
        # clamp
        return max(0.02, min(base, 0.85))

    def _constrain_bet(self, amt: int, remaining_chips: int) -> int:
        try:
            amt = int(amt)
        except Exception:
            amt = 0
        if amt < 0:
            amt = 0
        # never bet more than we have
        return min(amt, max(0, int(remaining_chips)))

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        # Basic information
        print("[get_action] round:", round_state.round, "round_num:", round_state.round_num, "current_bet:", round_state.current_bet, "pot:", round_state.pot)
        # Normalize opponent actions (case-insensitive)
        raised = False
        for player_action in (round_state.player_actions or {}).values():
            try:
                if player_action and str(player_action).upper() == "RAISE":
                    raised = True
                    break
            except Exception:
                continue

        # Preflop logic (round_num == 1)
        if round_state.round_num == 1:
            strength = self._strong_preflop()
            print(f"[get_action][PREFLOP] hole: {self.hole_cards}, strength: {strength:.2f}, raised: {raised}")

            # Small chance to bluff with very weak hands, but reduced vs raises
            bluff_chance = 0.05
            is_weak = strength < 12

            # Premium hands -> larger raises
            if strength >= 65 and not raised:
                amt = max(round_state.min_raise, min(int(remaining_chips * 0.22), 300))
                amt = self._constrain_bet(amt, remaining_chips)
                print(f"[ACTION] RAISE {amt} (very strong preflop)")
                return PokerAction.RAISE, int(amt)

            # Strong hands -> open or re-raise moderately
            if strength >= 40:
                if raised:
                    # defend or reraise occasionally if very strong
                    if strength >= 55 and remaining_chips > round_state.current_bet + round_state.min_raise and random.random() < 0.35:
                        amt = max(round_state.min_raise, min(int(remaining_chips * 0.14), 220))
                        amt = self._constrain_bet(amt, remaining_chips)
                        print(f"[ACTION] RAISE {amt} (preflop reraise, strong hand)")
                        return PokerAction.RAISE, int(amt)
                    print("[ACTION] CALL 0 (strong preflop, facing raise)")
                    return PokerAction.CALL, 0
                else:
                    amt = max(round_state.min_raise, min(int(remaining_chips * 0.10), 140))
                    amt = self._constrain_bet(amt, remaining_chips)
                    print(f"[ACTION] RAISE {amt} (strong preflop)")
                    return PokerAction.RAISE, int(amt)

            # Medium strength: open or call small bets
            if strength >= 18:
                if round_state.current_bet == 0:
                    print("[ACTION] CHECK 0 (medium preflop)")
                    return PokerAction.CHECK, 0
                else:
                    # defend vs small bets relative to stack
                    if round_state.current_bet <= max(1, int(remaining_chips * 0.045)):
                        print("[ACTION] CALL 0 (medium preflop small bet)")
                        return PokerAction.CALL, 0
                    print("[ACTION] FOLD 0 (medium preflop too big bet)")
                    return PokerAction.FOLD, 0

            # Weak hands: rare bluffs when no raise, otherwise fold to bets
            if is_weak and not raised and random.random() < bluff_chance:
                amt = max(round_state.min_raise, min(int(remaining_chips * 0.035), 80))
                amt = self._constrain_bet(amt, remaining_chips)
                print(f"[ACTION] RAISE {amt} (preflop bluff)")
                return PokerAction.RAISE, int(amt)

            if round_state.current_bet == 0:
                print("[ACTION] CHECK 0 (weak preflop)")
                return PokerAction.CHECK, 0
            else:
                print("[ACTION] FOLD 0 (weak preflop facing bet)")
                return PokerAction.FOLD, 0

        # Postflop logic (flop, turn, river)
        community = round_state.community_cards or []
        paired = self._has_pair_with_board(community)
        flush_draw = self._has_flush_draw(community)
        straight_draw = self._has_open_ended_straight_draw(community)
        print(f"[get_action][POSTFLOP] community: {community}, paired_with_board: {paired}, flush_draw: {flush_draw}, straight_draw: {straight_draw}")

        # Estimate equity and use simple pot-odds reasoning
        equity = self._estimate_equity(paired, flush_draw, straight_draw, round_state)
        pot = max(0, getattr(round_state, "pot", 0) or 0)
        bet = max(0, round_state.current_bet or 0)
        # pot odds: cost to call / (pot + cost to call)
        pot_odds = (bet / (pot + bet)) if (pot + bet) > 0 else 0.0
        print(f"[POSTFLOP] equity: {equity:.2f}, pot_odds: {pot_odds:.2f}, bet: {bet}, pot: {pot}")

        # If we pair the board or have a pocket pair, be more aggressive
        if paired or self._is_pair(self.hole_cards):
            if bet > 0:
                # call if equity sufficiently exceeds pot_odds (safety margin), or small bet
                if equity + 0.06 >= pot_odds or bet <= max(1, int(remaining_chips * 0.06)):
                    # occasionally reraise if clearly ahead
                    if equity > pot_odds + 0.22 and remaining_chips > bet + round_state.min_raise:
                        amt = max(round_state.min_raise, min(int(remaining_chips * 0.12), 220))
                        amt = self._constrain_bet(amt, remaining_chips)
                        print(f"[ACTION] RAISE {amt} (paired postflop, confident)")
                        return PokerAction.RAISE, int(amt)
                    print("[ACTION] CALL 0 (paired postflop)")
                    return PokerAction.CALL, 0
                else:
                    print("[ACTION] FOLD 0 (paired postflop, bad pot odds)")
                    return PokerAction.FOLD, 0
            else:
                # sometimes build pot a bit when we have a pair, but also reasonable chance to check
                if random.random() < 0.45:
                    print("[ACTION] CHECK 0 (paired postflop, slow-play)")
                    return PokerAction.CHECK, 0
                amt = max(round_state.min_raise, min(int(remaining_chips * 0.06), 160))
                amt = self._constrain_bet(amt, remaining_chips)
                print(f"[ACTION] RAISE {amt} (paired postflop, no bet)")
                return PokerAction.RAISE, int(amt)

        # Drawy hands: call based on pot odds or probe bet when free
        if flush_draw or straight_draw:
            if bet == 0:
                # sometimes probe bet to represent strength, but not too often
                if random.random() < 0.28 and remaining_chips > round_state.min_raise:
                    amt = max(round_state.min_raise, min(int(remaining_chips * 0.04), 90))
                    amt = self._constrain_bet(amt, remaining_chips)
                    print(f"[ACTION] RAISE {amt} (probe bet with draw)")
                    return PokerAction.RAISE, int(amt)
                print("[ACTION] CHECK 0 (draw, no bet)")
                return PokerAction.CHECK, 0
            # call if pot odds justify the call given our estimated equity
            # be slightly more willing to call draws if the bet is small relative to pot or stack
            if equity + 0.02 >= pot_odds or bet <= max(1, int(remaining_chips * 0.05)):
                print("[ACTION] CALL 0 (draw, pot odds ok)")
                return PokerAction.CALL, 0
            print("[ACTION] FOLD 0 (draw, bad pot odds)")
            return PokerAction.FOLD, 0

        # Otherwise play conservatively: check if possible, otherwise fold to raises, call small bets
        if bet == 0:
            print("[ACTION] CHECK 0 (postflop, no pair/no draw)")
            return PokerAction.CHECK, 0

        # If bet is small relative to remaining chips, or pot odds favor a call, call; else fold
        if bet <= max(1, int(remaining_chips * 0.05)) or equity + 0.03 >= pot_odds:
            print("[ACTION] CALL 0 (postflop, small bet or pot odds acceptable)")
            return PokerAction.CALL, 0

        print("[ACTION] FOLD 0 (postflop, facing large bet and poor odds)")
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("[on_end_round] Round ended. remaining_chips:", remaining_chips)

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("[on_end_game] Player score:", player_score, "All scores:", all_scores, "Active hands:", active_players_hands)