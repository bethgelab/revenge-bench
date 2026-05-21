from typing import List, Tuple
import eval7

# Flexible imports so the file works both as part of the `client` package
# and when run directly from the repo root (e.g. in pytest).
try:
    from client.bot import Bot
except ModuleNotFoundError:
    from bot import Bot

try:
    from client.type.poker_action import PokerAction
except ModuleNotFoundError:
    from type.poker_action import PokerAction

try:
    from client.type.round_state import RoundStateClient
except ModuleNotFoundError:
    from type.round_state import RoundStateClient


class MonteCarloPlayer(Bot):
    """
    A moderately smart poker bot:

    â¢ Pre-flop: uses simple heuristics (pair strength, suited, connectivity,
      high cards) to categorise hands and decides whether to raise, call/check
      or fold.

    â¢ Post-flop: runs a small Monte-Carlo simulation (default 50 rollouts)
      with `eval7` to estimate win equity versus 1 random opponent, then acts:

        â equity > 0.70 â aggressive (raise or bet)
        â equity > 0.40 â continue (call or check)
        â else          â fold or check

    The bot is kept intentionally light so that it comfortably finishes within
    the 10-second simulation limit.
    """

    N_SAMPLES = 50  # Monte-Carlo iterations (keep tiny for speed)

    RANK_ORDER = "23456789TJQKA"
    RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER, start=2)}

    def __init__(self):
        super().__init__()
        self.hole_cards: List[str] = []  # our two cards as strings, e.g. ["As", "Kd"]
        self.cached_strength = None      # strength cache per board texture
        self.cached_board = ""           # to avoid recomputing on identical boards

    # ------------------------------------------------------------------ #
    # Life-cycle callbacks
    # ------------------------------------------------------------------ #
    def on_start(
        self,
        starting_chips: int,
        player_hands: List[str],
        blind_amount: int,
        big_blind_player_id: int,
        small_blind_player_id: int,
        all_players: List[int],
    ):
        # Store our hole cards (assume first two belong to us)
        if len(player_hands) >= 2:
            self.hole_cards = player_hands[:2]
        else:
            self.hole_cards = []

        # Reset caches
        self.cached_strength = None
        self.cached_board = ""

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.cached_strength = None
        self.cached_board = ""

    # ------------------------------------------------------------------ #
    # Decision making
    # ------------------------------------------------------------------ #
    def get_action(
        self, round_state: RoundStateClient, remaining_chips: int
    ) -> Tuple[PokerAction, int]:
        strength = self._get_strength(round_state)

        current_bet = round_state.current_bet
        min_raise = round_state.min_raise or 0

        # -------- PREFLOP STRATEGY -------- #
        if round_state.round.lower() == "preflop":
            if current_bet == 0:
                if strength > 0.7:
                    raise_amt = max(min_raise, 2 * min_raise)
                    raise_amt = min(raise_amt, remaining_chips)
                    return PokerAction.RAISE, raise_amt
                else:
                    return PokerAction.CHECK, 0
            else:
                if strength < 0.4:
                    return PokerAction.FOLD, 0
                elif strength > 0.7 and remaining_chips > min_raise:
                    raise_amt = min(min_raise, remaining_chips)
                    return PokerAction.RAISE, raise_amt
                else:
                    return PokerAction.CALL, 0

        # -------- POSTFLOP STRATEGY -------- #
        if current_bet == 0:
            if strength > 0.7:
                bet = max(min_raise, int(0.1 * remaining_chips))
                bet = min(bet, remaining_chips)
                return PokerAction.RAISE, bet
            else:
                return PokerAction.CHECK, 0
        else:
            if strength < 0.3:
                return PokerAction.FOLD, 0
            elif strength > 0.7 and remaining_chips > min_raise:
                bet = min(min_raise, remaining_chips)
                return PokerAction.RAISE, bet
            else:
                return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        self.cached_strength = None
        self.cached_board = ""

    def on_end_game(
        self,
        round_state: RoundStateClient,
        player_score: float,
        all_scores: dict,
        active_players_hands: dict,
    ):
        pass

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_strength(self, round_state: RoundStateClient) -> float:
        board_key = "".join(sorted(round_state.community_cards))
        if self.cached_board == board_key and self.cached_strength is not None:
            return self.cached_strength

        if not self.hole_cards or len(self.hole_cards) != 2:
            return 0.0  # unknown hand

        if round_state.round.lower() == "preflop":
            strength = self._preflop_heuristic(self.hole_cards)
        else:
            strength = self._monte_carlo_strength(
                self.hole_cards, round_state.community_cards
            )

        self.cached_board = board_key
        self.cached_strength = strength
        return strength

    # ---------------- Strength evaluators ---------------- #
    def _preflop_heuristic(self, hand: List[str]) -> float:
        ranks = [card[0] for card in hand]
        suits = [card[1] for card in hand]
        vals = sorted([self.RANK_VALUE[r] for r in ranks], reverse=True)

        # Pair
        if ranks[0] == ranks[1]:
            base = 0.6 + (vals[0] - 2) / 25  # AA ~0.98, 22 ~0.6
            return min(base, 0.99)

        # Suited / connected / high-card bonuses
        suited = suits[0] == suits[1]
        connected = abs(vals[0] - vals[1]) == 1
        high_card_bonus = (vals[0] - 8) / 20 if vals[0] >= 10 else 0

        score = 0.3
        if suited:
            score += 0.05
        if connected:
            score += 0.02
        score += high_card_bonus
        score += (vals[0] + vals[1] - 7) / 60  # general high-card weight
        return max(0.0, min(score, 0.95))

    def _monte_carlo_strength(
        self, hole_cards: List[str], community_cards: List[str]
    ) -> float:
        deck = eval7.Deck()

        known_cards = [eval7.Card(c) for c in hole_cards + community_cards]
        for kc in known_cards:
            deck.cards.remove(kc)

        our_hand = [eval7.Card(c) for c in hole_cards]
        wins = ties = 0

        remaining_comm = 5 - len(community_cards)
        board_so_far = [eval7.Card(c) for c in community_cards]

        for _ in range(self.N_SAMPLES):
            deck.shuffle()
            draw = deck.peek(remaining_comm + 2)
            opp_hand = draw[:2]
            future_board = draw[2:]

            full_board = board_so_far + future_board
            our_val = eval7.evaluate(our_hand + full_board)
            opp_val = eval7.evaluate(list(opp_hand) + full_board)

            if our_val > opp_val:
                wins += 1
            elif our_val == opp_val:
                ties += 1

        return (wins + 0.5 * ties) / self.N_SAMPLES


# --- Pot-odds-aware extension ---------------------------------------------- #
class PotOddsPlayer(MonteCarloPlayer):
    CALL_MARGIN = 0.05
    AGGRO_THRESHOLD = 0.75

    def get_action(self, round_state: RoundStateClient, remaining_chips: int):
        strength = self._get_strength(round_state)

        current_bet = round_state.current_bet
        min_raise = round_state.min_raise or 0
        pot_size = round_state.pot

        my_contrib = round_state.player_bets.get(str(self.id), 0)
        to_call = max(current_bet - my_contrib, 0)

        if to_call == 0:
            return super().get_action(round_state, remaining_chips)

        pot_odds = to_call / (pot_size + to_call) if (pot_size + to_call) > 0 else 1.0
        if strength < pot_odds - self.CALL_MARGIN:
            return PokerAction.FOLD, 0

        if strength >= self.AGGRO_THRESHOLD and remaining_chips > to_call + min_raise:
            raise_amt = max(min_raise, to_call * 2)
            raise_amt = min(raise_amt, remaining_chips)
            return PokerAction.RAISE, raise_amt

        return PokerAction.CALL, 0


# Default alias used elsewhere
SimplePlayer = PotOddsPlayer