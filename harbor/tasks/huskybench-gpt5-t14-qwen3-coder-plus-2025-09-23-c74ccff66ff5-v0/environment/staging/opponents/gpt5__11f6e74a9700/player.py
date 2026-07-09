from typing import List, Tuple
import hashlib
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

RANK_ORDER = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}

def det_rand01(key: str) -> float:
    """Deterministic pseudo-random in [0,1) from a string key."""
    try:
        h = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return (int(h[:12], 16) % 1000000) / 1000000.0
    except Exception:
        return 0.5

def parse_card(card: str):
    # Expect format like 'As', 'Kd', 'Tc'
    rank = card[0]
    suit = card[1] if len(card) > 1 else ''
    return rank, suit

def pocket_pair(cards: List[str]) -> bool:
    if len(cards) < 2:
        return False
    r1, _ = parse_card(cards[0])
    r2, _ = parse_card(cards[1])
    return r1 == r2

def is_suited(cards: List[str]) -> bool:
    if len(cards) < 2:
        return False
    _, s1 = parse_card(cards[0])
    _, s2 = parse_card(cards[1])
    return s1 == s2

def ranks_sorted(cards: List[str]) -> Tuple[str, str]:
    r1, _ = parse_card(cards[0])
    r2, _ = parse_card(cards[1])
    # return high, low rank chars
    return (r1, r2) if RANK_ORDER[r1] >= RANK_ORDER[r2] else (r2, r1)

