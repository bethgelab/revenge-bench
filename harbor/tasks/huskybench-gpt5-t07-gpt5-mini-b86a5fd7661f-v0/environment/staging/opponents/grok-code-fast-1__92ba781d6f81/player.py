from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
from collections import Counter
import random

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_hand = []
        self.opponent_aggression = {}
        self.opponent_vpip = {}
        self.opponent_folds = {}

    def get_rank(self, card):
        rank = card[0]
        if rank == 'T': return 10
        if rank == 'J': return 11
        if rank == 'Q': return 12
        if rank == 'K': return 13
        if rank == 'A': return 14
        return int(rank)

    def evaluate_preflop(self, hand):
        c1, c2 = hand
        r1 = self.get_rank(c1)
        r2 = self.get_rank(c2)
        s1 = c1[1]
        s2 = c2[1]
        if r1 < r2:
            r1, r2 = r2, r1
        score = r1 * 10 + r2
        if r1 == r2:
            score += 100  # pair
        if s1 == s2:
            score += 20  # suited
        return score

    def is_flush(self, cards):
        suits = [c[1] for c in cards]
        return len(set(suits)) == 1

    def is_straight(self, ranks):
        ranks = sorted(set(ranks))
        if len(ranks) < 5:
            return False
        for i in range(len(ranks) - 4):
            if ranks[i+4] - ranks[i] == 4:
                return True
        if set([14,2,3,4,5]).issubset(set(ranks)):
            return True
        return False

    def evaluate_postflop(self, hand, community):
        cards = hand + community
        ranks = [self.get_rank(c) for c in cards]
        suits = [c[1] for c in cards]
        rank_counts = Counter(ranks)
        flush = self.is_flush(cards)
        straight = self.is_straight(ranks)
        if straight and flush:
            score = 800  # straight flush
        elif 4 in rank_counts.values():
            score = 700  # four of a kind
        elif 3 in rank_counts.values() and 2 in rank_counts.values():
            score = 600  # full house
        elif flush:
            score = 550  # flush
        elif straight:
            score = 450  # straight
        elif 3 in rank_counts.values():
            score = 500  # three of a kind
        elif list(rank_counts.values()).count(2) >= 2:
            score = 400  # two pair
        elif 2 in rank_counts.values():
            score = 300  # pair
        else:
            score = max(ranks) * 10  # high card
        return score

    def has_draw(self, hand, community):
        cards = hand + community
        ranks = [self.get_rank(c) for c in cards]
        suits = [c[1] for c in cards]
        suit_counts = Counter(suits)
        flush_draw = any(count == 4 for count in suit_counts.values())
        rank_set = set(ranks)
        straight_draw = False
        for r in range(2,15):
            if r in rank_set and r+1 in rank_set and r+2 in rank_set and r+3 in rank_set:
                if r-1 not in rank_set and r+4 not in rank_set:
                    straight_draw = True
                    break
        if set([14,2,3,4]).issubset(rank_set) and 5 not in rank_set:
            straight_draw = True
        return flush_draw or straight_draw

    def calculate_ev(self, strength, pot, bet, fold_prob=0.5, max_strength=800, position='middle', aggressive_opponent=False):
        win_prob = min(strength / max_strength, 1.0)
        if position == 'early': win_prob *= 0.9
        if aggressive_opponent: win_prob *= 0.95
        ev = fold_prob * pot + (1 - fold_prob) * (win_prob * (pot + bet) - bet)
        return ev

    def get_position(self, round_state):
        if self.player_id == round_state.small_blind_player_id:
            return 'early'
        elif self.player_id == round_state.big_blind_player_id:
            return 'late'
        else:
            return 'middle'

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.my_hand = player_hands
        self.player_id = all_players[0]

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.opponent_aggression = {}
        self.opponent_vpip = {}
        self.opponent_folds = {}

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        # Update opponent modeling
        for action in round_state.player_actions:
            if action.player_id != self.player_id:
                if action.action in [PokerAction.RAISE, PokerAction.BET]:
                    self.opponent_aggression[action.player_id] = self.opponent_aggression.get(action.player_id, 0) + 1
                    if round_state.round == 'preflop':
                        self.opponent_vpip[action.player_id] = self.opponent_vpip.get(action.player_id, 0) + 1
                elif action.action == PokerAction.FOLD:
                    self.opponent_folds[action.player_id] = self.opponent_folds.get(action.player_id, 0) + 1
        
        aggressive_opponent = max(self.opponent_aggression.values(), default=0) > 2
        total_opponent_actions = len([a for a in round_state.player_actions if a.player_id != self.player_id])
        total_folds = sum(self.opponent_folds.values())
        fold_prob = total_folds / total_opponent_actions if total_opponent_actions > 0 else 0.5
        loose_opponent = any(v > 0 for v in self.opponent_vpip.values())
        
        position = self.get_position(round_state)
        bluff_chance = 0.2 if position == 'late' else 0.1
        
        if position == 'early':
            strong_thresh = 130 if not (aggressive_opponent or loose_opponent) else 140
            medium_thresh = 110 if not (aggressive_opponent or loose_opponent) else 120
            strong_thresh_post = 550 if not (aggressive_opponent or loose_opponent) else 600
        else:
            strong_thresh = 120 if not (aggressive_opponent or loose_opponent) else 130
            medium_thresh = 100  # assuming default
            strong_thresh_post = 500 if not (aggressive_opponent or loose_opponent) else 550
        
        # Adjust for stack sizes
        opponent_chips = [chips for pid, chips in round_state.player_chips.items() if pid != self.player_id]
        low_stack_opponent = min(opponent_chips) < 200 if opponent_chips else False
        if low_stack_opponent and remaining_chips > 300:
            strong_thresh -= 10
            strong_thresh_post -= 50
        
        amount = round_state.min_raise if remaining_chips >= 1000 else remaining_chips
        
        if round_state.round == 'preflop':
            strength = self.evaluate_preflop(self.my_hand)
            if round_state.current_bet == 0:
                if strength >= strong_thresh:
                    if random.random() < 0.2:
                        return PokerAction.CHECK, 0
                    else:
                        return PokerAction.RAISE, amount
                elif strength >= medium_thresh:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.CHECK, 0
            else:
                if strength >= strong_thresh:
                    if random.random() < 0.2:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.RAISE, amount
                elif strength >= medium_thresh:
                    return PokerAction.CALL, 0
                else:
                    ev = self.calculate_ev(strength, round_state.pot, round_state.current_bet, fold_prob, 300, position, aggressive_opponent or loose_opponent)
                    if ev > 0:
                        return PokerAction.CALL, 0
                    else:
                        bluff = random.random() < 0.05
                        if bluff:
                            return PokerAction.RAISE, amount
                        else:
                            return PokerAction.FOLD, 0
        else:
            strength = self.evaluate_postflop(self.my_hand, round_state.community_cards)
            if strength >= strong_thresh_post:
                if round_state.current_bet == 0:
                    if random.random() < 0.2:
                        return PokerAction.CHECK, 0
                    else:
                        return PokerAction.RAISE, amount
                else:
                    if random.random() < 0.2:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.RAISE, amount
            elif strength >= 300:
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.CALL, 0
            else:
                has_draw = self.has_draw(self.my_hand, round_state.community_cards)
                bluff_chance = 0.3 if has_draw else bluff_chance
                if round_state.current_bet > 0:
                    pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                    fold_equity = fold_prob * round_state.pot / (round_state.pot + round_state.current_bet)
                    bluff = fold_equity > pot_odds or random.random() < bluff_chance
                    if bluff:
                        return PokerAction.RAISE, amount
                    else:
                        ev = self.calculate_ev(strength, round_state.pot, round_state.current_bet, fold_prob, position=position, aggressive_opponent=aggressive_opponent or loose_opponent)
                        if ev > 0:
                            return PokerAction.CALL, 0
                        else:
                            return PokerAction.FOLD, 0
                else:
                    bluff = random.random() < bluff_chance
                    if bluff:
                        return PokerAction.RAISE, amount
                    else:
                        return PokerAction.CHECK, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass