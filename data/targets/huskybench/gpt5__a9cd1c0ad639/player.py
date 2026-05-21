from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

RANK_ORDER = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
HIGH_RANKS = set(['T', 'J', 'Q', 'K', 'A'])

def parse_card(card: str):
    # card format like "As", "Td"
    if not card or len(card) < 2:
        return '2', 's'
    return card[0], card[1].lower()

def preflop_score(cards: List[str]) -> int:
    """Very fast heuristic score 0-100 based on two hole cards."""
    if len(cards) < 2:
        return 0
    r1, s1 = parse_card(cards[0])
    r2, s2 = parse_card(cards[1])
    v1, v2 = RANK_ORDER.get(r1, 0), RANK_ORDER.get(r2, 0)
    suited = s1 == s2
    highcards = sum([1 for r in (r1, r2) if r in HIGH_RANKS])
    pair = r1 == r2
    gap = abs(v1 - v2)
    top = max(v1, v2)

    score = 0
    if pair:
        # Pocket pairs
        if v1 >= 10:       # TT+
            score = 85 + (v1 - 10)  # up to 89 for AA
        elif v1 >= 7:      # 77-99
            score = 68 + (v1 - 7)   # 68-70
        else:              # small pairs
            score = 58 + (v1 - 2)   # 58-64
    else:
        # Broadways and Ax
        if {'A', 'K'}.issubset({r1, r2}):
            score = 78 if suited else 72
        elif {'A', 'Q'}.issubset({r1, r2}):
            score = 76 if suited else 70
        elif {'A', 'J'}.issubset({r1, r2}):
            score = 72 if suited else 66
        elif {'K', 'Q'}.issubset({r1, r2}):
            score = 70 if suited else 64
        elif {'K', 'J'}.issubset({r1, r2}):
            score = 66 if suited else 60
        elif {'Q', 'J'}.issubset({r1, r2}):
            score = 64 if suited else 58
        elif r1 == 'A' or r2 == 'A':
            # Other Ax
            score = 62 if suited else 54
        else:
            # Suited connectors and gappers
            if suited and gap == 1 and top >= 10:
                score = 62  # T9s, JTs
            elif suited and gap == 1 and top >= 8:
                score = 58  # 98s, 87s
            elif suited and gap == 2 and top >= 9:
                score = 55  # T8s, 97s
            elif suited and highcards >= 1:
                score = 52  # Kxs/Qxs/Jxs suited
            elif gap <= 1 and top >= 10:
                score = 50  # Offsuit broadway-ish
            else:
                score = 40 if suited else 35
    # Slight kicker bonus
    score += (top - 10) * 0.5 if top > 10 else 0
    return int(score)

def _ranks_list(cards: List[str]) -> List[int]:
    out = []
    for c in cards or []:
        r, _ = parse_card(c)
        out.append(RANK_ORDER.get(r, 0))
    return out

def _ranks_set_lowace(cards: List[str]) -> set:
    # include Ace as 1 for wheel checks
    s = set(_ranks_list(cards))
    if 14 in s:
        s.add(1)
    return s

def flush_draw(hole: List[str], board: List[str]) -> bool:
    if not hole:
        return False
    suits = {}
    for c in (hole or []) + (board or []):
        _, s = parse_card(c)
        suits[s] = suits.get(s, 0) + 1
    # Flush draw if 4+ cards of same suit among hole+board
    return any(cnt >= 4 for cnt in suits.values())

def straight_draw(hole: List[str], board: List[str]) -> bool:
    # Simple window-of-5 heuristic: if in any 5-rank window we have exactly 4 ranks present, we have a straight draw
    ranks = _ranks_set_lowace((hole or []) + (board or []))
    for k in range(1, 11):  # windows [k..k+4]
        present = 0
        for x in range(k, k + 5):
            if x in ranks:
                present += 1
        if present == 4:
            return True
    return False

def postflop_pair_info(hole: List[str], board: List[str]) -> Tuple[bool, bool, bool, bool]:
    """
    Returns tuple: (has_pair, is_overpair, is_top_pair, is_middle_or_underpair)
    - overpair: pocket pair higher than all board ranks
    - top pair: hole matches top board rank
    - middle/underpair: any other pair (including pocket pair under top board or pairing lower board rank)
    """
    if len(hole) < 2 or not board:
        # Preflop or no board: pocket pair counts as pair but not over/top classification
        r1, _ = parse_card(hole[0]) if hole else ('2', 's')
        r2, _ = parse_card(hole[1]) if len(hole) > 1 else ('2', 's')
        v1, v2 = RANK_ORDER.get(r1, 0), RANK_ORDER.get(r2, 0)
        pair = v1 == v2 and len(board or []) >= 3  # only consider on flop+ for postflop logic
        return (pair, False, False, pair)
    branks = _ranks_list(board)
    top_board = max(branks) if branks else 0
    r1, _ = parse_card(hole[0])
    r2, _ = parse_card(hole[1])
    v1, v2 = RANK_ORDER.get(r1, 0), RANK_ORDER.get(r2, 0)
    pocket_pair = v1 == v2
    match1 = v1 in branks
    match2 = v2 in branks
    is_top = (match1 and v1 == top_board) or (match2 and v2 == top_board)
    is_over = pocket_pair and v1 > top_board
    has_any = pocket_pair or match1 or match2
    is_midunder = has_any and not is_over and not is_top
    return (has_any, is_over, is_top, is_midunder)