def hand_category(cards: List[str]) -> str:
    """
    Very simple preflop hand tiers for heads-up:
    - premium: AA, KK, QQ, JJ, AKs, AKo, AQs
    - strong: TT, 99, AJs, KQs, AQo, KQo, ATs, KJs, QJs, JTs
    - medium: 88-66, ATo, KJo, QJo, T9s, 98s, 87s, 76s, A9s-A5s
    - spec: 55-22, 65s-54s, KTo, QTo, JTo
    - trash: others
    """
    if len(cards) < 2:
        return "trash"
    h, l = ranks_sorted(cards)
    suited = is_suited(cards)
    pp = pocket_pair(cards)

    if pp:
        if h in ['A','K','Q','J']:
            return "premium"
        if h in ['T','9']:
            return "strong"
        if h in ['8','7','6']:
            return "medium"
        return "spec"

    if h == 'A' and l == 'K':
        return "premium"  # AKs/AKo
    if h == 'A' and l == 'Q':
        return "premium" if suited else "strong"
    if h == 'A' and l == 'J':
        return "strong" if suited else "medium"
    if h == 'K' and l == 'Q':
        return "strong" if suited else "medium"
    if h == 'K' and l == 'J':
        return "medium" if suited else "spec"
    if h == 'Q' and l == 'J':
        return "medium" if suited else "spec"
    if h == 'J' and l == 'T':
        return "medium" if suited else "spec"
    if h == 'T' and l == '9':
        return "medium" if suited else "spec"
    if h == '9' and l == '8':
        return "medium" if suited else "spec"
    if h == '8' and l == '7':
        return "medium" if suited else "spec"
    if h == '7' and l == '6':
        return "medium" if suited else "spec"
    if h == '6' and l == '5':
        return "spec" if suited else "trash"
    if h == '5' and l == '4':
        return "spec" if suited else "trash"

    if h == 'A':
        # suited wheel aces and ATo
        if suited and l in ['9','8','7','6','5']:
            return "medium"
        return "medium" if l == 'T' else "spec"
    if h == 'K':
        return "medium" if (l == 'T' and not suited) else "spec"
    if h == 'Q':
        return "spec" if l == 'T' else "trash"
    if h == 'J':
        return "spec" if l == 'T' else "trash"

    return "trash"

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def _spr(remaining_chips: int, pot: int) -> float:
    pot = max(1, _safe_int(pot, 1))
    return float(max(0, remaining_chips)) / float(pot)

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole: List[str] = []
        self.blind_amount: int = 10
        self.is_small_blind: bool = False
        self.is_big_blind: bool = False
        self.all_players: List[int] = []

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # store state
        self.hole = player_hands or []
        self.blind_amount = blind_amount or self.blind_amount
        self.is_small_blind = (self.id == small_blind_player_id)
        self.is_big_blind = (self.id == big_blind_player_id)
        self.all_players = all_players or []

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        # No heavy computation to keep turn time minimal
        return

    def _my_bet(self, round_state: RoundStateClient) -> int:
        return round_state.player_bets.get(str(self.id), 0)

    def _cap_raise_to(self, round_state: RoundStateClient, target_total: int) -> int:
        # Cap by max_raise if provided (>0)
        max_r = round_state.max_raise or 0
        if max_r > 0:
            target_total = min(target_total, max_r)
        # Ensure at least current_bet
        target_total = max(target_total, round_state.current_bet)
        return target_total

    def _raise_amount_delta(self, round_state: RoundStateClient, target_total: int) -> int:
        my_bet = self._my_bet(round_state)
        delta = max(0, target_total - my_bet)
        return delta

    def _open_or_reraise_size(self, round_state: RoundStateClient, strength: str) -> int:
        """
        Determine a target total bet (not delta) based on strength, street, and position.
        Preflop: slightly larger opens from SB; postflop uses callers to decide.
        """
        cb = round_state.current_bet
        min_r = round_state.min_raise or 0
        street = (round_state.round or "").lower()

        # Base multiplier for raise sizing
        if strength == "premium":
            base_mult = 3.0
        elif strength == "strong":
            base_mult = 2.5
        elif strength == "medium":
            base_mult = 2.0
        else:
            base_mult = 0.0  # weak hands shouldn't raise via this path

        # Positional tweak preflop (SB opens a touch larger heads-up)
        pos_boost = 0.0
        if street == "preflop":
            if self.is_small_blind:
                pos_boost = 0.2

        mult = max(0.0, base_mult + pos_boost)

        if cb <= 0:
            # In case cb is 0 (e.g., postflop with no bet), use blind-based sizing
            base = max(self.blind_amount, 10)
            target = base * mult
        else:
            target = cb * mult

        # Ensure at least min_raise above current bet when raising
        target_total = int(max(cb + min_r, target)) if mult > 0 else cb
        target_total = self._cap_raise_to(round_state, target_total)
        return target_total

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        try:
            my_bet = self._my_bet(round_state)
            cb = round_state.current_bet
            min_r = round_state.min_raise or 0
            # Determine street
            street = (round_state.round or "").lower()

            # Basic info
            cat = hand_category(self.hole)

            # Convenience checks
            can_check = cb <= my_bet
            call_amount = max(0, cb - my_bet)

            # If we can check, be selective about betting; otherwise decide between call/raise/fold
            if street == "preflop":
                # Preflop strategy
                if can_check:
                    # We're not facing a bet (either BB checking option or post-raise equilibrium)
                    if cat in ["premium", "strong"]:
                        # Open or isolate
                        target_total = self._open_or_reraise_size(round_state, cat)
                        delta = self._raise_amount_delta(round_state, target_total)
                        if delta > 0 and delta <= remaining_chips:
                            return PokerAction.RAISE, delta
                        # fallback to check if can't raise
                        return PokerAction.CHECK, 0
                    elif cat == "medium":
                        # Mostly check; occasional small raise if we're on the button (SB heads-up)
                        if self.is_small_blind:
                            target_total = self._open_or_reraise_size(round_state, cat)
                            delta = self._raise_amount_delta(round_state, target_total)
                            if delta > 0 and delta <= remaining_chips and min_r > 0:
                                return PokerAction.RAISE, delta
                        return PokerAction.CHECK, 0
                    elif cat == "spec":
                        # Small blind occasional steal try with speculative hands
                        if self.is_small_blind and min_r > 0:
                            key = f"pf_steal:{round_state.round_num}:{self.id}:{''.join(self.hole)}"
                            if det_rand01(key) < 0.15:
                                target_total = self._open_or_reraise_size(round_state, "medium")
                                delta = self._raise_amount_delta(round_state, target_total)
                                if delta > 0 and delta <= remaining_chips:
                                    return PokerAction.RAISE, delta
                        return PokerAction.CHECK, 0
                    else:
                        return PokerAction.CHECK, 0
                else:
                    # Facing a bet (typically a raise)
                    pot = round_state.pot or 0
                    spr_val = _spr(remaining_chips, pot + call_amount)
                    if cat == "premium":
                        # Short SPR preflop: prefer jam
                        if spr_val <= 2.0 and call_amount > 0 and remaining_chips > call_amount:
                            return PokerAction.ALL_IN, 0
                        # 3-bet reasonable size
                        target_total = self._open_or_reraise_size(round_state, cat)
                        delta = self._raise_amount_delta(round_state, target_total)
                        if delta > 0 and delta < remaining_chips:
                            return PokerAction.RAISE, delta
                        # If cannot 3-bet without jamming, call
                        if call_amount <= remaining_chips:
                            return PokerAction.CALL, 0
                        return PokerAction.FOLD, 0
                    if cat == "strong":
                        # Consider shove if very shallow
                        if spr_val <= 1.7 and call_amount > 0 and remaining_chips > call_amount:
                            return PokerAction.ALL_IN, 0
                        # Prefer call
                        if call_amount <= remaining_chips:
                            return PokerAction.CALL, 0
                        return PokerAction.FOLD, 0
                    if cat == "medium":
                        # Call if price is reasonable (< ~2 blinds), else fold
                        price_ok = call_amount <= max(self.blind_amount * 2, 20)
                        if price_ok and call_amount <= remaining_chips:
                            return PokerAction.CALL, 0
                        return PokerAction.FOLD, 0
                    if cat == "spec":
                        # Call if very cheap (< blind), else fold
                        price_ok = call_amount <= max(self.blind_amount, 10)
                        if price_ok and call_amount <= remaining_chips:
                            return PokerAction.CALL, 0
                        return PokerAction.FOLD, 0
                    # trash
                    return PokerAction.FOLD, 0
            else:
                # Postflop: add pot-aware logic while keeping it light and conservative
                pot = round_state.pot or 0
                spr_val = _spr(remaining_chips, pot)

                if can_check:
                    # Consider a c-bet/value bet if no bet yet; mix frequencies by street
                    if round_state.current_bet == 0 and min_r > 0:
                        street_pf = (round_state.round or "").lower()
                        # Street-aware sizing fractions
                        if street_pf == "flop":
                            frac_by_cat = {"premium": 0.60, "strong": 0.48, "medium": 0.33, "spec": 0.25, "trash": 0.0}
                            # Allow rare stab with speculative hands on flop
                            freq_by_cat = {"premium": 1.00, "strong": 0.70, "medium": 0.50, "spec": 0.15, "trash": 0.0}
                        elif street_pf == "turn":
                            frac_by_cat = {"premium": 0.50, "strong": 0.40, "medium": 0.25, "spec": 0.0, "trash": 0.0}
                            freq_by_cat = {"premium": 0.90, "strong": 0.50, "medium": 0.35, "spec": 0.0, "trash": 0.0}
                        else:  # river
                            frac_by_cat = {"premium": 0.66, "strong": 0.40, "medium": 0.20, "spec": 0.0, "trash": 0.0}
                            freq_by_cat = {"premium": 0.85, "strong": 0.40, "medium": 0.25, "spec": 0.0, "trash": 0.0}

                        frac = frac_by_cat.get(cat, 0.0)
                        freq = freq_by_cat.get(cat, 0.0)
                        key = f"{round_state.round_num}:{street_pf}:{self.id}:{''.join(self.hole)}:{pot}:{len(round_state.community_cards)}"
                        r = det_rand01(key)
                        if frac > 0.0 and r < freq:
                            desired = int(max(min_r, pot * frac))
                            # Target total is the new current bet level when cb==0
                            target_total = self._cap_raise_to(round_state, max(round_state.current_bet + min_r, desired))
                            delta = self._raise_amount_delta(round_state, target_total)
                            if delta > 0 and delta <= remaining_chips:
                                return PokerAction.RAISE, delta
                    return PokerAction.CHECK, 0
                else:
                    # Facing a bet: combine pot-aware threshold with absolute blind threshold; tighten later streets
                    street_pf = (round_state.round or "").lower()
                    pot = round_state.pot or 0
                    spr_val = _spr(remaining_chips, pot)
                    base_abs = max(int(self.blind_amount * 1.5), 15)

                    # Base pot fraction by category, scaled by street (tighter on later streets for non-premium)
                    pot_frac_call = {
                        "premium": 0.70,
                        "strong": 0.50,
                        "medium": 0.33,
                        "spec": 0.20,
                        "trash": 0.10
                    }
                    base_frac = pot_frac_call.get(cat, 0.10)
                    street_scale = 1.0
                    if street_pf == "turn":
                        street_scale = 0.85
                    elif street_pf == "river":
                        street_scale = 0.70
                    frac = base_frac if cat == "premium" else min(0.9, base_frac * street_scale)

                    pot_threshold = int(pot * frac) if pot > 0 else base_abs

                    # Compose threshold: more liberal for premium/strong, tighter otherwise
                    if cat in ["premium", "strong"]:
                        threshold = max(base_abs, pot_threshold)
                    else:
                        threshold = min(base_abs, pot_threshold)

                    # Short SPR with premium: prefer to shove
                    if cat == "premium" and spr_val <= 1.5 and call_amount > 0 and remaining_chips > call_amount:
                        return PokerAction.ALL_IN, 0

                    # Consider value raises vs bets with premium/strong at reasonable size
                    if min_r > 0:
                        # Street-aware raise frequencies
                        if street_pf == "flop":
                            raise_freqs = {"premium": 0.55, "strong": 0.30, "medium": 0.10}
                        elif street_pf == "turn":
                            raise_freqs = {"premium": 0.45, "strong": 0.20, "medium": 0.05}
                        else:  # river
                            raise_freqs = {"premium": 0.35, "strong": 0.15, "medium": 0.03}
                        rf = raise_freqs.get(cat, 0.0)
                        # Avoid raising huge bets; prefer vs <=45% pot sizing
                        smallish = (pot > 0 and call_amount <= int(0.45 * pot)) or (pot == 0 and call_amount <= base_abs)
                        key_r = f"raise_vs_bet:{round_state.round_num}:{street_pf}:{self.id}:{''.join(self.hole)}:{pot}:{cb}"
                        if rf > 0.0 and smallish and det_rand01(key_r) < rf:
                            # Use sizing helper; map strong to strong, medium stays medium
                            use_strength = "premium" if cat == "premium" else ("strong" if cat == "strong" else "medium")
                            target_total = self._open_or_reraise_size(round_state, use_strength)
                            delta = self._raise_amount_delta(round_state, target_total)
                            if delta > 0 and delta <= remaining_chips:
                                return PokerAction.RAISE, delta

                    # Always continue vs micro-bets
                    micro_threshold = max(5, int(0.08 * pot))
                    if call_amount <= remaining_chips and call_amount <= micro_threshold:
                        return PokerAction.CALL, 0

                    if call_amount <= remaining_chips and call_amount <= max(1, threshold):
                        return PokerAction.CALL, 0
                    return PokerAction.FOLD, 0

        except Exception:
            # Failsafe: prefer check if possible, else fold
            if round_state.current_bet <= round_state.player_bets.get(str(self.id), 0):
                return PokerAction.CHECK, 0
            return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        return

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        return