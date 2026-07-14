from typing import List, Tuple
from collections import Counter
import random
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient


def rank_value(card: str) -> int:
    r = card[0].upper()
    if r == 'A':
        return 14
    if r == 'K':
        return 13
    if r == 'Q':
        return 12
    if r == 'J':
        return 11
    if r == 'T':
        return 10
    # digits 2-9
    try:
        return int(r)
    except Exception:
        return 0


def is_suited(c1: str, c2: str) -> bool:
    return len(c1) >= 2 and len(c2) >= 2 and c1[1].lower() == c2[1].lower()


def categorize_hand(cards: List[str]) -> str:
    """
    Rough preflop hand categories: 'premium', 'strong', 'medium', 'weak'
    Based only on hole cards for speed and simplicity.
    """
    if not cards or len(cards) < 2:
        return 'weak'
    c1, c2 = cards[0], cards[1]
    r1, r2 = rank_value(c1), rank_value(c2)
    suited = is_suited(c1, c2)
    high1, high2 = max(r1, r2), min(r1, r2)
    pair = r1 == r2

    # Pairs
    if pair:
        if r1 >= 11:  # JJ+
            return 'premium'
        if r1 >= 9:   # 99-TT
            return 'strong'
        return 'medium'  # 22-88

    # Non-pairs
    # Premium broadways
    if (high1 == 14 and high2 >= 13):  # AK, AQ, AJ
        return 'premium' if suited or high2 >= 13 else 'strong'  # AKs premium; AK off strong/premium, AQo strong
    if suited and ((high1 >= 13 and high2 >= 11) or (high1 == 14 and high2 >= 10)):  # suited broadways
        return 'strong'
    if high1 >= 13 and high2 >= 12:  # KQ, KQ off
        return 'strong'

    # Suited aces and connectors
    if suited and high1 == 14 and high2 >= 5:  # A5s+
        return 'medium'
    if suited and ((high1 >= 11 and high2 >= 9) or (high1 - high2 == 1 and high2 >= 6)):  # JTs+, 76s+
        return 'medium'

    # Offsuit broadways like AQo, AJo, KJo
    if high1 == 14 and high2 >= 11:
        return 'medium'
    if high1 >= 13 and high2 >= 11:
        return 'medium'

    return 'weak'


def _ranks_and_suits(cards: List[str]):
    ranks = [rank_value(c) for c in cards if c]
    suits = [c[1].lower() for c in cards if c and len(c) > 1]
    return ranks, suits


def board_texture_flags(board: List[str]) -> Tuple[bool, bool, bool]:
    """
    Returns (is_wet, is_monotone_or_3flush, is_paired_or_connected)
    Wet if: paired or 3+ to a suit or ranks tightly connected (span of any 3 ranks <= 4).
    """
    ranks, suits = _ranks_and_suits(board)
    if not board:
        return False, False, False

    suit_counts = Counter(suits)
    rank_counts = Counter(ranks)

    # Suited danger: monotone or at least 3 to a flush
    mono_or_3flush = (len(set(suits)) == 1 and len(suits) >= 3) or any(v >= 3 for v in suit_counts.values())

    # Paired board
    paired = any(v >= 2 for v in rank_counts.values())

    # Connectedness: if any window of 3 unique ranks spans <= 4 (e.g., 9-T-J or 5-7-8)
    connected = False
    ur = sorted(set(ranks))
    if len(ur) >= 3:
        for i in range(len(ur) - 2):
            if ur[i + 2] - ur[i] <= 4:
                connected = True
                break
    # Consider wheel potential: treat Ace as 1 for connection checks
    if 14 in ur:
        ur_w = sorted(set([1 if r == 14 else r for r in ur]))
        if len(ur_w) >= 3 and not connected:
            for i in range(len(ur_w) - 2):
                if ur_w[i + 2] - ur_w[i] <= 4:
                    connected = True
                    break

    paired_or_connected = paired or connected
    is_wet = mono_or_3flush or paired_or_connected
    return is_wet, mono_or_3flush, paired_or_connected


def evaluate_postflop_strength(hole_cards: List[str], board: List[str]) -> str:
    """
    Very lightweight postflop strength heuristic:
    - strong: trips+, overpair, top pair (Q+), or two pair
    - medium: any pair, basic flush-draw heuristic, or straight draw (OESD/gutshot)
    - weak: otherwise
    """
    if not board:
        return 'weak'
    if len(hole_cards) < 2:
        return 'weak'

    h1, h2 = hole_cards[0], hole_cards[1]
    r1, r2 = rank_value(h1), rank_value(h2)
    pair_in_hole = r1 == r2

    board_ranks, board_suits = _ranks_and_suits(board)
    hole_ranks, hole_suits = _ranks_and_suits(hole_cards)
    board_rank_counter = Counter(board_ranks)

    intersect = set(hole_ranks).intersection(set(board_ranks))
    intersect_count = len(intersect)

    max_board = max(board_ranks) if board_ranks else 0

    # Trips or better detection (approx)
    if pair_in_hole and r1 in board_ranks:
        return 'strong'  # set/trips
    if intersect_count >= 2:
        return 'strong'  # two pair or better
    # Overpair
    if pair_in_hole and r1 > max_board:
        return 'strong'

    # Top pair with decent kicker
    if intersect_count == 1:
        match_rank = list(intersect)[0]
        if match_rank == max_board and match_rank >= 12:  # top pair Q+
            return 'strong'
        return 'medium'

    # Pocket pair below board (still a pair)
    if pair_in_hole:
        return 'medium' if r1 >= 7 else 'weak'

    # Flush draw heuristic: 4+ of a suit with at least 1 from hole
    total_suits = Counter(board_suits + hole_suits)
    for s, cnt in total_suits.items():
        if cnt >= 4 and s in hole_suits:
            return 'medium'

    # Straight draw heuristic (OESD/gutshot):
    # Consider sequences of 5 ranks; if we have >=4 within any window and at least one from our hole cards, treat as medium.
    unique_ranks = set(board_ranks + hole_ranks)
    # Account for wheel: treat Ace as both high (14) and low (1)
    if 14 in unique_ranks:
        unique_ranks_wheel = unique_ranks | {1}
        hole_unique = set(hole_ranks) | ({1} if 14 in set(hole_ranks) else set())
    else:
        unique_ranks_wheel = unique_ranks
        hole_unique = set(hole_ranks)

    for start_r in range(1, 11):  # 1(A-low) to 10
        seq = {start_r, start_r + 1, start_r + 2, start_r + 3, start_r + 4}
        present = len(seq & unique_ranks_wheel)
        from_hole = len(seq & hole_unique)
        if present >= 4 and from_hole >= 1:
            return 'medium'

    # If board pairs (we might counterfeit) -> remain cautious
    if any(v >= 2 for v in board_rank_counter.values()):
        return 'weak'

    return 'weak'

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []
        self.blind_amount: int = 0
        self.bb_player_id = None
        self.sb_player_id = None

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Store basic info
        self.hole_cards = list(player_hands) if player_hands else []
        self.blind_amount = blind_amount
        self.bb_player_id = big_blind_player_id
        self.sb_player_id = small_blind_player_id
        # Lightweight logging
        print(f"[on_start] id={self.id} hole={self.hole_cards} blind={blind_amount} players={all_players} BB={big_blind_player_id} SB={small_blind_player_id}")

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print(f"[on_round_start] id={self.id} round={round_state.round} num={round_state.round_num} pot={round_state.pot} bet={round_state.current_bet} chips={remaining_chips}")

    def _player_contribution(self, round_state: RoundStateClient) -> int:
        try:
            return int(round_state.player_bets.get(str(self.id), 0))
        except Exception:
            return 0

    def _call_cost(self, round_state: RoundStateClient) -> int:
        return max(0, int(round_state.current_bet) - self._player_contribution(round_state))

    def _pot_odds(self, round_state: RoundStateClient) -> float:
        call_cost = self._call_cost(round_state)
        if call_cost <= 0:
            return 0.0
        pot = max(0, int(round_state.pot))
        return call_cost / (pot + call_cost)

    def _open_raise_amount(self, round_state: RoundStateClient, remaining_chips: int, target_bb: float) -> int:
        """
        Compute additional chips to put in now to reach a target multiple of big blind.
        """
        bb = max(1, int(self.blind_amount))
        target_total = int(target_bb * bb)
        already = self._player_contribution(round_state)
        add = max(0, target_total - already)
        # avoid tiny raises: at least 1 BB if we're betting into 0
        if round_state.current_bet == 0:
            add = max(add, bb)
        return max(0, min(add, remaining_chips))

    def _min_reraise_amount(self, round_state: RoundStateClient, remaining_chips: int) -> int:
        """
        Compute a minimal legal reraise amount (additional chips now) when facing a bet.
        amount_to_send = call_cost + min_raise
        """
        call_cost = self._call_cost(round_state)
        min_raise = int(getattr(round_state, 'min_raise', 0) or 0)
        target = call_cost + max(min_raise, 1)
        return max(0, min(target, remaining_chips))

    def _postflop_bet_amount(self, round_state: RoundStateClient, remaining_chips: int, bb_mult: float = 1.0) -> int:
        """
        Size a postflop bet using min_raise and/or big blind as floor.
        """
        bb = max(1, int(self.blind_amount))
        base = max(int(bb_mult * bb), 1)
        min_raise = int(getattr(round_state, 'min_raise', 0) or 0)
        amt = max(base, min_raise)
        return max(0, min(amt, remaining_chips))

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        # Safety checks
        if remaining_chips <= 0:
            return PokerAction.CHECK, 0  # runner will handle all-in semantics

        stage = (round_state.round or "").lower()
        call_cost = self._call_cost(round_state)
        pot_odds = self._pot_odds(round_state)
        category = categorize_hand(self.hole_cards)

        # Preflop strategy (more aggressive heads-up)
        if stage == "preflop" or round_state.round_num == 1:
            # If no bet yet (current_bet could be 0 or just blinds are posted)
            if round_state.current_bet == 0:
                if category == 'premium':
                    amt = self._open_raise_amount(round_state, remaining_chips, target_bb=3.0)
                    if amt > 0:
                        return PokerAction.RAISE, amt
                    return PokerAction.CHECK, 0
                elif category == 'strong':
                    amt = self._open_raise_amount(round_state, remaining_chips, target_bb=2.5)
                    if amt > 0:
                        return PokerAction.RAISE, amt
                    return PokerAction.CHECK, 0
                elif category == 'medium':
                    # Heads-up: open small raise rather than limp
                    amt = self._open_raise_amount(round_state, remaining_chips, target_bb=2.0)
                    if amt > 0:
                        return PokerAction.RAISE, amt
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.CHECK, 0
            else:
                # SB first-to-act preflop: treat as open-raise spot into the big blind
                already = self._player_contribution(round_state)
                try:
                    bb = max(1, int(self.blind_amount))
                except Exception:
                    bb = max(1, self.blind_amount or 1)
                sb_amt = max(1, bb // 2)
                if self.blind_amount > 0 and round_state.current_bet == bb and already <= sb_amt:
                    if category in ('premium', 'strong', 'medium'):
                        # Prefer proper open sizing (HU aggression) while respecting min-raise legality
                        target_bb = 3.0 if category == 'premium' else (2.5 if category == 'strong' else 2.0)
                        amt_open = self._open_raise_amount(round_state, remaining_chips, target_bb=target_bb)
                        min_rr = self._min_reraise_amount(round_state, remaining_chips)
                        amt = max(amt_open, min_rr)
                        amt = min(amt, remaining_chips)
                        if amt > 0:
                            return PokerAction.RAISE, amt
                        return PokerAction.CALL, 0
                # Facing a raise
                if call_cost == 0:
                    return PokerAction.CHECK, 0
                # Premium: prefer 3-bet or shove if short
                if category == 'premium':
                    # If very short (<=12bb), shove
                    if self.blind_amount > 0 and remaining_chips <= 12 * self.blind_amount and call_cost < remaining_chips:
                        return PokerAction.ALL_IN, 0  # Runner converts ALL_IN amount
                    # Otherwise make a minimal reraise
                    amt = self._min_reraise_amount(round_state, remaining_chips)
                    if amt > 0:
                        return PokerAction.RAISE, amt
                    return PokerAction.CALL, 0
                # Strong: call with decent pot odds
                if category == 'strong':
                    # Call wider if call is cheap (<= 2BB)
                    cheap = call_cost <= max(2 * max(1, self.blind_amount), int(0.08 * remaining_chips))
                    if pot_odds <= 0.4 or cheap:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
                # Medium: call only if cheap or very favorable odds
                if category == 'medium':
                    if call_cost <= max(2 * max(1, self.blind_amount), int(0.1 * remaining_chips)) or pot_odds <= 0.3:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
                # Weak: fold to any bet
                return PokerAction.FOLD, 0

        # Postflop and later streets
        post_strength = evaluate_postflop_strength(self.hole_cards, round_state.community_cards)
        is_wet, suited_wet, pair_or_conn = board_texture_flags(round_state.community_cards)

        if round_state.current_bet == 0:
            # Consider betting when free
            if post_strength == 'strong':
                amt = self._postflop_bet_amount(round_state, remaining_chips, bb_mult=2.0 if is_wet else 2.5)
                if amt > 0:
                    return PokerAction.RAISE, amt
                return PokerAction.CHECK, 0
            if post_strength == 'medium':
                # C-bet more on dry textures, pot-control on wet/paired/connected boards
                if not is_wet:
                    amt = self._postflop_bet_amount(round_state, remaining_chips, bb_mult=1.0)
                    if amt > 0:
                        return PokerAction.RAISE, amt
                return PokerAction.CHECK, 0
            # Weak: occasional bluff on very dry boards
            if not is_wet:
                seed = (round_state.round_num * 131 + (self.id or 0) * 977 + len(round_state.community_cards) * 37) & 0xFFFFFFFF
                rng = random.Random(seed)
                if rng.random() < 0.22:  # ~22% frequency
                    amt = self._postflop_bet_amount(round_state, remaining_chips, bb_mult=1.0)
                    if amt > 0:
                        return PokerAction.RAISE, amt
            # Otherwise, check
            return PokerAction.CHECK, 0
        else:
            # Facing a bet postflop
            if call_cost == 0:
                return PokerAction.CHECK, 0

            # Short stack with strong hand -> shove
            if post_strength == 'strong' and self.blind_amount > 0 and remaining_chips <= 10 * self.blind_amount and call_cost < remaining_chips:
                return PokerAction.ALL_IN, 0

            if post_strength == 'strong':
                # Allow calls up to ~25% of stack or with good pot odds
                if call_cost <= int(0.25 * remaining_chips) or pot_odds <= 0.35:
                    return PokerAction.CALL, 0
                # Otherwise, fold to very large bets
                return PokerAction.FOLD, 0

            if post_strength == 'medium':
                # Call only if cheap or good odds; on wet boards, be a bit tighter
                cheap = call_cost <= max(1 * max(1, self.blind_amount), int(0.1 * remaining_chips))
                if (cheap or pot_odds <= (0.28 if is_wet else 0.3)):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            # Weak: fold unless the bet is extremely small
            if call_cost <= max(1, self.blind_amount):
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print(f"[on_end_round] id={self.id} chips={remaining_chips} pot={round_state.pot}")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print(f"[on_end_game] id={self.id} score={player_score} all_scores={all_scores} active_hands={active_players_hands}")