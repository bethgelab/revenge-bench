from typing import List, Tuple
import json
import os
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
import random
from collections import Counter

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.opponent_model = {}
        self.opponent_model_file = "opponent_model.json"
        # Bot state
        self.big_blind = 0
        self.player_id = None
        self.opponent_id = None
        self.hand = []

    def set_id(self, player_id: int):
        self.player_id = player_id

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.big_blind = blind_amount
        self.hand = player_hands
        opponent_ids = [p_id for p_id in all_players if p_id != self.player_id]
        if opponent_ids:
            self.opponent_id = opponent_ids[0]
        
        if os.path.exists(self.opponent_model_file):
            with open(self.opponent_model_file, 'r') as f:
                try:
                    self.opponent_model = json.load(f)
                except json.JSONDecodeError:
                    self.opponent_model = {}

        if str(self.opponent_id) not in self.opponent_model:
            self.opponent_model[str(self.opponent_id)] = {
                'hands_played': 0,
                'vpip_opportunities': 0,
                'vpip_actions': 0,
                'pfr_opportunities': 0,
                'pfr_actions': 0,
                'cbet_opportunities': 0,
                'cbet_actions': 0,
                'fold_to_cbet_opportunities': 0,
                'fold_to_cbet_actions': 0
            }

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.hand_vpip_tracked = False
        self.hand_pfr_opportunity_tracked = False
        self.hand_cbet_tracked = False
        self.hand_fold_to_cbet_tracked = False

    def _get_opponent_cbet_frequency(self) -> float:
        stats = self.opponent_model.get(str(self.opponent_id))
        if not stats or stats['cbet_opportunities'] < 5:
            return 0.55
        return (stats['cbet_actions'] / stats['cbet_opportunities']) if stats['cbet_opportunities'] > 0 else 0

    def _get_opponent_fold_to_cbet_frequency(self) -> float:
        stats = self.opponent_model.get(str(self.opponent_id))
        if not stats or stats['fold_to_cbet_opportunities'] < 5:
            return 0.5
        return (stats['fold_to_cbet_actions'] / stats['fold_to_cbet_opportunities']) if stats['fold_to_cbet_opportunities'] > 0 else 0

    def _get_opponent_stats(self) -> dict:
        stats = self.opponent_model.get(str(self.opponent_id))
        if not stats or stats['hands_played'] < 5:
            return {'vpip': 0.25, 'pfr': 0.15} 
        vpip = (stats['vpip_actions'] / stats['vpip_opportunities']) if stats['vpip_opportunities'] > 0 else 0
        pfr = (stats['pfr_actions'] / stats['pfr_opportunities']) if stats['pfr_opportunities'] > 0 else 0
        return {'vpip': vpip, 'pfr': pfr}

    def _track_opponent_preflop_stats(self, round_state: RoundStateClient):
        if round_state.round_num != 1 or not hasattr(round_state, 'action_sequence'):
            return
        opponent_stats = self.opponent_model[str(self.opponent_id)]
        if not self.hand_pfr_opportunity_tracked:
            pre_opponent_actions = [a for a in round_state.action_sequence if a.get('round') == 1 and a.get('player') != self.opponent_id]
            is_pfr_opportunity = not any(a.get('action') == 'RAISE' for a in pre_opponent_actions)
            if is_pfr_opportunity:
                opponent_stats['pfr_opportunities'] += 1
            self.hand_pfr_opportunity_tracked = True
        if not self.hand_vpip_tracked:
            is_opponent_bb = (round_state.big_blind_player_id == self.opponent_id)
            for action in round_state.action_sequence:
                if action.get('player') == self.opponent_id and action.get('round') == 1:
                    action_type = action.get('action')
                    is_bb_check = is_opponent_bb and action_type == 'CHECK'
                    if action_type in ['CALL', 'RAISE', 'BET'] and not is_bb_check:
                        opponent_stats['vpip_actions'] += 1
                        if action_type in ['RAISE', 'BET']:
                            opponent_stats['pfr_actions'] += 1
                        self.hand_vpip_tracked = True
                        break 
                    elif action_type == 'FOLD':
                        self.hand_vpip_tracked = True
                        break

    def _track_opponent_postflop_stats(self, round_state: RoundStateClient):
        if round_state.round_num != 2 or self.hand_cbet_tracked or not hasattr(round_state, 'action_sequence'):
            return
        opponent_stats = self.opponent_model[str(self.opponent_id)]
        preflop_aggressor = None
        preflop_actions = [a for a in round_state.action_sequence if a.get('round') == 1]
        for action in reversed(preflop_actions):
            if action.get('action') in ['RAISE', 'BET']:
                preflop_aggressor = action.get('player')
                break
        if preflop_aggressor != self.opponent_id:
            self.hand_cbet_tracked = True
            return
        flop_actions = [a for a in round_state.action_sequence if a.get('round') == 2]
        action_checked_to_opponent = not any(a.get('action') != 'CHECK' for a in flop_actions if a.get('player') != self.opponent_id)
        if action_checked_to_opponent:
            opponent_stats['cbet_opportunities'] += 1
            for action in flop_actions:
                if action.get('player') == self.opponent_id and action.get('action') == 'BET':
                    opponent_stats['cbet_actions'] += 1
                    break
        self.hand_cbet_tracked = True

    def _track_opponent_fold_to_cbet(self, round_state: RoundStateClient):
        if self.hand_fold_to_cbet_tracked or not hasattr(round_state, 'action_sequence'):
            return

        preflop_aggressor = None
        preflop_actions = [a for a in round_state.action_sequence if a.get('round') == 1]
        for action in reversed(preflop_actions):
            if action.get('action') in ['RAISE', 'BET']:
                preflop_aggressor = action.get('player')
                break
        
        if preflop_aggressor != self.player_id:
            self.hand_fold_to_cbet_tracked = True
            return

        my_cbet = False
        flop_actions = [a for a in round_state.action_sequence if a.get('round') == 2]
        my_bet_index = -1
        for i, action in enumerate(flop_actions):
            if action.get('player') == self.player_id and action.get('action') == 'BET':
                my_cbet = True
                my_bet_index = i
                break
        
        if not my_cbet:
            self.hand_fold_to_cbet_tracked = True
            return

        opponent_had_chance_to_act = False
        opponent_folded = False
        if my_bet_index != -1:
            for i in range(my_bet_index + 1, len(flop_actions)):
                action = flop_actions[i]
                if action.get('player') == self.opponent_id:
                    opponent_had_chance_to_act = True
                    if action.get('action') == 'FOLD':
                        opponent_folded = True
                    break
        
        if opponent_had_chance_to_act:
            opponent_stats = self.opponent_model[str(self.opponent_id)]
            opponent_stats['fold_to_cbet_opportunities'] += 1
            if opponent_folded:
                opponent_stats['fold_to_cbet_actions'] += 1
        
        self.hand_fold_to_cbet_tracked = True

    def _get_opponent_aggression(self, round_state: RoundStateClient) -> float:
        if not hasattr(round_state, 'action_sequence'): return 0
        opponent_actions = [a for a in round_state.action_sequence if a.get('player') == self.opponent_id]
        if not opponent_actions: return 0
        aggro_actions = sum(1 for a in opponent_actions if a.get('action') in ['RAISE', 'BET'])
        return aggro_actions / len(opponent_actions)

    def _get_hand_strength(self, hand: List[str], community_cards: List[str]) -> int:
        all_cards = hand + community_cards
        if not all_cards: return 0
        ranks = [c[:-1] for c in all_cards]
        suits = [c[-1] for c in all_cards]
        rank_map = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        num_ranks = sorted([int(r) if r.isdigit() else rank_map[r] for r in ranks], reverse=True)
        rank_counts = Counter(num_ranks)
        suit_counts = Counter(suits)
        is_flush = max(suit_counts.values()) >= 5
        unique_ranks = sorted(list(set(num_ranks)), reverse=True)
        is_straight = False
        if len(unique_ranks) >= 5:
            for i in range(len(unique_ranks) - 4):
                if unique_ranks[i] - unique_ranks[i+4] == 4:
                    is_straight = True
                    break
            if not is_straight and unique_ranks[0] == 14 and 5 in unique_ranks and 4 in unique_ranks and 3 in unique_ranks and 2 in unique_ranks:
                is_straight = True
        if is_straight and is_flush: return 9
        if 4 in rank_counts.values(): return 8
        if 3 in rank_counts.values() and 2 in rank_counts.values(): return 7
        if is_flush: return 6
        if is_straight: return 5
        if 3 in rank_counts.values(): return 4
        if list(rank_counts.values()).count(2) >= 2: return 3
        if 2 in rank_counts.values(): return 2
        return 1

    def _is_flush_draw(self, hand: List[str], community_cards: List[str]) -> bool:
        suits = [c[-1] for c in hand + community_cards]
        return max(Counter(suits).values()) == 4

    def _calculate_straight_draw_outs(self, hand: List[str], community_cards: List[str]) -> int:
        all_cards = hand + community_cards
        ranks = [c[:-1] for c in all_cards]
        rank_map = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        num_ranks = sorted(list(set([int(r) if r.isdigit() else rank_map[r] for r in ranks])))
        outs = 0
        if len(num_ranks) >= 4:
            for i in range(len(num_ranks) - 3):
                if num_ranks[i+3] - num_ranks[i] == 3: outs += 8
                if num_ranks[i+3] - num_ranks[i] == 4 and (num_ranks[i+1]-num_ranks[i]==1 and num_ranks[i+3]-num_ranks[i+2]==1): outs += 4
        return outs

    def _calculate_outs(self, hand: List[str], community_cards: List[str]) -> int:
        outs = 0
        if self._is_flush_draw(hand, community_cards): outs += 9
        outs += self._calculate_straight_draw_outs(hand, community_cards)
        return outs

    def _calculate_pot_odds(self, pot_size: int, bet_to_call: int) -> float:
        if pot_size + bet_to_call == 0: return 0
        return bet_to_call / (pot_size + bet_to_call)

    def _calculate_draw_equity(self, outs: int, community_cards: List[str]) -> float:
        if len(community_cards) == 3: return (outs / 47) * 2
        if len(community_cards) == 4: return outs / 46
        return 0

    def get_action(self, round_state: RoundStateClient) -> Tuple[PokerAction, int]:
        card1, card2 = self.hand[0], self.hand[1]
        rank1, suit1, rank2, suit2 = card1[:-1], card1[-1], card2[:-1], card2[-1]
        ranks = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        try: rank1_val = int(rank1)
        except ValueError: rank1_val = ranks.get(rank1, 0)
        try: rank2_val = int(rank2)
        except ValueError: rank2_val = ranks.get(rank2, 0)

        if round_state.round_num == 1: # Pre-flop
            self._track_opponent_preflop_stats(round_state)
            pfr = self._get_opponent_stats()['pfr']
            if rank1 == rank2:
                return (PokerAction.CALL, 0) if rank1_val < 6 and pfr > 0.25 else (PokerAction.RAISE, 2 * self.big_blind)
            can_call = (suit1 == suit2) or (rank1_val >= 10 or rank2_val >= 10)
            if can_call:
                return (PokerAction.RAISE, 2 * self.big_blind) if pfr < 0.15 and (rank1_val >= 11 or rank2_val >= 11) else (PokerAction.CALL, 0)
            return (PokerAction.FOLD, 0) if round_state.current_bet > 3 * self.big_blind else (PokerAction.FOLD, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)
        
        # Post-flop
        if round_state.round_num == 3: self._track_opponent_fold_to_cbet(round_state)
        if round_state.round_num == 2: self._track_opponent_postflop_stats(round_state)
        hand_strength = self._get_hand_strength(self.hand, round_state.community_cards)
        pot_size, opponent_aggression = round_state.pot_size, self._get_opponent_aggression(round_state)
        
        if hand_strength >= 3:
            bet_multiplier = 0.75 if opponent_aggression == 0 else 0.33 if opponent_aggression > 0.5 else 0.5
            bet_amount = int(pot_size * bet_multiplier)
            return (PokerAction.RAISE, bet_amount) if round_state.current_bet > 0 else (PokerAction.BET, bet_amount)
        
        elif hand_strength == 2:
            opponent_cbet_freq = self._get_opponent_cbet_frequency()
            fold_threshold = 0.65 if opponent_cbet_freq > 0.7 else 0.3 if opponent_cbet_freq < 0.4 else 0.5
            fold_threshold -= 0.15 if opponent_aggression > 0.5 else 0.1 if opponent_aggression > 0 else 0
            if round_state.current_bet > pot_size * max(0.1, fold_threshold): return (PokerAction.FOLD, 0)
            return (PokerAction.CALL, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)

        else: # Draws or Bluffs
            is_draw = self._is_flush_draw(self.hand, round_state.community_cards) or self._calculate_straight_draw_outs(self.hand, round_state.community_cards) > 0
            if is_draw:
                equity = self._calculate_draw_equity(self._calculate_outs(self.hand, round_state.community_cards), round_state.community_cards)
                pot_odds = self._calculate_pot_odds(pot_size, round_state.current_bet)
                if round_state.current_bet > 0:
                    return (PokerAction.CALL, 0) if equity > pot_odds else (PokerAction.FOLD, 0)
                return (PokerAction.BET, int(pot_size * 0.33))

            else: # No made hand, no draw -> Bluffing opportunity
                preflop_aggressor = None
                if hasattr(round_state, 'action_sequence'):
                    preflop_actions = [a for a in round_state.action_sequence if a.get('round') == 1]
                    for action in reversed(preflop_actions):
                        if action.get('action') in ['RAISE', 'BET']:
                            preflop_aggressor = action.get('player')
                            break

                if preflop_aggressor == self.player_id and round_state.current_bet == 0 and round_state.round_num == 2:
                    fold_freq = self._get_opponent_fold_to_cbet_frequency()
                    bluff_chance = 0
                    if fold_freq > 0.6:
                        bluff_chance = 0.8
                    elif fold_freq > 0.4:
                        bluff_chance = 0.5
                    
                    if random.random() < bluff_chance:
                        return (PokerAction.BET, int(pot_size * 0.5))

                return (PokerAction.FOLD, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        opponent_stats = self.opponent_model.get(str(self.opponent_id))
        if opponent_stats:
            opponent_stats["hands_played"] += 1
            opponent_stats["vpip_opportunities"] += 1

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        with open(self.opponent_model_file, "w") as f:
            json.dump(self.opponent_model, f, indent=4)