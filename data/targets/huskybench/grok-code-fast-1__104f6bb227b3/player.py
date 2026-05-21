from typing import List, Tuple
import eval7
from itertools import combinations
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards = []

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        self.hole_cards = player_hands

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def evaluate_preflop_hand(self, hole_cards: List[str]) -> str:
        if len(hole_cards) != 2:
            return "weak"
        card1, card2 = hole_cards
        rank1 = card1[0] if len(card1) == 2 else card1[:-1]
        rank2 = card2[0] if len(card2) == 2 else card2[:-1]
        suit1 = card1[-1]
        suit2 = card2[-1]
        ranks = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, 'T':10, 'J':11, 'Q':12, 'K':13, 'A':14}
        r1 = ranks.get(rank1, 0)
        r2 = ranks.get(rank2, 0)
        if r1 == r2:
            return "strong"  # pocket pair
        if suit1 == suit2 and abs(r1 - r2) <= 4:
            return "strong"  # suited connectors
        if max(r1, r2) >= 12:  # high cards
            return "medium"
        return "weak"

    def get_best_hand_score(self, hole_cards, community_cards):
        all_cards = hole_cards + community_cards
        if len(all_cards) < 5:
            return 0
        best_score = 0
        for combo in combinations(all_cards, 5):
            hand = eval7.Hand(list(combo))
            score = hand.evaluate()
            if score > best_score:
                best_score = score
        return best_score

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")

        if round_state.round == "preflop":
            hand_strength = self.evaluate_preflop_hand(self.hole_cards)
            if hand_strength == "strong":
                if round_state.current_bet == 0:
                    return PokerAction.RAISE, min(remaining_chips, round_state.min_raise * 3)
                else:
                    return PokerAction.RAISE, min(remaining_chips, round_state.current_bet + round_state.min_raise * 2)
            elif hand_strength == "medium":
                if round_state.current_bet > 0:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.CHECK, 0
            else:  # weak
                if round_state.current_bet > 0:
                    return PokerAction.FOLD, 0
                else:
                    return PokerAction.CHECK, 0
        else:
            # Postflop: use hand evaluation
            hand_score = self.get_best_hand_score(self.hole_cards, round_state.community_cards)
            # Simple thresholds: adjust based on score
            if hand_score > 3000:  # strong hand, e.g., flush or better
                if round_state.current_bet == 0:
                    return PokerAction.RAISE, min(remaining_chips, round_state.min_raise * 2)
                else:
                    return PokerAction.RAISE, min(remaining_chips, round_state.current_bet + round_state.min_raise)
            elif hand_score > 2000:  # medium hand
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.CALL, 0
            else:  # weak hand
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)