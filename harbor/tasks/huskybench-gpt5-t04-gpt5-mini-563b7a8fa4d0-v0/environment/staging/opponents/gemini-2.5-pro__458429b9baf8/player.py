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
        # Positional awareness variables
        self.player_order = []
        self.sb_player_id = -1
        self.bb_player_id = -1

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print(f"My hand for this game is: {player_hands}")
        self.hand = player_hands
        # Store positional info
        self.player_order = all_players
        self.sb_player_id = small_blind_player_id
        self.bb_player_id = big_blind_player_id
        for p_id in all_players:
            if p_id != self.id:
                self.opponent_stats[p_id] = {
                    'vpip_put_money_in_pot': 0, 'vpip_opportunities': 0, 
                    'pfr_raise_count': 0, 'pfr_opportunities': 0, 
                    'cbet_opportunities': 0, 'cbet_fold_count': 0,
                    'afq_raises': 0, 'afq_calls': 0, 'afq_folds': 0,
                    'wtsd_saw_flop': 0, 'wtsd_showdown_count': 0
                }

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.was_preflop_aggressor = False
        # Reset per-round stat trackers
        self.preflop_vpip_opportunities_given = False
        self.vpip_acted_this_round = set()
        self.pfr_acted_this_round = set()
        self.opponents_saw_flop = set()
        self.processed_actions = set()


    def _get_position(self):
        """
        Determines the bot's position for the current hand.
        For 2 players (heads-up): SB is on the button (in position post-flop), BB is out of position.
        """
        if self.id == self.sb_player_id:
            return 'SB' # Button
        elif self.id == self.bb_player_id:
            return 'BB'
        return None # Should not happen in a 2-player game

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

    def _get_dynamic_bet_size(self, strength: float, pot: int, round_state: RoundStateClient, is_bluff: bool = False) -> int:
        big_blind = 2 * round_state.big_blind_amount
        if is_bluff:
            bet = int(pot * random.uniform(0.33, 0.5))
            return max(bet, big_blind)

        if strength >= 6:
            return int(pot * random.uniform(0.75, 1.2))
        elif strength >= 4:
            return int(pot * random.uniform(0.6, 0.9))
        elif strength >= 2:
            return int(pot * random.uniform(0.5, 0.75))
        elif strength >= 1.5:
            return int(pot * random.uniform(0.4, 0.6))
        else:
            return max(int(pot * 0.5), big_blind)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        self._update_opponent_stats(round_state)
        self._update_postflop_opponent_stats(round_state)
        self._update_cbet_stats(round_state)
        
        position = self._get_position()
        
        if round_state.round == 'preflop':
            strength = self._get_preflop_strength()
            big_blind = 2 * round_state.big_blind_amount
            
            if position == 'SB':
                if strength <= 5:
                    raise_amount = self._get_clamped_raise_amount(int(big_blind * random.uniform(2.5, 3.5)), round_state, remaining_chips)
                    self.was_preflop_aggressor = True
                    return PokerAction.RAISE, raise_amount
                elif strength <= 7:
                    return PokerAction.CALL, round_state.bet_to_match
                else:
                    return PokerAction.FOLD, 0
            
            elif position == 'BB':
                opponent_id = self.sb_player_id
                opp_stats = self.opponent_stats[opponent_id]
                vpip = (opp_stats['vpip_put_money_in_pot'] / opp_stats['vpip_opportunities']) if opp_stats['vpip_opportunities'] > 0 else 0.25
                pfr = (opp_stats['pfr_raise_count'] / opp_stats['pfr_opportunities']) if opp_stats['pfr_opportunities'] > 0 else 0.20
                
                is_facing_raise = round_state.bet_to_match > big_blind / 2
                
                if not is_facing_raise:
                    if strength <= 6:
                        raise_amount = self._get_clamped_raise_amount(int(big_blind * random.uniform(3.0, 4.0)), round_state, remaining_chips)
                        self.was_preflop_aggressor = True
                        return PokerAction.RAISE, raise_amount
                    else:
                        return PokerAction.CHECK, 0
                else:
                    if strength <= 3:
                        raise_amount = self._get_clamped_raise_amount(int(round_state.pot_total * random.uniform(2.2, 2.8)), round_state, remaining_chips)
                        return PokerAction.RAISE, raise_amount
                    elif strength <= 6:
                        return PokerAction.CALL, round_state.bet_to_match
                    elif strength <= 7 and random.random() < 0.2:
                        return PokerAction.CALL, round_state.bet_to_match
                    else:
                        return PokerAction.FOLD, 0

        else: # Post-flop
            opponent_id = self.sb_player_id if self.id == self.bb_player_id else self.bb_player_id
            opp_stats = self.opponent_stats[opponent_id]

            # Calculate AFq (Aggression Frequency) and WTSD (Went to Showdown)
            total_postflop_actions = opp_stats['afq_raises'] + opp_stats['afq_calls'] + opp_stats['afq_folds']
            afq = (opp_stats['afq_raises'] / total_postflop_actions) if total_postflop_actions > 5 else 0.33 # Smoothed default
            wtsd = (opp_stats['wtsd_showdown_count'] / opp_stats['wtsd_saw_flop']) if opp_stats['wtsd_saw_flop'] > 5 else 0.30 # Smoothed default

            # Classify opponent
            opponent_type = 'standard'
            if wtsd > 0.4 and afq < 0.25:
                opponent_type = 'calling_station'
            elif afq > 0.45:
                opponent_type = 'aggressive'
            elif wtsd < 0.25 and afq < 0.25:
                opponent_type = 'tight_passive'
            
            strength = self._get_postflop_strength(round_state.community_cards)
            pot = round_state.pot_total
            bet_to_match = round_state.bet_to_match
            is_facing_bet = bet_to_match > 0
            board_texture = self._get_board_texture(round_state.community_cards)

            if position == 'BB': # Out of Position
                if not is_facing_bet:
                    # Value Betting Logic
                    value_bet_threshold = 2
                    if opponent_type == 'calling_station':
                        value_bet_threshold = 1.5
                    if strength >= value_bet_threshold:
                        bet_amount = self._get_dynamic_bet_size(strength, pot, round_state)
                        return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # C-Betting Logic
                    elif self.was_preflop_aggressor and round_state.round == 'flop':
                        bluff_chance = 0.30
                        if opponent_type == 'tight_passive':
                            bluff_chance = 0.80 if board_texture == 'dry' else 0.50
                        elif opponent_type == 'calling_station':
                            bluff_chance = 0.15
                        
                        if random.random() < bluff_chance:
                            bet_amount = self._get_dynamic_bet_size(0, pot, round_state, is_bluff=True)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # Semi-Bluffing with Draws
                    elif 0.6 <= strength <= 0.8:
                        if opponent_type != 'calling_station': # Less semi-bluffing against stations
                            bet_amount = self._get_dynamic_bet_size(0, pot, round_state, is_bluff=True)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                    
                    # Default Action
                    else:
                        return PokerAction.CHECK, 0
                else: # Facing a bet
                    # Raising Logic (strong hands)
                    if strength >= 4:
                        raise_amount = self._get_clamped_raise_amount(int(pot * 2.5), round_state, remaining_chips)
                        return PokerAction.RAISE, raise_amount

                    # Calling Logic (medium hands)
                    call_threshold = 1.5
                    if opponent_type == 'aggressive':
                        call_threshold = 1.2
                    elif opponent_type == 'tight_passive':
                        call_threshold = 1.8
                    if strength >= call_threshold:
                        return PokerAction.CALL, bet_to_match

                    # Calling with Draws
                    elif 0.6 <= strength <= 0.8:
                        pot_odds = bet_to_match / (pot + bet_to_match)
                        draw_odds = (9/47) if strength == 0.7 else (8/47) # simplified odds
                        if pot_odds < draw_odds:
                            return PokerAction.CALL, bet_to_match
                        else:
                            return PokerAction.FOLD, 0
                    
                    # Default Action
                    else:
                        return PokerAction.FOLD, 0

            elif position == 'SB': # In Position
                if not is_facing_bet:
                    # Value Betting Logic
                    value_bet_threshold = 1.5
                    if opponent_type == 'calling_station':
                        value_bet_threshold = 1.2
                    if strength >= value_bet_threshold:
                        bet_amount = self._get_dynamic_bet_size(strength, pot, round_state)
                        return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # C-Betting Logic
                    elif self.was_preflop_aggressor and round_state.round == 'flop':
                        bluff_chance = 0.40
                        if opponent_type == 'tight_passive':
                            bluff_chance = 0.85 if board_texture == 'dry' else 0.60
                        elif opponent_type == 'calling_station':
                            bluff_chance = 0.25
                        
                        if random.random() < bluff_chance:
                            bet_amount = self._get_dynamic_bet_size(0, pot, round_state, is_bluff=True)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # Semi-Bluffing with Draws
                    elif 0.6 <= strength <= 0.8:
                        if opponent_type != 'calling_station':
                            bet_amount = self._get_dynamic_bet_size(0, pot, round_state, is_bluff=True)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                    
                    # Default Action
                    else:
                        return PokerAction.CHECK, 0
                else: # Facing a bet
                    # Raising Logic (strong hands)
                    if strength >= 4:
                        raise_amount = self._get_clamped_raise_amount(int(pot * 2.5), round_state, remaining_chips)
                        return PokerAction.RAISE, raise_amount

                    # Calling Logic (medium hands)
                    call_threshold = 1.0
                    if opponent_type == 'aggressive':
                        call_threshold = 0.9 # Float more against aggression
                    elif opponent_type == 'tight_passive':
                        call_threshold = 2.0 # Fold to donk bets from nits
                    if strength >= call_threshold:
                        return PokerAction.CALL, bet_to_match

                    # Calling with Draws
                    elif 0.6 <= strength <= 0.8:
                        pot_odds = bet_to_match / (pot + bet_to_match)
                        draw_odds = (9/47) if strength == 0.7 else (8/47) # simplified odds
                        if pot_odds < draw_odds:
                            return PokerAction.CALL, bet_to_match
                        else:
                            return PokerAction.FOLD, 0
                    
                    # Default Action
                    else:
                        return PokerAction.FOLD, 0
        
        return PokerAction.FOLD, 0

    def _get_board_texture(self, community_cards: List[str]) -> str:
        if not community_cards:
            return 'none'
        
        num_cards = len(community_cards)
        suits = [c[1] for c in community_cards]
        ranks = sorted([self.ranks[c[0]] for c in community_cards], reverse=True)

        suit_counts = Counter(suits)
        is_flush_draw = any(c >= 2 for c in suit_counts.values()) if num_cards < 5 else any(c >= 3 for c in suit_counts.values())

        rank_counts = Counter(ranks)
        is_paired = any(c >= 2 for c in rank_counts.values())

        gaps = [ranks[i] - ranks[i+1] for i in range(len(ranks) - 1)]
        connectivity = sum(1 for g in gaps if g <= 2) # Count small gaps
        is_straight_draw = connectivity >= 2

        if is_flush_draw and is_straight_draw:
            return 'wet'
        if is_flush_draw or is_straight_draw:
            return 'wet'
        if is_paired:
            return 'paired'
        
        return 'dry'

    def _get_postflop_strength(self, community_cards: List[str]) -> float:
        if not self.hand: return 0
        
        all_cards = self.hand + community_cards
        if len(all_cards) < 3: return 0

        ranks = sorted([self.ranks[c[0]] for c in all_cards], reverse=True)
        suits = [c[1] for c in all_cards]
        
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        
        counts = sorted(rank_counts.values(), reverse=True)
        
        is_flush = any(c >= 5 for c in suit_counts.values())
        
        unique_ranks = sorted(list(set(ranks)), reverse=True)
        is_straight = False
        if len(unique_ranks) >= 5:
            for i in range(len(unique_ranks) - 4):
                if unique_ranks[i] - unique_ranks[i+4] == 4:
                    is_straight = True
                    break
            if not is_straight and unique_ranks[0] == 14 and unique_ranks[1] == 5 and unique_ranks[2] == 4 and unique_ranks[3] == 3 and unique_ranks[4] == 2:
                is_straight = True

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
                if set([14, 2, 3, 4]).issubset(set(unique_ranks)) or set([14, 2, 3, 5]).issubset(set(unique_ranks)) or set([14, 2, 4, 5]).issubset(set(unique_ranks)) or set([14, 3, 4, 5]).issubset(set(unique_ranks)):
                    is_straight_draw = True
        
        if is_flush_draw and is_straight_draw: return 0.8
        if is_flush_draw: return 0.7
        if is_straight_draw: return 0.6
        
        return 0

    def _get_clamped_raise_amount(self, amount: int, round_state: RoundStateClient, remaining_chips: int) -> int:
        min_raise = round_state.min_raise
        max_raise = min(round_state.max_raise, remaining_chips)
        if max_raise < min_raise:
            return max(0, remaining_chips)
        return max(min_raise, min(amount, max_raise))

    def _update_opponent_stats(self, round_state: RoundStateClient):
        if round_state.round != 'preflop':
            return

        if not self.preflop_vpip_opportunities_given:
            for p_id in self.opponent_stats.keys():
                self.opponent_stats[p_id]['vpip_opportunities'] += 1
                self.opponent_stats[p_id]['pfr_opportunities'] += 1
            self.preflop_vpip_opportunities_given = True

        history = round_state.history.get('preflop', [])
        for action_data in history:
            p_id = action_data['player_id']
            if p_id in self.opponent_stats:
                action = action_data['action']
                
                is_vpip_action = False
                if action == 'CALL' or action == 'RAISE':
                    is_vpip_action = True
                
                is_bb = (p_id == self.bb_player_id)
                if is_bb and action == 'CHECK':
                    is_vpip_action = False

                if is_vpip_action and p_id not in self.vpip_acted_this_round:
                    self.opponent_stats[p_id]['vpip_put_money_in_pot'] += 1
                    self.vpip_acted_this_round.add(p_id)
                
                if action == 'RAISE' and p_id not in self.pfr_acted_this_round:
                    self.opponent_stats[p_id]['pfr_raise_count'] += 1
                    self.pfr_acted_this_round.add(p_id)

    def _update_postflop_opponent_stats(self, round_state: RoundStateClient):
        for street in ['flop', 'turn', 'river']:
            if street in round_state.history:
                for i, action_data in enumerate(round_state.history[street]):
                    action_id = f"{street}_{i}"
                    if action_id in self.processed_actions:
                        continue

                    p_id = action_data['player_id']
                    if p_id in self.opponent_stats:
                        if street == 'flop':
                            self.opponents_saw_flop.add(p_id)

                        action = action_data['action']
                        if action == 'RAISE':
                            self.opponent_stats[p_id]['afq_raises'] += 1
                        elif action == 'CALL':
                            self.opponent_stats[p_id]['afq_calls'] += 1
                        elif action == 'FOLD':
                            self.opponent_stats[p_id]['afq_folds'] += 1
                    
                    self.processed_actions.add(action_id)

    def _update_cbet_stats(self, round_state: RoundStateClient):
        if round_state.round != 'turn':
            return

        if not self.was_preflop_aggressor:
            return

        flop_history = round_state.history.get('flop', [])
        if not flop_history:
            return

        opponent_id = -1
        for p_id in self.player_order:
            if p_id != self.id:
                opponent_id = p_id
                break
        if opponent_id == -1:
            return

        first_actor_id = flop_history[0]['player_id']
        first_action = flop_history[0]['action']
        
        cbet_made = False
        if first_actor_id == self.id:
            if first_action == 'RAISE':
                cbet_made = True
        elif first_actor_id == opponent_id and first_action == 'CHECK':
            for action in flop_history[1:]:
                if action['player_id'] == self.id:
                    if action['action'] == 'RAISE':
                        cbet_made = True
                    break
        
        if cbet_made:
            self.opponent_stats[opponent_id]['cbet_opportunities'] += 1
            
            opponent_folded = False
            for action in flop_history:
                if action['player_id'] == opponent_id and action['action'] == 'FOLD':
                    opponent_folded = True
                    break
            
            if opponent_folded:
                self.opponent_stats[opponent_id]['cbet_fold_count'] += 1

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        showdown_players = set(round_state.player_hands.keys())
        for p_id in self.opponents_saw_flop:
            self.opponent_stats[p_id]['wtsd_saw_flop'] += 1
            if str(p_id) in showdown_players:
                self.opponent_stats[p_id]['wtsd_showdown_count'] += 1

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass