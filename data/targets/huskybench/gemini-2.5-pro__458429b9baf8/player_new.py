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
                self.opponent_stats[p_id] = {'vpip_put_money_in_pot': 0, 'vpip_opportunities': 0, 'pfr_raise_count': 0, 'pfr_opportunities': 0, 'cbet_opportunities': 0, 'cbet_fold_count': 0}

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        self.was_preflop_aggressor = False
        self.preflop_vpip_opportunities_given = set()

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
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0

            elif position == 'BB':
                is_facing_raise = round_state.current_bet > big_blind
                
                if not is_facing_raise:
                    if strength <= 6:
                        raise_amount = self._get_clamped_raise_amount(int(big_blind * random.uniform(3.5, 4.5)), round_state, remaining_chips)
                        self.was_preflop_aggressor = True
                        return PokerAction.RAISE, raise_amount
                    else:
                        return PokerAction.CHECK, 0
                else:
                    if strength <= 4:
                        raise_amount = self._get_clamped_raise_amount(int(round_state.current_bet * random.uniform(2.8, 3.2)), round_state, remaining_chips)
                        self.was_preflop_aggressor = True
                        return PokerAction.RAISE, raise_amount
                    elif strength <= 6:
                        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet) if (round_state.pot + round_state.current_bet) > 0 else 1
                        if pot_odds < 0.35:
                            return PokerAction.CALL, 0
                        else:
                            return PokerAction.FOLD, 0
                    else:
                        return PokerAction.FOLD, 0
            
            return (PokerAction.CHECK, 0) if round_state.current_bet == 0 else (PokerAction.FOLD, 0)

        else: # Post-flop
            strength = self._get_postflop_strength(round_state.community_cards)
            opponent_id = [p_id for p_id in self.player_order if p_id != self.id][0]
            stats = self.opponent_stats[opponent_id]
            fold_to_cbet_rate = 0
            if stats['cbet_opportunities'] > 2:
                fold_to_cbet_rate = stats['cbet_fold_count'] / stats['cbet_opportunities']

            # --- Positional Logic ---
            is_facing_bet = round_state.current_bet > 0

            # IN POSITION (SB) - Acts last
            if position == 'SB':
                # Case 1: Opponent checked to us. We can bet.
                if not is_facing_bet:
                    # C-Betting: We were pre-flop aggressor, now we can make a continuation bet.
                    if self.was_preflop_aggressor and round_state.round == 'flop':
                        # Bluff c-bet with weak hands if opponent folds a lot
                        if strength < 1 and (fold_to_cbet_rate > 0.5 or stats['cbet_opportunities'] <= 2):
                             bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state, is_bluff=True)
                             return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                        # Value c-bet with strong hands
                        elif strength >= 1.5:
                            bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                    
                    # Semi-bluff with draws
                    if 0.6 <= strength < 1:
                        bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state, is_bluff=True)
                        return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # Value bet with medium-strong hands or better
                    if strength >= 1.2: # Lowered threshold for IP
                        bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state)
                        return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                    
                    # If nothing else, check back.
                    return PokerAction.CHECK, 0

                # Case 2: Opponent bet into us. We can call, raise, or fold.
                else:
                    # Raise for value with very strong hands
                    if strength >= 3: # Trips or better
                        raise_multiplier = random.uniform(2.0, 2.8)
                        raise_amount = self._get_clamped_raise_amount(int(round_state.current_bet * raise_multiplier), round_state, remaining_chips)
                        return PokerAction.RAISE, raise_amount

                    # Call with medium-strength hands and good draws
                    if strength >= 1 or (0.6 <= strength < 1):
                        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                        # More willing to call with position and draws
                        if strength >= 1 or pot_odds < 0.4:
                            return PokerAction.CALL, 0
                    
                    # Fold otherwise
                    return PokerAction.FOLD, 0

            # OUT OF POSITION (BB) - Acts first
            elif position == 'BB':
                # Case 1: We are first to act. We can check or bet.
                if not is_facing_bet:
                    # C-Betting: We were pre-flop aggressor
                    if self.was_preflop_aggressor and round_state.round == 'flop':
                        # Value c-bet with strong hands
                        if strength >= 1.5:
                            bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                        # More cautious with bluff c-bets OOP
                        elif strength < 1 and (fold_to_cbet_rate > 0.6 or stats['cbet_opportunities'] <= 2):
                             bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state, is_bluff=True)
                             return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # Donk Betting / Probing: Bet with strong hands even if not PFA
                    if not self.was_preflop_aggressor and strength >= 2:
                        bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state)
                        return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)
                    
                    # Check with most other hands to control the pot
                    return PokerAction.CHECK, 0
                
                # Case 2: We checked and opponent bet. We can call, raise, or fold.
                else:
                    # Check-raise with very strong hands
                    if strength >= 4: # Straight or better
                        raise_multiplier = random.uniform(2.2, 3.0)
                        raise_amount = self._get_clamped_raise_amount(int(round_state.current_bet * raise_multiplier), round_state, remaining_chips)
                        return PokerAction.RAISE, raise_amount
                    
                    # Check-call with medium hands and good draws
                    if strength >= 1.5 or (0.7 <= strength < 1): # Need better draws to call OOP
                        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                        if strength >= 1.5 or pot_odds < 0.33: # Tighter pot odds requirement
                            return PokerAction.CALL, 0
                    
                    # Check-fold otherwise
                    return PokerAction.FOLD, 0

            return (PokerAction.CHECK, 0) if round_state.current_bet == 0 else (PokerAction.FOLD, 0)

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
        is_preflop = round_state.round == 'preflop'
        
        for p_id in self.opponent_stats.keys():
            p_id_str = str(p_id)
            
            if is_preflop and p_id not in self.preflop_vpip_opportunities_given:
                self.opponent_stats[p_id]['vpip_opportunities'] += 1
                self.opponent_stats[p_id]['pfr_opportunities'] += 1
                self.preflop_vpip_opportunities_given.add(p_id)

            if p_id_str in round_state.player_actions:
                action = round_state.player_actions[p_id_str]
                bet = round_state.player_bets.get(p_id_str, 0)

                if is_preflop:
                    if bet > round_state.big_blind_amount or action == 'RAISE':
                        if self.opponent_stats[p_id]['vpip_put_money_in_pot'] == 0:
                           self.opponent_stats[p_id]['vpip_put_money_in_pot'] = 1
                        self.opponent_stats[p_id]['pfr_raise_count'] += 1
                    elif action == 'CALL' or action == 'CHECK':
                        if self.opponent_stats[p_id]['vpip_put_money_in_pot'] == 0:
                           self.opponent_stats[p_id]['vpip_put_money_in_pot'] = 1
        pass

    def _update_postflop_opponent_stats(self, round_state: RoundStateClient):
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
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass