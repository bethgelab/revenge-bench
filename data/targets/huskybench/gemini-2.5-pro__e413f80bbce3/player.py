import logging
from typing import List, Tuple
from collections import Counter
import random

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.opponent_stats = {}
        self.processed_history_len = 0
        self.hand = []
        self.blind_amount = 0

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.hand = player_hands
        self.blind_amount = blind_amount
        for player_id in all_players:
            if player_id != self.id:
                self.opponent_stats[player_id] = {
                    "general": {"total_actions": 0, "hands_played": 0},
                    "preflop": {"raises": 0, "calls": 0, "folds": 0, "checks": 0, "actions": 0, "raise_amount": 0, "call_amount": 0},
                    "flop":    {"raises": 0, "calls": 0, "folds": 0, "checks": 0, "actions": 0, "raise_amount": 0, "call_amount": 0},
                    "turn":    {"raises": 0, "calls": 0, "folds": 0, "checks": 0, "actions": 0, "raise_amount": 0, "call_amount": 0},
                    "river":   {"raises": 0, "calls": 0, "folds": 0, "checks": 0, "actions": 0, "raise_amount": 0, "call_amount": 0}
                }

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.processed_history_len = 0
        pass

    def _get_hand_strength(self, community_cards: List[str]) -> int:
        all_cards = self.hand + community_cards
        ranks = [card[0] for card in all_cards]
        suits = [card[1] for card in all_cards]
        rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        numeric_ranks = sorted([rank_map[r] for r in ranks], reverse=True)
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        counts = sorted(rank_counts.values(), reverse=True)
        is_flush = max(suit_counts.values()) >= 5
        is_straight = False
        unique_ranks = sorted(list(set(numeric_ranks)), reverse=True)
        if len(unique_ranks) >= 5:
            for i in range(len(unique_ranks) - 4):
                if unique_ranks[i] - unique_ranks[i+4] == 4:
                    is_straight = True
                    break
            if not is_straight and set([14, 2, 3, 4, 5]).issubset(set(unique_ranks)):
                is_straight = True
        if is_straight and is_flush: return 8
        if counts[0] == 4: return 7
        if counts[0] == 3 and len(counts) > 1 and counts[1] >= 2: return 6
        if is_flush: return 5
        if is_straight: return 4
        if counts[0] == 3: return 3
        if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 2
        if counts[0] == 2: return 1
        return 0

    def _get_preflop_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        is_aggressive_opponent = False
        for opponent_id, stats in self.opponent_stats.items():
            preflop_actions = stats["preflop"]["actions"]
            if preflop_actions > 5:
                preflop_raise_rate = stats["preflop"]["raises"] / preflop_actions
                if preflop_raise_rate > 0.3:
                    is_aggressive_opponent = True
                    break
        card1_rank = self.hand[0][0]
        card2_rank = self.hand[1][0]
        is_pair = card1_rank == card2_rank
        is_suited = self.hand[0][1] == self.hand[1][1]
        if is_aggressive_opponent:
            premium_pairs = ['A', 'K', 'Q', 'J']
            strong_cards = ['A', 'K']
            playable_suited = False
            playable_pairs = True
        else:
            premium_pairs = ['A', 'K', 'Q', 'J', 'T']
            strong_cards = ['A', 'K', 'Q']
            playable_suited = True
            playable_pairs = True
        if is_pair and card1_rank in premium_pairs:
            return PokerAction.RAISE, self._get_bet_size(round_state, remaining_chips, 3, None)
        if card1_rank in strong_cards or card2_rank in strong_cards:
            return PokerAction.RAISE, self._get_bet_size(round_state, remaining_chips, 2, None)
        can_call = (is_pair and playable_pairs) or (is_suited and playable_suited)
        if can_call:
            call_threshold = self.blind_amount * 2 if is_aggressive_opponent else remaining_chips * 0.1
            if round_state.current_bet > 0 and round_state.current_bet < call_threshold:
                return PokerAction.CALL, 0
        if round_state.current_bet == 0:
            return PokerAction.CHECK, 0
        return PokerAction.FOLD, 0

    def _was_preflop_aggressor(self, round_state: RoundStateClient) -> bool:
        preflop_history = [h for h in round_state.history if h.street == 'preflop']
        last_raiser = -1
        for action in preflop_history:
            if action.action == PokerAction.RAISE:
                last_raiser = action.player_id
        return last_raiser == self.id

    def _get_postflop_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        hand_strength = self._get_hand_strength(round_state.community_cards)
        
        if hand_strength >= 2: # Two pair or better
            if round_state.current_bet == 0:
                bet_amount = self._get_bet_size(round_state, remaining_chips, 0.5, None)
                return PokerAction.RAISE, bet_amount
            else:
                if round_state.current_bet < remaining_chips * 0.3:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
        else: # Weak hand
            if round_state.current_bet > 0:
                return PokerAction.FOLD, 0
            else:
                return PokerAction.CHECK, 0

    def _estimate_opponent_strength(self, round_state: RoundStateClient, opponent_id: int) -> float:
        strength_score = 0
        street_weights = {"preflop": 0.5, "flop": 1.0, "turn": 1.5, "river": 2.0}
        for street in ["preflop", "flop", "turn", "river"]:
            if street in self.opponent_stats[opponent_id]:
                stats = self.opponent_stats[opponent_id][street]
                if stats["actions"] > 0:
                    pot_size = round_state.pot if round_state.pot > 0 else self.blind_amount * 3
                    normalized_raises = stats.get("raise_amount", 0) / pot_size
                    normalized_calls = stats.get("call_amount", 0) / pot_size
                    street_score = (normalized_raises * 2) + (normalized_calls * 1)
                    strength_score += street_score * street_weights[street]
        if strength_score == 0:
            return 0.5
        normalized_score = strength_score / 10.0
        return max(0, min(1, normalized_score))

    def _get_bet_size(self, round_state: RoundStateClient, remaining_chips: int, pot_fraction: float, opponent_id: int) -> int:
        bet = int(round_state.pot * pot_fraction)
        min_bet = round_state.min_raise if round_state.min_raise > 0 else self.blind_amount
        return min(remaining_chips, max(min_bet, bet))

    def _should_bluff(self, round_state: RoundStateClient) -> bool:
        return False

    def _update_opponent_stats(self, round_state: RoundStateClient):
        new_actions = round_state.history[self.processed_history_len:]
        for action_record in new_actions:
            player_id = action_record.player_id
            if player_id in self.opponent_stats:
                action = action_record.action
                street = round_state.round
                if street not in self.opponent_stats[player_id]:
                    street = "preflop"
                self.opponent_stats[player_id]["general"]["total_actions"] += 1
                self.opponent_stats[player_id][street]["actions"] += 1
                if action == PokerAction.RAISE:
                    self.opponent_stats[player_id][street]["raises"] += 1
                    if action_record.amount is not None:
                        self.opponent_stats[player_id][street]["raise_amount"] += action_record.amount
                elif action == PokerAction.FOLD:
                    self.opponent_stats[player_id][street]["folds"] += 1
                elif action == PokerAction.CALL:
                    self.opponent_stats[player_id][street]["calls"] += 1
                    if action_record.amount is not None:
                        self.opponent_stats[player_id][street]["call_amount"] += action_record.amount
                elif action == PokerAction.CHECK:
                    self.opponent_stats[player_id][street]["checks"] += 1
        self.processed_history_len = len(round_state.history)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        # self._update_opponent_stats(round_state)
        if round_state.round.lower() == 'preflop':
            return self._get_preflop_action(round_state, remaining_chips)
        else:
            return self._get_postflop_action(round_state, remaining_chips)

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass