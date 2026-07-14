from typing import List, Tuple, Dict
import random

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

# Try to use eval7 for quick equity simulations if available
try:
    import eval7  # type: ignore
    HAS_EVAL7 = True
except Exception:
    HAS_EVAL7 = False


RANK_ORDER = "23456789TJQKA"
RANK_TO_VAL = {r: i + 2 for i, r in enumerate(RANK_ORDER)}


def _parse_card_str(card: str) -> Tuple[str, str]:
    """Split a card string like 'As' into ('A','s')."""
    return card[0], card[1]


def _is_pair(cards: List[str]) -> bool:
    r1, _ = _parse_card_str(cards[0])
    r2, _ = _parse_card_str(cards[1])
    return r1 == r2


def _is_suited(cards: List[str]) -> bool:
    _, s1 = _parse_card_str(cards[0])
    _, s2 = _parse_card_str(cards[1])
    return s1 == s2


def _connected_gap(cards: List[str]) -> int:
    r1, _ = _parse_card_str(cards[0])
    r2, _ = _parse_card_str(cards[1])
    return abs(RANK_TO_VAL[r1] - RANK_TO_VAL[r2]) - 1


def _sorted_ranks(cards: List[str]) -> Tuple[str, str]:
    r1, _ = _parse_card_str(cards[0])
    r2, _ = _parse_card_str(cards[1])
    if RANK_TO_VAL[r1] >= RANK_TO_VAL[r2]:
        return r1, r2
    return r2, r1


def preflop_category(cards: List[str]) -> int:
    """
    Coarse preflop strength category:
      3 - strong, 2 - medium, 1 - speculative, 0 - weak
    """
    r1, r2 = _sorted_ranks(cards)
    suited = _is_suited(cards)
    pair = r1 == r2

    # Strong pairs and broadways
    strong_pairs = set("AKQJT")
    if pair and r1 in strong_pairs:
        return 3
    if (r1, r2) in {("A", "K"), ("A", "Q")}:
        return 3 if suited or r2 == "K" else 2
    if suited and (r1, r2) in {("A", "J"), ("K", "Q")}:
        return 3
    if pair and r1 in set("987"):
        return 2
    if suited and (r1, r2) in {("K", "J"), ("Q", "J"), ("J", "T")}:
        return 2
    if (r1, r2) in {("A", "J"), ("K", "Q")}:
        return 2
    # Small pairs and suited connectors are speculative
    if pair:
        return 1
    gap = _connected_gap(cards)
    if suited and gap <= 1 and RANK_TO_VAL[r1] <= RANK_TO_VAL["T"]:
        return 1
    return 0


def compute_equity_eval7(hole: List[str], board: List[str], iters: int = 250) -> float:
    """
    Monte Carlo equity estimate vs 1 random opponent using eval7.
    Keeps iterations modest for performance.
    """
    if not HAS_EVAL7:
        return 0.0
    deck = [c for c in eval7.Deck()]
    # Remove known cards
    known = [eval7.Card(h) for h in hole] + [eval7.Card(b) for b in board]
    deck = [c for c in deck if c not in known]

    hole_cards = [eval7.Card(h) for h in hole]
    board_cards = [eval7.Card(b) for b in board]

    wins = ties = 0
    for _ in range(iters):
        random.shuffle(deck)
        opp = deck[0:2]
        needed = 5 - len(board_cards)
        sim_board = board_cards + deck[2:2 + needed]
        our_score = eval7.evaluate(hole_cards + sim_board)
        opp_score = eval7.evaluate(opp + sim_board)
        if our_score > opp_score:
            wins += 1
        elif our_score == opp_score:
            ties += 1
    total = iters
    return (wins + 0.5 * ties) / total if total > 0 else 0.0


def _board_ranks(board: List[str]) -> List[str]:
    return [c[0] for c in board] if board else []


def _board_max_rank_val(board: List[str]) -> int:
    ranks = _board_ranks(board)
    return max((RANK_TO_VAL[r] for r in ranks), default=0)


def _hole_ranks(cards: List[str]) -> Tuple[str, str]:
    r1, _ = _parse_card_str(cards[0])
    r2, _ = _parse_card_str(cards[1])
    return r1, r2


def _hole_suits(cards: List[str]) -> Tuple[str, str]:
    _, s1 = _parse_card_str(cards[0])
    _, s2 = _parse_card_str(cards[1])
    return s1, s2


def _has_top_pair(hole: List[str], board: List[str]) -> bool:
    if not board:
        return False
    top = _board_max_rank_val(board)
    r1, r2 = _hole_ranks(hole)
    return RANK_TO_VAL[r1] == top or RANK_TO_VAL[r2] == top


