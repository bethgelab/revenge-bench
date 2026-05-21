from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
from collections import Counter
import random

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = []
        self.card_rank = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        self.blind_amount = 0
        self.big_blind_player_id = -1
        self.small_blind_player_id = -1
        self.all_players = []
        self.cached_hand_strength = -1
        self.was_pre_flop_aggressor = False
        self.cached_community_cards = []

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.big_blind_player_id = big_blind_player_id
        self.small_blind_player_id = small_blind_player_id
        self.all_players = all_players
        self.hand = player_hands
        self.blind_amount = blind_amount
        self.was_pre_flop_aggressor = False

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def _get_pre_flop_strength(self):
        if not self.hand:
            return 0
        ranks = sorted([self.card_rank[card[1]] for card in self.hand], reverse=True)
        suits = [card[0] for card in self.hand]
        is_suited = suits[0] == suits[1]
        is_pair = ranks[0] == ranks[1]
        is_connector = abs(ranks[0] - ranks[1]) == 1
        is_suited_connector = is_suited and is_connector
        if is_pair and ranks[0] >= self.card_rank['J']: return 10
        if ranks[0] == self.card_rank['A'] and ranks[1] == self.card_rank['K']: return 10
        if is_pair and ranks[0] >= self.card_rank['8']: return 9
        if is_suited_connector and ranks[0] >= self.card_rank['T']: return 9
        if ranks[0] >= self.card_rank['Q'] and ranks[1] >= self.card_rank['J']: return 8
        if is_pair: return 7
        if is_suited: return 6
        if is_connector: return 5
        if ranks[0] >= self.card_rank['T']: return 4
        return 0

    def _count_limpers(self, round_state: RoundStateClient) -> int:
        limpers = 0
        for player_id, bet in round_state.player_bets.items():
            if bet == self.blind_amount and player_id != str(self.small_blind_player_id) and player_id != str(self.big_blind_player_id):
                limpers += 1
        return limpers

    def _get_post_flop_strength(self, community_cards: List[str]):
        all_cards = self.hand + community_cards
        ranks = [self.card_rank[card[1]] for card in all_cards]
        suits = [card[0] for card in all_cards]
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        is_flush = max(suit_counts.values()) >= 5 if suit_counts else False
        unique_ranks = sorted(list(set(ranks)))
        is_straight = False
        if len(unique_ranks) >= 5:
            for i in range(len(unique_ranks) - 4):
                if unique_ranks[i+4] - unique_ranks[i] == 4:
                    is_straight = True
                    break
            if not is_straight and set([14, 2, 3, 4, 5]).issubset(set(unique_ranks)):
                is_straight = True
        counts = sorted(rank_counts.values(), reverse=True)
        if is_straight and is_flush: return 9
        if counts and counts[0] == 4: return 8
        if counts and len(counts) > 1 and counts[0] == 3 and counts[1] >= 2: return 7
        if is_flush: return 6
        if is_straight: return 5
        if counts and counts[0] == 3: return 4
        if counts and len(counts) > 1 and counts[0] == 2 and counts[1] == 2: return 3.5
        if counts and counts[0] == 2: return 2
        
        has_flush_draw = 4 in suit_counts.values()
        has_oesd = False
        has_gutshot = False
        player_and_community_ranks = set(unique_ranks)
        for i in range(1, 11):
            straight_window = set(range(i, i + 5))
            matches = len(player_and_community_ranks.intersection(straight_window))
            if matches == 4:
                if not (i in player_and_community_ranks and (i + 4) in player_and_community_ranks):
                    has_oesd = True
                    break
                else:
                    has_gutshot = True
        wheel_ranks = {14, 2, 3, 4, 5}
        if not has_oesd and len(player_and_community_ranks.intersection(wheel_ranks)) == 4:
            if not (14 in player_and_community_ranks and 5 in player_and_community_ranks):
                has_oesd = True
            else:
                has_gutshot = True
        if has_flush_draw and (has_oesd or has_gutshot): return 1.7
        if has_flush_draw: return 1.6
        if has_oesd: return 1.5
        if has_gutshot: return 1.4
        
        return 1 # High card

    def get_action(self, round_state: RoundStateClient) -> Tuple[PokerAction, int]:
        if round_state.round == "Preflop":
            hand_strength = self._get_pre_flop_strength()
            position = self._get_position()
            limpers = self._count_limpers(round_state)

            if position == "small_blind":
                if hand_strength >= 9: return PokerAction.RAISE, self.blind_amount * 4
                if hand_strength >= 7: return PokerAction.RAISE, self.blind_amount * 3
                if hand_strength >= 5: return PokerAction.CALL, 0
                return PokerAction.FOLD, 0
            
            if position == "big_blind":
                if round_state.current_bet == self.blind_amount:
                    if hand_strength >= 8: return PokerAction.RAISE, self.blind_amount * 4
                    return PokerAction.CHECK, 0
                else:
                    if hand_strength >= 9: return PokerAction.RAISE, round_state.current_bet * 3
                    if hand_strength >= 7: return PokerAction.CALL, 0
                    return PokerAction.FOLD, 0

            if position == "early":
                if hand_strength >= 9: self.was_pre_flop_aggressor = True; return PokerAction.RAISE, self.blind_amount * 4
                if hand_strength >= 8: self.was_pre_flop_aggressor = True; return PokerAction.RAISE, self.blind_amount * 3
                if hand_strength == 7: return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            if position == "middle":
                if hand_strength >= 8: self.was_pre_flop_aggressor = True; return PokerAction.RAISE, self.blind_amount * 3
                if hand_strength >= 6: return PokerAction.CALL, 0
                return PokerAction.FOLD, 0

            if position == "late":
                if limpers > 0 and hand_strength >= 8: self.was_pre_flop_aggressor = True; return PokerAction.RAISE, self.blind_amount * (4 + limpers)
                if hand_strength >= 7: self.was_pre_flop_aggressor = True; return PokerAction.RAISE, self.blind_amount * 3
                if hand_strength >= 4: return PokerAction.CALL, 0
                return PokerAction.FOLD, 0
            
            return PokerAction.FOLD, 0
        else: # Post-flop
            if self.cached_community_cards == round_state.community_cards:
                hand_strength = self.cached_hand_strength
            else:
                hand_strength = self._get_post_flop_strength(round_state.community_cards)
                self.cached_hand_strength = hand_strength
                self.cached_community_cards = round_state.community_cards

            if len(round_state.community_cards) == 3 and self.was_pre_flop_aggressor and round_state.current_bet == 0:
                board_texture = self._get_board_texture(round_state.community_cards)
                if board_texture == "WET": return PokerAction.RAISE, int(round_state.pot * 0.75)
                else: return PokerAction.RAISE, int(round_state.pot * 0.5)

            if hand_strength >= 7: return PokerAction.RAISE, round_state.pot
            elif hand_strength == 6: return PokerAction.RAISE, int(round_state.pot * 0.75)
            elif hand_strength == 5: return PokerAction.RAISE, int(round_state.pot * 0.66)
            elif hand_strength == 4: return PokerAction.RAISE, int(round_state.pot * 0.5)
            elif hand_strength == 3.5:
                if round_state.current_bet == 0: return PokerAction.RAISE, int(round_state.pot * 0.5)
                elif round_state.current_bet <= round_state.pot: return PokerAction.CALL, 0
                else: return PokerAction.FOLD, 0
            elif hand_strength == 2:
                if round_state.current_bet == 0: return PokerAction.CHECK, 0
                elif round_state.current_bet <= self.blind_amount * 2: return PokerAction.CALL, 0
                else: return PokerAction.FOLD, 0
            
            elif hand_strength >= 1.4: # Draws
                if hand_strength >= 1.7: # Combo Draw
                    if round_state.current_bet == 0: return PokerAction.RAISE, round_state.pot
                    elif round_state.current_bet <= round_state.pot * 1.5: return PokerAction.RAISE, round_state.current_bet * 2
                    else: return PokerAction.CALL, 0
                elif hand_strength >= 1.6: # Flush Draw
                    if round_state.current_bet == 0: return PokerAction.RAISE, int(round_state.pot * 0.66)
                    elif round_state.current_bet <= round_state.pot: return PokerAction.CALL, 0
                    else: return PokerAction.FOLD, 0
                elif hand_strength >= 1.5: # OESD
                    if round_state.current_bet == 0: return PokerAction.RAISE, int(round_state.pot * 0.5)
                    elif round_state.current_bet <= round_state.pot * 0.75: return PokerAction.CALL, 0
                    else: return PokerAction.FOLD, 0
                elif hand_strength >= 1.4: # Gutshot
                    if round_state.current_bet == 0: return PokerAction.CHECK, 0
                    elif round_state.current_bet <= round_state.pot * 0.25: return PokerAction.CALL, 0
                    else: return PokerAction.FOLD, 0
            
            else: # High card / Bluff
                num_active_players = sum(1 for p in round_state.players if p.is_active)
                if round_state.current_bet == 0 and num_active_players <= 2 and round_state.pot < self.blind_amount * 5:
                    return PokerAction.RAISE, int(round_state.pot * 0.5)
                elif round_state.current_bet > 0:
                    return PokerAction.FOLD, 0
                else:
                    return PokerAction.CHECK, 0
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass

    def _get_position(self):
        if self.id == self.big_blind_player_id: return "big_blind"
        if self.id == self.small_blind_player_id: return "small_blind"
        num_players = len(self.all_players)
        my_index = self.all_players.index(self.id)
        bb_index = self.all_players.index(self.big_blind_player_id)
        relative_position = (my_index - bb_index + num_players) % num_players
        if num_players <= 3:
            return "late" if relative_position == num_players - 1 else "early"
        elif num_players <= 6:
            if relative_position >= num_players - 2: return "late"
            elif relative_position <= 1: return "early"
            else: return "middle"
        else:
            if relative_position >= num_players - 3: return "late"
            elif relative_position <= 2: return "early"
            else: return "middle"

    def _get_board_texture(self, community_cards: List[str]):
        if len(community_cards) < 3: return "DRY"
        ranks = sorted([self.card_rank[card[1]] for card in community_cards])
        suits = [card[0] for card in community_cards]
        suit_counts = Counter(suits)
        if max(suit_counts.values()) >= 3: return "WET"
        unique_ranks = sorted(list(set(ranks)))
        if len(unique_ranks) >= 3:
            for i in range(len(unique_ranks) - 2):
                if unique_ranks[i+2] - unique_ranks[i] <= 4: return "WET"
        if len(unique_ranks) < len(community_cards): return "WET"
        high_cards = [r for r in ranks if r >= self.card_rank['T']]
        if len(high_cards) >= 2: return "WET"
        return "DRY"