def has_high_card(hole: List[str]) -> bool:
    if not hole:
        return False
    r1, _ = parse_card(hole[0])
    r2, _ = parse_card(hole[1]) if len(hole) > 1 else ('2', 's')
    return (r1 in HIGH_RANKS) or (r2 in HIGH_RANKS)

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []
        self.blind_amount: int = 0
        self.big_blind_player_id = None
        self.small_blind_player_id = None
        self.all_players: List[int] = []
        self.was_preflop_raiser: bool = False

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        # Store context for the round
        self.hole_cards = player_hands or []
        self.blind_amount = blind_amount or 0
        self.big_blind_player_id = big_blind_player_id
        self.small_blind_player_id = small_blind_player_id
        self.all_players = all_players or []
        self.was_preflop_raiser = False
        # Minimal print to avoid heavy I/O
        print(f"Start: my_id={self.id}, hole={self.hole_cards}, blind={self.blind_amount}")

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        # Minimal logging to avoid overhead
        pass

    def _my_bet(self, round_state: RoundStateClient) -> int:
        return round_state.player_bets.get(str(self.id), 0)

    def _call_amount(self, round_state: RoundStateClient) -> int:
        return max(0, round_state.current_bet - self._my_bet(round_state))

    def _raise_delta_to(self, round_state: RoundStateClient, target_total: int) -> int:
        # Amount field expects delta from current personal bet to reach target_total
        my_bet = self._my_bet(round_state)
        return max(0, target_total - my_bet)

    def _bounded_target(self, round_state: RoundStateClient, target_total: int) -> int:
        # Respect min/max raise if available; fallback to simple bounds
        try:
            if round_state.current_bet == 0:
                # Opening raise: min_total is at least min_raise if provided, else at least 2bb
                min_total = round_state.min_raise if round_state.min_raise > 0 else max(self.blind_amount * 2, target_total)
            else:
                # Subsequent raises: need to be at least current_bet + min_raise
                min_total = max(round_state.current_bet + max(round_state.min_raise, 0), self._my_bet(round_state))
            max_total = round_state.max_raise if round_state.max_raise and round_state.max_raise > 0 else target_total
            return max(min_total, min(target_total, max_total))
        except Exception:
            return target_total

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        round_name = (round_state.round or "").lower()
        call_amt = self._call_amount(round_state)
        pot = round_state.pot
        my_bet = self._my_bet(round_state)
        current_bet = round_state.current_bet
        num_players = max(2, len(self.all_players) or 2)

        # Preflop strategy (slightly wider for heads-up and SB)
        if round_name.startswith("preflop"):
            score = preflop_score(self.hole_cards)
            # Heads-up and SB adjustments
            base_open = 50
            if num_players <= 2:
                base_open -= 5
            if self.id == self.small_blind_player_id:
                base_open -= 5
            base_call = base_open
            three_bet_thresh = 75 if num_players <= 2 else 80
            jam_thresh = 88

            open_size = max(self.blind_amount * 3, current_bet)  # aim ~3bb open

            if current_bet == 0:
                if score >= base_open:
                    # Open raise to ~3bb
                    target_total = max(open_size, self.blind_amount * 3)
                    target_total = self._bounded_target(round_state, target_total)
                    self.was_preflop_raiser = True
                    return PokerAction.RAISE, self._raise_delta_to(round_state, target_total)
                else:
                    return PokerAction.CHECK, 0
            else:
                # Facing raise
                raise_size = current_bet - my_bet
                # If very large raise relative to blind and stack, fold most hands
                if raise_size >= max(self.blind_amount * 6, int(0.22 * remaining_chips)):
                    if score >= jam_thresh:
                        # Strongest hands can jam
                        self.was_preflop_raiser = True
                        return PokerAction.ALL_IN, remaining_chips
                    return PokerAction.FOLD, 0
                # 3-bet best hands, call medium, fold trash
                if score >= three_bet_thresh:
                    # 3-bet to around 2x current bet total
                    target_total = max(current_bet + round_state.min_raise, int(current_bet * 2))
                    target_total = self._bounded_target(round_state, target_total)
                    delta = self._raise_delta_to(round_state, target_total)
                    if delta >= remaining_chips:
                        self.was_preflop_raiser = True
                        return PokerAction.ALL_IN, remaining_chips
                    self.was_preflop_raiser = True
                    return PokerAction.RAISE, delta
                elif score >= base_call:
                    if call_amt >= remaining_chips:
                        return PokerAction.ALL_IN, remaining_chips
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0

        # Postflop simple rules with improved hand classification and pot odds
        board = round_state.community_cards or []
        board_count = len(board)
        have_pair, is_overpair, is_top_pair, is_midunder = postflop_pair_info(self.hole_cards, board)
        fdraw = flush_draw(self.hole_cards, board)
        sdraw = straight_draw(self.hole_cards, board)
        combo_draw = fdraw and sdraw
        have_high = has_high_card(self.hole_cards)

        def pot_odds_ok(call_amount: int, assumed_equity: float) -> bool:
            if call_amount <= 0:
                return True
            denom = pot + call_amount
            if denom <= 0:
                return False
            pot_odds = call_amount / float(denom)
            # Require equity edge; cap vs stack to avoid spew
            # Tighter on river
            cap = 0.25 if board_count == 5 else 0.3
            return (assumed_equity * 0.97) >= pot_odds and call_amount <= int(cap * remaining_chips)

        # Equity heuristics by street
        if board_count >= 3:
            if is_overpair:
                eq = 0.62 if board_count == 3 else (0.54 if board_count == 4 else 0.50)
            elif is_top_pair:
                eq = 0.58 if board_count == 3 else (0.50 if board_count == 4 else 0.45)
            elif is_midunder or have_pair:
                eq = 0.40 if board_count == 3 else (0.30 if board_count == 4 else 0.20)
            elif combo_draw and board_count == 3:
                eq = 0.46
            elif fdraw and board_count >= 3:
                eq = 0.35 if board_count == 3 else 0.20
            elif sdraw and board_count >= 3:
                eq = 0.31 if board_count == 3 else 0.17
            elif have_high and board_count == 3:
                eq = 0.22
            else:
                eq = 0.05 if board_count == 5 else 0.08
        else:
            eq = 0.08

        # If no bet, decide to value/draw bet or check, with c-bets as preflop aggressor
        if current_bet == 0:
            # Value/draw bet: around 40-60% pot
            if is_overpair or is_top_pair or (combo_draw and board_count == 3) or (fdraw and board_count >= 3):
                target_frac = 0.55 if (is_overpair or is_top_pair) else 0.5
                bet_size = max(self.blind_amount * 2, int(target_frac * max(pot, self.blind_amount * 3)))
                target_total = max(current_bet + max(round_state.min_raise, 0), my_bet + bet_size)
                target_total = self._bounded_target(round_state, target_total)
                delta = self._raise_delta_to(round_state, target_total)
                if delta >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.RAISE, delta
            # Flop continuation bet when we had the initiative
            if self.was_preflop_raiser and board_count == 3 and (have_high or fdraw or sdraw):
                bet_size = max(self.blind_amount * 2, int(0.4 * max(pot, self.blind_amount * 3)))
                target_total = max(current_bet + max(round_state.min_raise, 0), my_bet + bet_size)
                target_total = self._bounded_target(round_state, target_total)
                delta = self._raise_delta_to(round_state, target_total)
                if delta >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.RAISE, delta
            return PokerAction.CHECK, 0
        else:
            # Facing a bet: use pot odds for calls, small raises for thin value with pairs
            # On river, do not chase draws
            if board_count == 5 and not (is_overpair or is_top_pair) and (fdraw or sdraw or combo_draw):
                return PokerAction.FOLD, 0

            if pot_odds_ok(call_amt, eq):
                if call_amt >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.CALL, 0

            # Occasional small raise with pairs vs small bets
            small_bet_threshold = int(0.35 * max(pot, self.blind_amount * 3))
            if (is_overpair or is_top_pair) and call_amt <= min(small_bet_threshold, self.blind_amount * 2):
                target_total = max(current_bet + max(round_state.min_raise, 0), current_bet + self.blind_amount * 2)
                target_total = self._bounded_target(round_state, target_total)
                delta = self._raise_delta_to(round_state, target_total)
                if delta >= remaining_chips:
                    return PokerAction.ALL_IN, remaining_chips
                return PokerAction.RAISE, delta

            return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Game end. Score:", player_score)
        # Minimal summary
        # print("All final scores: ", all_scores)
        # print("Active players hands: ", active_players_hands)