def _has_overpair(hole: List[str], board: List[str]) -> bool:
    if not board:
        return False
    if not _is_pair(hole):
        return False
    r, _ = _hole_ranks(hole)
    return RANK_TO_VAL[r] > _board_max_rank_val(board)


def _has_flush_draw(hole: List[str], board: List[str]) -> bool:
    # Simple 4-to-a-flush detection including at least one hole card
    if not board:
        return False
    suits = [c[1] for c in board + hole]
    hole_suits = set(_hole_suits(hole))
    suit_counts: Dict[str, int] = {}
    for s in suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    # Need 4 or more of a suit overall and we should contribute at least one
    for s, cnt in suit_counts.items():
        if cnt >= 4 and s in hole_suits:
            return True
    return False


class SimplePlayer(Bot):
    """
    Improved simple player with:
    - basic preflop hand categorization
    - postflop pot-odds driven decisions + simple c-bet/top-pair logic
    - lightweight equity simulation when eval7 is available
    - equity caching to reduce per-street computation
    """
    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []
        self.blind_amount: int = 0
        self.big_blind_player_id: int = None
        self.small_blind_player_id: int = None
        self.all_players: List[int] = []
        self.preflop_cat: int = 0
        self.was_preflop_raiser: bool = False
        self._equity_cache_key: str = ""
        self._equity_cache_value: float = 0.0

    def _reset_equity_cache(self):
        self._equity_cache_key = ""
        self._equity_cache_value = 0.0

    def _equity_cache_try_get(self, round_state: RoundStateClient) -> Tuple[bool, float]:
        key = f"{round_state.round}:{''.join(round_state.community_cards or [])}"
        if key == self._equity_cache_key:
            return True, self._equity_cache_value
        return False, 0.0

    def _equity_cache_set(self, round_state: RoundStateClient, value: float):
        self._equity_cache_key = f"{round_state.round}:{''.join(round_state.community_cards or [])}"
        self._equity_cache_value = value

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int,
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Store context for decision making
        self.hole_cards = list(player_hands) if player_hands else []
        self.blind_amount = blind_amount or 0
        self.big_blind_player_id = big_blind_player_id
        self.small_blind_player_id = small_blind_player_id
        self.all_players = all_players or []
        # Precompute preflop category
        if len(self.hole_cards) == 2:
            self.preflop_cat = preflop_category(self.hole_cards)
        else:
            self.preflop_cat = 0
        self.was_preflop_raiser = False
        self._reset_equity_cache()
        print(f"[Bot {self.id}] Game start. Hole cards: {self.hole_cards}, blind: {self.blind_amount}")

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        # Reset equity cache on new street
        self._reset_equity_cache()
        print(f"[Bot {self.id}] Round start. Round: {round_state.round}, Pot: {round_state.pot}")

    def _call_amount(self, round_state: RoundStateClient) -> int:
        me = str(self.id)
        my_bet = round_state.player_bets.get(me, 0) if round_state.player_bets else 0
        return max(0, round_state.current_bet - my_bet)

    def _any_raised(self, round_state: RoundStateClient) -> bool:
        if not round_state.player_actions:
            return False
        for act in round_state.player_actions.values():
            if str(act).lower() in ("raise", "all in", "all_in", "allin", "bet"):
                return True
        return False

    def _bounded_raise(self, round_state: RoundStateClient, remaining_chips: int, target: int) -> int:
        mn = max(1, int(round_state.min_raise or 1))
        mx = max(mn, int(round_state.max_raise or mn))
        amt = max(mn, min(mx, int(target)))
        return max(1, min(amt, remaining_chips))

    def _default_raise_size(self, round_state: RoundStateClient, remaining_chips: int) -> int:
        # Pot-size raise heuristic: 2.5x preflop, 60-80% pot postflop
        pot = round_state.pot or 0
        min_raise = max(1, int(round_state.min_raise or 1))
        if str(round_state.round).lower() == "preflop":
            base = max(min_raise, int(max(2.2 * self.blind_amount, pot * 0.9)))
        else:
            # Between 60% and 80% pot randomly to vary sizing
            frac = 0.6 + 0.2 * random.random()
            base = max(min_raise, int(max(pot * frac, min_raise)))
        return self._bounded_raise(round_state, remaining_chips, base)

    def _equity_or_heuristic(self, round_state: RoundStateClient) -> float:
        """
        Return equity estimate if possible; else a heuristic proxy:
        - preflop: map category to equity guess
        - postflop: conservative default 0.45
        Uses cache per street to avoid recomputation.
        """
        cached, val = self._equity_cache_try_get(round_state)
        if cached:
            return val

        board = round_state.community_cards or []
        if HAS_EVAL7 and len(self.hole_cards) == 2:
            try:
                iters = 220 if str(round_state.round).lower() == "preflop" else 280
                val = compute_equity_eval7(self.hole_cards, board, iters)
                self._equity_cache_set(round_state, val)
                return val
            except Exception:
                pass
        if str(round_state.round).lower() == "preflop":
            val = {3: 0.66, 2: 0.57, 1: 0.50, 0: 0.43}.get(self.preflop_cat, 0.45)
        else:
            val = 0.45
        self._equity_cache_set(round_state, val)
        return val

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """Decide action using preflop rules and postflop pot-odds + simple board-aware logic."""
        print(f"[Bot {self.id}] Acting. Round: {round_state.round}, Pot: {round_state.pot}, Bet: {round_state.current_bet}")

        call_amount = self._call_amount(round_state)
        pot = round_state.pot or 0
        any_raised = self._any_raised(round_state)
        board = round_state.community_cards or []

        # If nothing to call, decide whether to raise or check based on strength
        if round_state.current_bet == 0:
            if str(round_state.round).lower() == "preflop":
                if self.preflop_cat >= 3:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    self.was_preflop_raiser = True
                    return PokerAction.RAISE, amt
                if self.preflop_cat == 2 and random.random() < 0.6:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    self.was_preflop_raiser = True
                    return PokerAction.RAISE, amt
                # Limp/check otherwise
                return PokerAction.CHECK, 0
            else:
                # Postflop: c-bet occasionally as preflop aggressor, and value bet with decent made hands
                top_pair = _has_top_pair(self.hole_cards, board)
                overpair = _has_overpair(self.hole_cards, board)
                flush_draw = _has_flush_draw(self.hole_cards, board)

                if overpair or top_pair:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    return PokerAction.RAISE, amt
                if flush_draw and random.random() < 0.5:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    return PokerAction.RAISE, amt
                if self.was_preflop_raiser and self.preflop_cat >= 1 and random.random() < 0.5:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    return PokerAction.RAISE, amt
                return PokerAction.CHECK, 0

        # There is a bet to call
        # Preflop facing a raise
        if str(round_state.round).lower() == "preflop":
            if self.preflop_cat >= 3:
                # Strong: mostly continue; occasionally re-raise
                if any_raised and random.random() < 0.28:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    self.was_preflop_raiser = True
                    return PokerAction.RAISE, amt
                return PokerAction.CALL, 0
            if self.preflop_cat == 2:
                # Medium: call if affordable relative to stack
                if call_amount <= max(self.blind_amount * 6, remaining_chips // 10):
                    return PokerAction.CALL, 0
                return PokerAction.FOLD, 0
            # Speculative/weak: fold to raises unless very cheap
            if call_amount <= self.blind_amount and random.random() < 0.18:
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Postflop: use pot odds with equity estimate + simple hand features
        eq = self._equity_or_heuristic(round_state)
        threshold = call_amount / max(1, (pot + call_amount))  # break-even equity

        top_pair = _has_top_pair(self.hole_cards, board)
        overpair = _has_overpair(self.hole_cards, board)
        flush_draw = _has_flush_draw(self.hole_cards, board)

        # If we have strong made hand, prefer continuing and sometimes raising
        if overpair or top_pair:
            if random.random() < 0.35:
                amt = self._default_raise_size(round_state, remaining_chips)
                return PokerAction.RAISE, amt
            return PokerAction.CALL, 0

        # Semi-bluff with draws
        if flush_draw:
            # Be mindful of pot odds; treat draw equity ~35%
            draw_eq = max(eq, 0.35)
            if draw_eq > max(0.5, threshold + 0.03):
                if random.random() < 0.30:
                    amt = self._default_raise_size(round_state, remaining_chips)
                    return PokerAction.RAISE, amt
                return PokerAction.CALL, 0
            if draw_eq >= threshold:
                return PokerAction.CALL, 0
            return PokerAction.FOLD, 0

        # Default pot-odds logic
        if eq > max(0.55, threshold + 0.05):
            if random.random() < 0.30:
                amt = self._default_raise_size(round_state, remaining_chips)
                return PokerAction.RAISE, amt
            return PokerAction.CALL, 0
        if eq >= threshold:
            return PokerAction.CALL, 0
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print(f"[Bot {self.id}] End of round. Chips: {remaining_chips}")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print(f"[Bot {self.id}] Game end. Score: {player_score}")
        print(f"[Bot {self.id}] All final scores: {all_scores}")
        if active_players_hands:
            print(f"[Bot {self.id}] Active players hands: {active_players_hands}")