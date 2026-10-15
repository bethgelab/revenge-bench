import eval7
import random
import json
from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = None
        self.position = None
        self.opponent_raise_count = 0
        self.opponent_fold_count = 0
        self.opponent_call_count = 0
        self.opponent_stats = {}
        self.round_raises = 0
        self.previous_actions = {}

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        if self.id == big_blind_player_id:
            self.position = "BB"
        elif self.id == small_blind_player_id:
            self.position = "SB"
        else:
            self.position = "Unknown"
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        self.hand = [eval7.Card(c) for c in player_hands]
        try:
            with open("opponent_stats.json", "r") as f:
                self.opponent_stats = json.load(f)
        except:
            self.opponent_stats.setdefault("total_raises", 0)
            self.opponent_stats.setdefault("total_folds", 0)
            self.opponent_stats.setdefault("total_calls", 0)
            self.opponent_stats.setdefault("rounds", 0)
        self.opponent_stats.setdefault("total_raises", 0)
        self.opponent_stats.setdefault("total_folds", 0)
        self.opponent_stats.setdefault("total_calls", 0)
        self.opponent_stats.setdefault("rounds", 0)
    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Round state: ", round_state)
        self.opponent_raise_count = 0
        self.opponent_fold_count = 0
        self.opponent_call_count = 0
        self.round_raises = 0
        self.opponent_raises_this_round = 0
        self.opponent_folds_this_round = 0
        self.opponent_calls_this_round = 0
        self.previous_actions = {}

    def evaluate_hand(self, community_cards: List[str]) -> int:
        board = [eval7.Card(c) for c in community_cards]
        return eval7.equity(self.hand, board)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        # Update cumulative counters for this round
        for pid, act in round_state.player_actions.items():
            if pid != self.id:
                prev_act = self.previous_actions.get(pid)
                if act == "Raise" and prev_act != "Raise":
                    self.opponent_raises_this_round += 1
                if act == "Fold" and prev_act != "Fold":
                    self.opponent_folds_this_round += 1
                if act == "Call" and prev_act != "Call":
                    self.opponent_calls_this_round += 1
        self.previous_actions = round_state.player_actions.copy()
        
        self.opponent_raise_count = self.opponent_raises_this_round
        self.opponent_call_count = self.opponent_calls_this_round
        self.opponent_fold_count = self.opponent_folds_this_round
        self.round_raises = self.opponent_raise_count

        if self.hand is None:
            return PokerAction.FOLD, 0

        strength = self.evaluate_hand(round_state.community_cards)
        if self.position == "SB":
            strength -= 0.1  # Adjust for position
        avg_raises = self.opponent_stats.get("total_raises", 0) / max(self.opponent_stats.get("rounds", 1), 1)
        avg_folds = self.opponent_stats.get("total_folds", 0) / max(self.opponent_stats.get("rounds", 1), 1)
        avg_calls = self.opponent_stats.get("total_calls", 0) / max(self.opponent_stats.get("rounds", 1), 1)
        opponent_adjust = self.opponent_raise_count > 0

        # Simple thresholds: lower strength number is better
        # Assuming 7-card evaluation, rough thresholds
        if strength > 0.6:  # Very strong hand
            if round_state.current_bet == 0:
                base_raise = round_state.big_blind * 3
                if opponent_adjust:
                    base_raise = min(base_raise * 2, round_state.max_raise)
                return PokerAction.RAISE, min(remaining_chips, base_raise)
            else:
                return PokerAction.RAISE, min(remaining_chips, round_state.max_raise)
        elif strength > 0.2:  # Medium hand
            if round_state.current_bet == 0:
                return PokerAction.CHECK, 0
            else:
                if round_state.current_bet / (round_state.pot + round_state.current_bet) < (0.3 if opponent_adjust else 0.4):
                    if random.random() < 0.2:
                        return PokerAction.RAISE, min(remaining_chips, round_state.max_raise)
                    else:
                        return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
        else:  # Weak hand
            bluff_prob = 0.3 if self.opponent_raise_count == 0 else 0.15
            if self.opponent_fold_count > 0:
                bluff_prob += 0.1
            if avg_raises < 1.5:
                bluff_prob += 0.05
            if avg_folds > 0.5:
                bluff_prob += 0.05
                bluff_prob += 0.05
            if round_state.current_bet == 0:
                return PokerAction.CHECK, 0
            else:
                if random.random() < bluff_prob:
                    return PokerAction.RAISE, min(remaining_chips, round_state.max_raise)
                else:
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")
        self.opponent_stats["total_raises"] = self.opponent_stats.get("total_raises", 0) + self.opponent_raises_this_round
        self.opponent_stats["total_folds"] = self.opponent_stats.get("total_folds", 0) + self.opponent_folds_this_round
        self.opponent_stats["total_calls"] = self.opponent_stats.get("total_calls", 0) + self.opponent_calls_this_round
        self.opponent_stats["rounds"] = self.opponent_stats.get("rounds", 0) + 1

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)
        with open("opponent_stats.json", "w") as f:
            json.dump(self.opponent_stats, f)