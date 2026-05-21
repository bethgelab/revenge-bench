from typing import List, Tuple
from collections import Counter
import random

from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = None
        self.ranks = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        self.inv_ranks = {v: k for k, v in self.ranks.items()}
        self.was_preflop_aggressor = False
        self.opponent_stats = {}

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print(f"My hand for this game is: {player_hands}")
        self.hand = player_hands
        for p_id in all_players:
            if p_id != self.id:
                self.opponent_stats[p_id] = {'vpip_put_money_in_pot': 0, 'vpip_opportunities': 0, 'pfr_raise_count': 0, 'pfr_opportunities': 0}

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.was_preflop_aggressor = False
        self.preflop_vpip_opportunities_given = set()

    def _get_preflop_strength(self):
        card1, card2 = self.hand[0], self.hand[1]
        rank1_str, suit1 = card1[0], card1[1]
        rank2_str, suit2 = card2[0], card2[1]
        rank1, rank2 = self.ranks.get(rank1_str, 0), self.ranks.get(rank2_str, 0)
        is_suited = suit1 == suit2
        
        high_rank_str = self.inv_ranks[max(rank1, rank2)]
        low_rank_str = self.inv_ranks[min(rank1, rank2)]
        
        if rank1 == rank2:
            hand_str = high_rank_str + low_rank_str
        else:
            hand_str = high_rank_str + low_rank_str + ('s' if is_suited else 'o')

        tier1 = {'AA', 'KK', 'QQ', 'JJ', 'AKs'}
        tier2 = {'TT', 'AQs', 'AJs', 'KQs', 'AKo'}
        tier3 = {'99', 'JTs', 'QJs', 'KJs', 'ATs', 'AQo'}
        tier4 = {'88', 'KTs', 'QTs', 'J9s', 'T9s', '98s', 'AJo', 'KQo'}
        tier5 = {'77', '87s', '76s', '65s', 'A9s', 'A8s', 'A7s', 'A6s', 'A5s', 'A4s', 'A3s', 'A2s', 'KJo', 'QJo', 'JTo'}
        tier6 = {'66', '55', 'T8s', '97s', '86s', '75s', '54s', 'ATo', 'KTo', 'QTo'}
        tier7 = {'44', '33', '22', 'J9o', 'T9o', '98o'}
        tier8 = {'K9s', 'K8s', 'K7s', 'K6s', 'K5s', 'K4s', 'K3s', 'K2s', 'Q9s', 'Q8s', 'J8s', '64s'}

        if hand_str in tier1: return 1
        if hand_str in tier2: return 2
        if hand_str in tier3: return 3
        if hand_str in tier4: return 4
        if hand_str in tier5: return 5
        if hand_str in tier6: return 6
        if hand_str in tier7: return 7
        if hand_str in tier8: return 8
        return 9

    def _get_postflop_strength(self, community_cards: List[str]):
        all_cards = self.hand + community_cards
        if not all_cards: return 0
        
        all_ranks = sorted([self.ranks[c[0]] for c in all_cards], reverse=True)
        all_suits = [c[1] for c in all_cards]
        
        rank_counts = Counter(all_ranks)
        suit_counts = Counter(all_suits)
        
        counts = sorted(rank_counts.values(), reverse=True)

        is_flush = any(c >= 5 for c in suit_counts.values())
        
        unique_ranks = sorted(list(set(all_ranks)), reverse=True)
        is_straight = False
        if len(unique_ranks) >= 5:
            if set([14, 5, 4, 3, 2]).issubset(set(unique_ranks)):
                is_straight = True
            else:
                for i in range(len(unique_ranks) - 4):
                    if unique_ranks[i] - unique_ranks[i+4] == 4:
                        is_straight = True
                        break
        
        if is_straight and is_flush: return 8
        if counts[0] == 4: return 7
        if counts[0] == 3 and len(counts) > 1 and counts[1] >= 2: return 6
        if is_flush: return 5
        if is_straight: return 4
        if counts[0] == 3: return 3
        if counts[0] == 2 and len(counts) > 1 and counts[1] == 2: return 2
        if counts[0] == 2:
            pair_rank = [rank for rank, count in rank_counts.items() if count == 2][0]
            hole_ranks = [self.ranks[c[0]] for c in self.hand]
            community_ranks = sorted([self.ranks[c[0]] for c in community_cards], reverse=True)
            
            if community_ranks and pair_rank == community_ranks[0] and pair_rank in hole_ranks:
                return 1.5
            if hole_ranks[0] == hole_ranks[1] and pair_rank == hole_ranks[0] and community_ranks and pair_rank < community_ranks[0]:
                return 1.2
            return 1

        is_flush_draw = any(c == 4 for c in suit_counts.values())
        
        is_straight_draw = False
        if len(unique_ranks) >= 4:
            for i in range(len(unique_ranks) - 3):
                if unique_ranks[i] - unique_ranks[i+3] == 3:
                    is_straight_draw = True
                    break
            if not is_straight_draw:
                for i in range(len(unique_ranks) - 3):
                    if unique_ranks[i] - unique_ranks[i+3] == 4:
                        is_straight_draw = True
                        break
        if not is_straight_draw and len(set(unique_ranks).intersection({14,2,3,4,5})) == 4:
            is_straight_draw = True

        if is_flush_draw and is_straight_draw: return 0.8
        if is_flush_draw: return 0.7
        if is_straight_draw: return 0.6
        
        return 0

    def _get_clamped_raise_amount(self, amount: int, round_state: RoundStateClient, remaining_chips: int) -> int:
        min_raise = round_state.min_raise
        max_raise = remaining_chips
        return max(min_raise, min(amount, max_raise))

    def _update_opponent_stats(self, round_state: RoundStateClient):
        for p_id, p_state in round_state.player_states.items():
            if int(p_id) != self.id:
                stats = self.opponent_stats[int(p_id)]
                
                if round_state.round == 'preflop':
                    if p_state.has_acted and int(p_id) not in self.preflop_vpip_opportunities_given:
                        stats['vpip_opportunities'] += 1
                        self.preflop_vpip_opportunities_given.add(int(p_id))
                        
                        last_action = round_state.player_actions.get(p_id)
                        if last_action:
                            if last_action.action in ['Call', 'Raise']:
                                stats['vpip_put_money_in_pot'] += 1
                            
                            if not any(a.action == 'Raise' for a in round_state.player_actions.values()):
                                stats['pfr_opportunities'] += 1
                                if last_action.action == 'Raise':
                                    stats['pfr_raise_count'] += 1