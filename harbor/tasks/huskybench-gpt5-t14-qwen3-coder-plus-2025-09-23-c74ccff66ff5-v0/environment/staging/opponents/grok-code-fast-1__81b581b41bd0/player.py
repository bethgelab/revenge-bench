from typing import List, Tuple
import random
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.ranks = {"2":2, "3":3, "4":4, "5":5, "6":6, "7":7, "8":8, "9":9, "T":10, "J":11, "Q":12, "K":13, "A":14}

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        self.hole_cards = player_hands
        self.position = "BB" if self.id == big_blind_player_id else "SB"
        print("My id: ", self.id)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def get_preflop_rank(self):
        card1, card2 = self.hole_cards
        r1 = self.ranks[card1[0]]
        r2 = self.ranks[card2[0]]
        suited = card1[1] == card2[1]
        high = max(r1, r2)
        low = min(r1, r2)
        if r1 == r2:
            return 100 + high
        elif suited:
            return high * 10 + low
        else:
            return high * 10 + low - 5

    def evaluate_hand(self, hole_cards, community_cards):
        all_cards = hole_cards + community_cards
        ranks = sorted([self.ranks[c[0]] for c in all_cards], reverse=True)
        suits = [c[1] for c in all_cards]
        rank_count = {}
        for r in ranks:
            rank_count[r] = rank_count.get(r, 0) + 1
        suit_count = {}
        for s in suits:
            suit_count[s] = suit_count.get(s, 0) + 1
        flush_suit = None
        for s, c in suit_count.items():
            if c >= 5:
                flush_suit = s
        if flush_suit:
            flush_ranks = sorted([self.ranks[c[0]] for c in all_cards if c[1] == flush_suit], reverse=True)
            if self.is_straight(flush_ranks):
                return 800 + max(flush_ranks)
            else:
                return 500 + max(flush_ranks)
        if self.is_straight(ranks):
            return 400 + max(ranks)
        pairs = [r for r, c in rank_count.items() if c == 2]
        triples = [r for r, c in rank_count.items() if c == 3]
        quads = [r for r, c in rank_count.items() if c == 4]
        if quads:
            return 700 + quads[0]
        if triples and pairs:
            return 600 + triples[0]
        if triples:
            return 300 + triples[0]
        if len(pairs) >= 2:
            return 200 + max(pairs)
        if pairs:
            return 100 + pairs[0]
        return max(ranks)

    def is_straight(self, ranks):
        ranks = sorted(set(ranks), reverse=True)
        for i in range(len(ranks) - 4):
            if ranks[i] - ranks[i+4] == 4:
                return True
        if 14 in ranks and 2 in ranks and 3 in ranks and 4 in ranks and 5 in ranks:
            return True
        return False

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        if round_state.round == "preflop":
            threshold_strong = 125 if self.position == "SB" else 115
            threshold_medium = 115 if self.position == "SB" else 105
            fold_pct = 0.10 if self.position == "SB" else 0.05
            rank = self.get_preflop_rank()
            if rank > threshold_strong:
                amount = min(round_state.max_raise, remaining_chips, round_state.current_bet + round_state.min_raise * 3)
                return PokerAction.RAISE, amount
            elif rank > threshold_medium:
                if round_state.current_bet == 0:
                    amount = min(round_state.max_raise, remaining_chips, round_state.min_raise * 2)
                    return PokerAction.RAISE, amount
            else:
                if round_state.current_bet > remaining_chips * fold_pct:
                    return PokerAction.FOLD, 0
                else:
                    if round_state.current_bet == 0 and random.random() < 0.05:
                        amount = min(round_state.max_raise, remaining_chips, round_state.min_raise)
                        return PokerAction.RAISE, amount
                    else:
                        return PokerAction.CALL, 0
        else:
            hand_score = self.evaluate_hand(self.hole_cards, round_state.community_cards)
            if round_state.current_bet == 0:
                if hand_score > 200:
                    amount = min(round_state.max_raise, remaining_chips, round_state.min_raise * 2)
                    return PokerAction.RAISE, amount
                elif random.random() < 0.1:
                    amount = min(round_state.max_raise, remaining_chips, round_state.min_raise)
                    return PokerAction.RAISE, amount
                else:
                    return PokerAction.CHECK, 0
            else:
                pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                if hand_score > 100 and pot_odds < 0.5:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)