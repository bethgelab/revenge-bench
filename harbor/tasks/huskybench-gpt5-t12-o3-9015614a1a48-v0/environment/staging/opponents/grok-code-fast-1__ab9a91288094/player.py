from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
from random import random

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards = []
        self.is_big_blind = False

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.hole_cards = player_hands
        self.is_big_blind = (big_blind_player_id == self.id)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass

    def evaluate_hand(self, community: List[str]) -> int:
        """Simple hand strength evaluator. Higher score is better."""
        if len(community) == 0:
            # Use Chen formula for preflop
            ranks = [c[0] for c in self.hole_cards]
            rank_nums = sorted([rank_values[r] for r in ranks], reverse=True)
            high = rank_nums[0]
            low = rank_nums[1]
            suited = self.hole_cards[0][1] == self.hole_cards[1][1]
            pair = high == low
            gap = high - low - 1
            chen_score = high
            if pair:
                chen_score += 2
            if suited:
                chen_score += 2
            if gap == 1:
                chen_score -= 1
            elif gap == 2:
                chen_score -= 2
            elif gap == 3:
                chen_score -= 4
            elif gap >= 4:
                chen_score -= 5
            # Scale Chen score to fit our scale (Chen max ~20, our scale up to 100)
            return int(chen_score * 5)  # roughly 0-100
        cards = self.hole_cards + community
        if len(cards) < 2:
            return 0
        ranks = [c[0] for c in cards]
        suits = [c[1] for c in cards]
        rank_values = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, 'T':10, 'J':11, 'Q':12, 'K':13, 'A':14}
        rank_nums = [rank_values.get(r, 0) for r in ranks]
        rank_count = {}
        for r in ranks:
            rank_count[r] = rank_count.get(r, 0) + 1
        pairs = sum(1 for v in rank_count.values() if v == 2)
        three = sum(1 for v in rank_count.values() if v == 3)
        four = sum(1 for v in rank_count.values() if v == 4)
        flush = len(set(suits)) == 1 and len(cards) >= 5
        straight = False
        if len(cards) >= 5:
            sorted_unique = sorted(set(rank_nums))
            for i in range(len(sorted_unique) - 4):
                if sorted_unique[i + 4] - sorted_unique[i] == 4:
                    straight = True
                    break
        if four:
            score = 100
        elif three and pairs:
            score = 90
        elif flush:
            score = 80
        elif straight:
            score = 70
        elif three:
            score = 60
        elif pairs == 2:
            score = 50
        elif pairs == 1:
            score = 30 + max(rank_nums)  # bonus for high pair
        else:
            score = max(rank_nums)  # high card
        return score

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """Returns the action for the player based on hand strength."""
        community = round_state.community_cards
        hand_strength = self.evaluate_hand(community)
        round_type = round_state.round.lower()
        effective_strength = hand_strength + (10 if self.is_big_blind else 0)
        current_bet = round_state.current_bet
        pot = round_state.pot
        min_raise = round_state.min_raise
        call_amount = current_bet - round_state.player_bets.get(str(self.id), 0)
        pot_odds = call_amount / (pot + call_amount) if pot + call_amount > 0 else 0
        opponent_chips = [int(chips) for pid, chips in round_state.player_chips.items() if pid != str(self.id)]
        min_opponent_stack = min(opponent_chips) if opponent_chips else remaining_chips
        
        if call_amount > remaining_chips:
            return PokerAction.ALL_IN, remaining_chips
        
        if round_type == 'preflop':
            if effective_strength > 60:  # Strong hand
                if current_bet == 0:
                    return PokerAction.RAISE, min(remaining_chips, max(min_raise, min(pot // 4, min_opponent_stack // 5)))
                else:
                    return PokerAction.RAISE, min(remaining_chips, max(min_raise, min(pot // 2, min_opponent_stack // 4)))
            elif effective_strength > 30:  # Medium hand
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.CALL, 0
            else:  # Weak hand
                if current_bet == 0:
                    if random() < 0.05:
                        return PokerAction.RAISE, min(remaining_chips, max(min_raise, min(pot // 4, min_opponent_stack // 5)))
                    else:
                        return PokerAction.CHECK, 0
                else:
                    if random() < 0.1:
                        return PokerAction.RAISE, min(remaining_chips, max(min_raise, min(pot // 4, min_opponent_stack // 5)))
                    else:
                        return PokerAction.FOLD, 0
        else:  # Postflop
            if effective_strength > 70:
                return PokerAction.RAISE, min(remaining_chips, max(min_raise, min(pot // 3, min_opponent_stack // 4)))
            elif effective_strength > 40:
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                else:
                    if pot_odds < effective_strength / 100:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
            else:
                if current_bet == 0:
                    if random() < 0.05:
                        return PokerAction.RAISE, min(remaining_chips, max(min_raise, min(pot // 4, min_opponent_stack // 5)))
                    else:
                        return PokerAction.CHECK, 0
                else:
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the end of the round."""
        pass