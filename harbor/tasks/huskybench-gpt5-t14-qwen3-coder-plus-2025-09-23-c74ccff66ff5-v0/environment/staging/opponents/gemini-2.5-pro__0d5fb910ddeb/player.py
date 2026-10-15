import random
from typing import List, Tuple, Dict
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = []
        self.all_players = []
        self.initial_small_blind_player_id = -1
        self.opponent_aggression = {} # {player_id: [raises, total_actions]}

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.hand = player_hands
        self.all_players = all_players
        self.initial_small_blind_player_id = small_blind_player_id
        for player_id in all_players:
            if player_id != self.id:
                self.opponent_aggression[player_id] = [0, 0]

    def has_straight(self, community_cards: List[str]) -> bool:
        all_cards = self.hand + community_cards
        all_ranks = [card[0] for card in all_cards]
        rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        numerical_ranks = sorted(list(set([rank_map[rank] for rank in all_ranks])))

        if len(numerical_ranks) < 5:
            return False

        # Ace-low straight
        if all(rank in numerical_ranks for rank in [14, 2, 3, 4, 5]):
            return True

        for i in range(len(numerical_ranks) - 4):
            if numerical_ranks[i+4] - numerical_ranks[i] == 4:
                return True
        
        return False

    def has_flush(self, community_cards: List[str]) -> bool:
        all_cards = self.hand + community_cards
        suits = [card[1] for card in all_cards]
        for suit in "shdc":
            if suits.count(suit) >= 5:
                return True
        return False

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def get_position(self, round_num: int) -> str:
        num_players = len(self.all_players)
        if num_players < 2 or self.initial_small_blind_player_id == -1:
            return "unknown"

        try:
            initial_sb_index = self.all_players.index(self.initial_small_blind_player_id)
            my_index = self.all_players.index(self.id)
        except ValueError:
            return "unknown"

        current_sb_index = (initial_sb_index + round_num - 1) % num_players
        current_bb_index = (current_sb_index + 1) % num_players
        current_button_index = (current_sb_index - 1 + num_players) % num_players

        if my_index == current_button_index:
            return "late"
        if num_players > 3 and my_index == (current_button_index - 1 + num_players) % num_players:
            return "late"

        if my_index == current_sb_index or my_index == current_bb_index:
            return "blinds"

        utg_index = (current_bb_index + 1) % num_players
        if num_players > 3 and my_index == utg_index:
            return "early"
        if num_players > 5 and my_index == (utg_index + 1) % num_players:
            return "early"

        return "middle"

    def get_rank_counts(self, community_cards: List[str]) -> dict:
        all_cards = self.hand + community_cards
        ranks = [card[0] for card in all_cards]
        return {rank: ranks.count(rank) for rank in set(ranks)}

    def get_hand_strength(self, community_cards: List[str]) -> int:
        rank_counts = self.get_rank_counts(community_cards)
        is_flush = self.has_flush(community_cards)
        is_straight = self.has_straight(community_cards)

        if is_straight and is_flush: return 8
        if 4 in rank_counts.values(): return 7
        if 3 in rank_counts.values() and 2 in rank_counts.values(): return 6
        if is_flush: return 5
        if is_straight: return 4
        if 3 in rank_counts.values(): return 3
        
        pairs = list(rank_counts.values()).count(2)
        if pairs == 2: return 2
        if pairs == 1: return 1
        
        return 0

    def get_opponent_aggression_score(self, opponent_id: int) -> float:
        if opponent_id in self.opponent_aggression:
            raises, total_actions = self.opponent_aggression[opponent_id]
            if total_actions > 0:
                return raises / total_actions
        return 0.2 # Default aggression

    def _get_avg_opponent_aggression(self, round_state: RoundStateClient) -> float:
        total_aggression = 0
        num_opponents = 0
        for player_id in round_state.player_bets:
            if int(player_id) != self.id:
                total_aggression += self.get_opponent_aggression_score(int(player_id))
                num_opponents += 1
        return total_aggression / num_opponents if num_opponents > 0 else 0.2

    def _get_bluff_chance(self, position: str, avg_opponent_aggression: float) -> float:
        bluff_chance = 0.20
        if position == "late":
            bluff_chance = 0.30
        elif position == "early":
            bluff_chance = 0.10
        
        if avg_opponent_aggression > 0.4: # Very aggressive opponent
            bluff_chance *= 0.5 # Bluff less
        elif avg_opponent_aggression < 0.15: # Very passive opponent
            bluff_chance *= 1.5 # Bluff more
        return bluff_chance

    def _get_raise_amount(self, hand_strength: int, pot_size: int, strength_threshold: int) -> int:
        raise_multiplier = 1.0 + random.uniform(-0.1, 0.1) # +/- 10%
        raise_amount = 0
        if hand_strength >= strength_threshold:
            if hand_strength == 8: raise_amount = int(pot_size * 3.0 * raise_multiplier)
            elif hand_strength == 7: raise_amount = int(pot_size * 2.0 * raise_multiplier)
            elif hand_strength == 6: raise_amount = int(pot_size * 1.5 * raise_multiplier)
            elif hand_strength == 5: raise_amount = int(pot_size * 1.2 * raise_multiplier)
            elif hand_strength == 4: raise_amount = int(pot_size * 1.0 * raise_multiplier)
            elif hand_strength == 3: raise_amount = int(pot_size * 0.8 * raise_multiplier)
            elif hand_strength == 2: raise_amount = int(pot_size * 0.7 * raise_multiplier)
            elif hand_strength == 1: raise_amount = int(pot_size * 0.5 * raise_multiplier)
        return raise_amount

    def _should_fold(self, hand_strength: int, to_call: int, pot_size: int, strength_threshold: int, position: str, avg_opponent_aggression: float) -> bool:
        if to_call == 0:
            return False
            
        fold_threshold = 0.3
        if position == "early":
            fold_threshold = 0.2
        
        if avg_opponent_aggression > 0.4:
            fold_threshold *= 0.8 # Fold more easily against aggressive players
        
        return hand_strength < strength_threshold and to_call > pot_size * fold_threshold

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        hand_strength = self.get_hand_strength(round_state.community_cards)
        my_bet = round_state.player_bets.get(str(self.id), 0)
        to_call = round_state.current_bet - my_bet
        min_raise = round_state.min_raise
        pot_size = round_state.pot
        position = self.get_position(round_state.round_num)
        avg_opponent_aggression = self._get_avg_opponent_aggression(round_state)

        strength_threshold = 1
        if position == "early":
            strength_threshold = 2

        # Fold logic
        if self._should_fold(hand_strength, to_call, pot_size, strength_threshold, position, avg_opponent_aggression):
            return PokerAction.FOLD, 0

        # Raise / Bet logic
        raise_amount = self._get_raise_amount(hand_strength, pot_size, strength_threshold)
        if raise_amount > 0:
            final_bet = min(remaining_chips, max(min_raise, raise_amount))
            if final_bet > to_call:
                return PokerAction.RAISE, final_bet

        # Bluffing logic
        bluff_chance = self._get_bluff_chance(position, avg_opponent_aggression)
        if hand_strength < strength_threshold and random.random() < bluff_chance:
            bluff_raise = int(pot_size * random.uniform(0.5, 0.75))
            if bluff_raise >= min_raise and bluff_raise <= remaining_chips:
                return PokerAction.RAISE, bluff_raise

        # Call / Check logic
        if to_call > 0:
            return PokerAction.CALL, min(to_call, remaining_chips)
        else:
            return PokerAction.CHECK, 0
            
    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        for player_id_str, action in round_state.player_actions.items():
            player_id = int(player_id_str)
            if player_id != self.id and player_id in self.opponent_aggression:
                self.opponent_aggression[player_id][1] += 1 # Total actions
                if action == "RAISE":
                    self.opponent_aggression[player_id][0] += 1 # Raises

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass