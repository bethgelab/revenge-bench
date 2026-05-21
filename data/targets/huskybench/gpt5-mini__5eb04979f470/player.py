from typing import List, Tuple, Optional
import random
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

RANK_ORDER = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
              '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

PREMIUM_HANDS = {
    ('A', 'A'), ('K', 'K'), ('Q', 'Q'), ('A', 'K'), ('A', 'Q'), ('J', 'J')
}

# Normalized sets for order-independent membership checks
PREMIUM_HANDS_SETS = {frozenset(x) for x in PREMIUM_HANDS}

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []
        self.last_round_state: Optional[RoundStateClient] = None
        # Use a per-instance RNG to avoid global interference; optionally seeded later
        self.rng = random.Random()

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Save hole cards (expected as a list like ["As","Kd"])
        self.hole_cards = player_hands if player_hands else []
        self.starting_chips = starting_chips
        self.all_players = all_players  # seating order (if provided)
        # seed RNG with a mixture of starting chips and hole cards for repeatability within a game
        seed = starting_chips + sum(ord(c) for c in ''.join(self.hole_cards)) if self.hole_cards else starting_chips
        self.rng.seed(seed)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.last_round_state = round_state

    def _in_late_position(self, round_state: RoundStateClient) -> bool:
        """Return True if this player is in a late seating position (last third).
        Falls back to False on missing data."""
        try:
            if not hasattr(self, 'all_players') or self.all_players is None or self.id is None:
                return False
            total = len(self.all_players) if self.all_players else 0
            if total <= 0:
                return False
            if self.id not in self.all_players:
                return False
            idx = self.all_players.index(self.id)
            # late if in the last third of seating order
            return idx >= max(0, int(total * 2 / 3))
        except Exception:
            return False

    def _parse_card(self, card: str):
        if not card or len(card) < 2:
            return None, None
        rank = card[0].upper()
        suit = card[1].lower()
        return rank, suit

    def _ranks_from_cards(self, cards: List[str]) -> List[int]:
        vals = []
        for c in cards:
            r, _ = self._parse_card(c)
            if r and r in RANK_ORDER:
                vals.append(RANK_ORDER[r])
        return vals

    def _suits_from_cards(self, cards: List[str]) -> List[str]:
        suits = []
        for c in cards:
            _, s = self._parse_card(c)
            if s:
                suits.append(s)
        return suits

    def _has_straight(self, ranks: List[int], length: int = 5) -> bool:
        if not ranks:
            return False
        uniq = sorted(set(ranks))
        # Ace can be low for A-2-3-4-5
        if 14 in uniq:
            uniq = [1] + uniq
        consec = 1
        for i in range(1, len(uniq)):
            if uniq[i] == uniq[i-1] + 1:
                consec += 1
                if consec >= length:
                    return True
            else:
                consec = 1
        return False

    def _has_straight_draw(self, ranks: List[int]) -> bool:
        # crude check for open-ended or inside straight draw: presence of 4-card consecutive sequence
        if not ranks:
            return False
        uniq = sorted(set(ranks))
        if 14 in uniq:
            uniq = [1] + uniq
        consec = 1
        has_four = False
        for i in range(1, len(uniq)):
            if uniq[i] == uniq[i-1] + 1:
                consec += 1
                if consec >= 4:
                    has_four = True
                    break
            else:
                consec = 1
        return has_four

    def _hand_strength(self, round_state: Optional[RoundStateClient] = None):
        """
        Lightweight evaluator:
        - Preflop: score by pockets, suitedness, connectors, and high-cards
        - Postflop: detect made hands and draws using community cards to bump strength
        Returns a score roughly on a 0-100-ish scale where higher is stronger.
        """
        # Base preflop score from hole cards
        if not self.hole_cards or len(self.hole_cards) < 2:
            return 0.0
        r1, s1 = self._parse_card(self.hole_cards[0])
        r2, s2 = self._parse_card(self.hole_cards[1])
        if r1 is None or r2 is None:
            return 0.0

        v1 = RANK_ORDER.get(r1, 0)
        v2 = RANK_ORDER.get(r2, 0)
        ranks = (r1, r2)
        score = 0.0

        # Pocket pairs
        if r1 == r2:
            score += 60 + min(v1, v2)  # higher pairs much stronger

        # Premium combos (AK, AQ, KK, QQ, JJ)
        if frozenset(ranks) in PREMIUM_HANDS_SETS:
            score += 40

        # Suited bonus - increased a bit to value flush potential
        if s1 == s2:
            score += 16

        # High card bonuses
        if v1 >= 13:  # A or K
            score += 10
        elif v1 >= 11:
            score += 6
        if v2 >= 13:
            score += 10
        elif v2 >= 11:
            score += 6

        # Connectors: give more to close connectors, especially if suited
        diff = abs(v1 - v2)
        if diff == 0:
            pass
        elif diff == 1:
            score += 12
            if s1 == s2:
                score += 6
        elif diff == 2:
            score += 6
            if s1 == s2:
                score += 3
        elif diff <= 4:
            score += 3

        # Offsuit penalty
        if s1 != s2:
            score -= 2

        # Lower card penalty (kicker matters) but softened to not over-penalize connectors
        score -= min(v1, v2) * 0.25

        # Favor hands containing Ace or King a bit more
        if 'A' in ranks:
            score += 6
        if 'K' in ranks:
            score += 3

        # If no round_state or preflop, return preflop score mapped to ~0-90
        if not round_state or getattr(round_state, 'round', 'preflop').lower() == 'preflop':
            return float(score)

        # Postflop: incorporate community cards
        community = getattr(round_state, 'community_cards', []) or []
        all_cards = list(self.hole_cards) + list(community)
        comm_ranks = self._ranks_from_cards(community)
        comm_suits = self._suits_from_cards(community)
        all_ranks = self._ranks_from_cards(all_cards)
        all_suits = self._suits_from_cards(all_cards)

        # Count occurrences (including hole cards)
        from collections import Counter
        rank_counts = Counter([r for r in [r1, r2] if r is not None])
        for c in community:
            cr, _ = self._parse_card(c)
            if cr:
                rank_counts[cr] += 1

        # Made hands detection (simple)
        max_same_rank = max(rank_counts.values()) if rank_counts else 0

        # Pair/trips/quad logic
        if max_same_rank >= 4:
            # quads
            score += 70
        elif max_same_rank == 3:
            # trips: strong
            score += 50
        elif max_same_rank == 2:
            # At least a pair somewhere; check if it's just pair with board or uses our hole cards
            # if our hole contributes to the pair, favor more
            hole_rank_counts = Counter([r1, r2])
            pair_used = False
            for rk, cnt in rank_counts.items():
                if cnt >= 2 and hole_rank_counts.get(rk, 0) > 0:
                    pair_used = True
                    break
            score += 26 if pair_used else 8
            # small kicker bonus if top pair with good kicker
            if pair_used:
                # determine kicker value
                kicker = max(v1, v2)
                comm_vals = self._ranks_from_cards(community)
                top_comm = max(comm_vals) if comm_vals else 0
                if kicker >= top_comm and kicker >= 11:
                    score += 6

        # Two pair detection (crude: look across counts)
        pairs = sum(1 for v in rank_counts.values() if v >= 2)
        if pairs >= 2:
            score += 45

        # Flush detection and draw - increase draw value slightly
        suit_counts = Counter(all_suits)
        max_suit = max(suit_counts.values()) if suit_counts else 0
        if max_suit >= 5:
            score += 60  # made flush
        elif max_suit == 4:
            score += 26  # flush draw (made slightly more valuable)

        # Straight detection and draw
        if self._has_straight(all_ranks, 5):
            score += 55
        elif self._has_straight_draw(all_ranks):
            score += 22

        # Small bonus for top pair with good kicker (already handled above for pair_used)

        # Normalize a bit to keep values sensible
        # preflop score contributed ~[-10..90], postflop additions can push higher; cap
        return float(min(max(score, 0.0), 100.0))

    def _safe_min_raise(self, round_state: RoundStateClient):
        mr = getattr(round_state, 'min_raise', None)
        if not mr or mr <= 0:
            return 10
        return int(mr)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """
        Improved lightweight strategy with postflop awareness:
        - Use combined hand strength for pre/post-flop decisions
        - Consider pot odds when facing a bet to make reasonable calls
        - Raise more with strong made hands and controlled bluffs
        - Use pot-relative raises so aggression scales with the current pot
        """
        self.last_round_state = round_state
        strength = self._hand_strength(round_state)

        current_bet = getattr(round_state, 'current_bet', 0) or 0
        min_raise = self._safe_min_raise(round_state)
        pot = getattr(round_state, 'pot', 0) or 0

        # Controlled randomness for bluffing: position-aware and preflop-aware
        is_preflop = getattr(round_state, 'round', 'preflop').lower() == 'preflop'
        bluff_chance = 0.07 + max(0.0, (30.0 - strength) / 500.0)
        # Be more willing to bluff in late position during preflop
        try:
            if is_preflop and self._in_late_position(round_state):
                bluff_chance += 0.09
        except Exception:
            pass
        if remaining_chips < getattr(self, 'starting_chips', 0) * 0.25:
            bluff_chance += 0.03
        # on flop/turn/river be more conservative with bluffs
        if not is_preflop:
            bluff_chance *= 0.55
        # cap bluff chance a bit higher to allow controlled aggression
        bluff_chance = min(bluff_chance, 0.30)

        # If there's no bet, decide whether to check or open-raise
        if current_bet == 0:
            is_preflop = getattr(round_state, 'round', 'preflop').lower() == 'preflop'
            try:
                strength_eff = strength + (6 if is_preflop and self._in_late_position(round_state) else 0)
            except Exception:
                strength_eff = strength
            # Very strong made hands or monster postflop: big raise relative to pot
            if strength_eff >= 70:
                amt = min(remaining_chips, max(min_raise * 6, int(max(1, pot) * 0.6)))
                return PokerAction.RAISE, max(amt, min_raise)
            # Strong hands: raise moderately (pot-based)
            if strength_eff >= 50:
                amt = min(remaining_chips, max(min_raise * 4, int(max(1, pot) * 0.4)))
                return PokerAction.RAISE, max(amt, min_raise)
            # Good but not huge: small steal sometimes
            if strength_eff >= 30:
                if self.rng.random() < 0.5:
                    amt = min(remaining_chips, max(min_raise, int(max(1, pot) * 0.25)))
                    return PokerAction.RAISE, max(amt, min_raise)
                return PokerAction.CHECK, 0
            # Small chance to bluff-raise with weak hands (positioned)
            if self.rng.random() < bluff_chance:
                amt = min(remaining_chips, max(min_raise, int(getattr(self, 'starting_chips', 0) * 0.06)))
                return PokerAction.RAISE, max(amt, min_raise)
            # Otherwise check
            return PokerAction.CHECK, 0

        # Facing a bet: compute call amount and pot odds
        call_amount = current_bet
        pot_odds = (call_amount / (pot + call_amount)) if (pot + call_amount) > 0 else 0.0

        # If we have a very strong hand, raise for value (pot-based)
        if strength >= 65:
            amt = min(remaining_chips, max(min_raise * 4, int(max(1, pot) * 0.5)))
            return PokerAction.RAISE, max(amt, min_raise)

        # If bet is tiny relative to our remaining stack, call
        if call_amount <= max(20, int(remaining_chips * 0.03)):
            return PokerAction.CALL, 0

        # Pot-odds informed call: if our strength implies equity greater than pot odds (with safety margin), call
        strength_equity = min(0.95, strength / 100.0)
        # position-aware safety margin: be slightly more permissive in late position
        pos_factor = 1.1
        try:
            if self._in_late_position(round_state):
                pos_factor = 1.05
        except Exception:
            pass
        if call_amount > 0 and strength_equity > pot_odds * pos_factor:
            # Only call if not an overly deep fraction of our stack
            if call_amount <= max(150, int(remaining_chips * 0.18)):
                return PokerAction.CALL, 0

        # Medium strength or draws: call moderate bets (slightly more permissive)
        if strength >= 35 and call_amount <= max(160, int(remaining_chips * 0.20)):
            return PokerAction.CALL, 0

        # If strength is reasonable and opponent bet is stealable size, sometimes reraise to push
        if strength >= 30 and call_amount <= int(remaining_chips * 0.15) and self.rng.random() < 0.35:
            amt = min(remaining_chips, max(min_raise * 2, int(max(1, pot) * 0.35)))
            return PokerAction.RAISE, max(amt, min_raise)

        # Occasional shove/call when stack is short and we need action
        if remaining_chips < getattr(self, 'starting_chips', 0) * 0.18 and self.rng.random() < 0.06:
            if call_amount < remaining_chips * 0.5:
                return PokerAction.CALL, 0
            return PokerAction.RAISE, remaining_chips

        # Otherwise fold to large bets
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        # Reset hole cards between rounds if server doesn't provide new ones via on_start
        self.hole_cards = []

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        # Simple end-of-game hook (could log or learn)
        pass