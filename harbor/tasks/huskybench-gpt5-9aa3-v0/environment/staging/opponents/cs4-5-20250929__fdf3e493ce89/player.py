from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = []
        self.starting_chips = 0
        self.blind_amount = 0
        
    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.starting_chips = starting_chips
        self.blind_amount = blind_amount
        self.hand = player_hands
        
    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """Returns the action for the player based on hand strength and game state."""
        
        # Evaluate hand strength (now considers community cards)
        hand_strength = self._evaluate_hand_strength(round_state)
        
        # Calculate pot odds
        pot_odds = self._calculate_pot_odds(round_state, remaining_chips)
        
        # Determine aggression level based on hand strength
        if hand_strength >= 0.8:  # Very strong hand
            return self._play_aggressive(round_state, remaining_chips)
        elif hand_strength >= 0.6:  # Strong hand
            return self._play_strong(round_state, remaining_chips)
        elif hand_strength >= 0.4:  # Medium hand
            return self._play_medium(round_state, remaining_chips, pot_odds)
        else:  # Weak hand
            return self._play_weak(round_state, remaining_chips, pot_odds)
    
    def _evaluate_hand_strength(self, round_state: RoundStateClient) -> float:
        """Evaluate hand strength considering both hole cards and community cards."""
        if not self.hand or len(self.hand) < 2:
            return 0.3
        
        # If we have community cards, evaluate actual hand strength
        if round_state.community_cards and len(round_state.community_cards) > 0:
            return self._evaluate_made_hand(round_state.community_cards)
        
        # Otherwise, evaluate preflop hand strength
        return self._evaluate_preflop_strength()
    
    def _evaluate_preflop_strength(self) -> float:
        """Evaluate preflop hand strength based on hole cards only."""
        card1, card2 = self.hand[0], self.hand[1]
        rank1, suit1 = card1[0], card1[1]
        rank2, suit2 = card2[0], card2[1]
        
        # Rank values
        rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                      '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        val1 = rank_values.get(rank1, 0)
        val2 = rank_values.get(rank2, 0)
        
        # Base strength on card values
        max_val = max(val1, val2)
        min_val = min(val1, val2)
        
        # Pocket pairs
        if val1 == val2:
            if val1 >= 10:  # High pocket pairs (TT+)
                return 0.85 + (val1 - 10) * 0.03
            elif val1 >= 7:  # Medium pocket pairs (77-99)
                return 0.65 + (val1 - 7) * 0.05
            else:  # Low pocket pairs (22-66)
                return 0.50 + (val1 - 2) * 0.03
        
        # Suited cards
        suited = (suit1 == suit2)
        
        # High cards (both cards 10+)
        if min_val >= 10:
            base = 0.70
            if suited:
                base += 0.10
            if val1 == 14 or val2 == 14:  # Has an Ace
                base += 0.10
            return min(base, 0.95)
        
        # One high card
        if max_val >= 10:
            base = 0.40 + (max_val - 10) * 0.05
            if suited:
                base += 0.08
            if max_val == 14:  # Ace
                base += 0.10
            return min(base, 0.75)
        
        # Connected cards (potential straights)
        if abs(val1 - val2) <= 2:
            base = 0.35
            if suited:
                base += 0.05
            return base
        
        # Low cards
        return 0.25
    
    def _evaluate_made_hand(self, community_cards: List[str]) -> float:
        """Evaluate actual made hand strength with community cards."""
        all_cards = self.hand + community_cards
        
        # Rank values
        rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                      '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        # Count ranks and suits
        rank_counts = {}
        suit_counts = {}
        ranks = []
        
        for card in all_cards:
            rank, suit = card[0], card[1]
            rank_val = rank_values.get(rank, 0)
            ranks.append(rank_val)
            rank_counts[rank_val] = rank_counts.get(rank_val, 0) + 1
            suit_counts[suit] = suit_counts.get(suit, 0) + 1
        
        # Check for flush
        has_flush = any(count >= 5 for count in suit_counts.values())
        
        # Check for straight
        has_straight = False
        sorted_ranks = sorted(set(ranks))
        for i in range(len(sorted_ranks) - 4):
            if sorted_ranks[i+4] - sorted_ranks[i] == 4:
                has_straight = True
                break
        # Check for A-2-3-4-5 straight (wheel)
        if set([14, 2, 3, 4, 5]).issubset(set(ranks)):
            has_straight = True
        
        # Get pairs, trips, quads
        pairs = [rank for rank, count in rank_counts.items() if count == 2]
        trips = [rank for rank, count in rank_counts.items() if count == 3]
        quads = [rank for rank, count in rank_counts.items() if count == 4]
        
        # Evaluate hand
        if has_straight and has_flush:
            return 0.99  # Straight flush
        elif quads:
            return 0.95  # Four of a kind
        elif trips and pairs:
            return 0.90  # Full house
        elif has_flush:
            return 0.85  # Flush
        elif has_straight:
            return 0.80  # Straight
        elif trips:
            return 0.70  # Three of a kind
        elif len(pairs) >= 2:
            return 0.60  # Two pair
        elif len(pairs) == 1:
            # One pair - strength depends on pair rank
            pair_rank = pairs[0]
            if pair_rank >= 10:
                return 0.50  # High pair
            else:
                return 0.40  # Low pair
        else:
            # High card - check if we have top pair potential
            my_ranks = [rank_values.get(card[0], 0) for card in self.hand]
            max_my_rank = max(my_ranks)
            if max_my_rank >= 12:  # King or Ace
                return 0.35
            elif max_my_rank >= 10:  # Queen or Jack
                return 0.30
            else:
                return 0.20
    
    def _calculate_pot_odds(self, round_state: RoundStateClient, remaining_chips: int) -> float:
        """Calculate pot odds."""
        if round_state.current_bet == 0:
            return 1.0
        
        call_amount = round_state.current_bet - round_state.player_bets.get(str(self.id), 0)
        if call_amount <= 0:
            return 1.0
        
        pot_after_call = round_state.pot + call_amount
        if pot_after_call == 0:
            return 0.0
        
        return call_amount / pot_after_call
    
    def _play_aggressive(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """Play aggressively with strong hands."""
        my_bet = round_state.player_bets.get(str(self.id), 0)
        
        if round_state.current_bet == 0:
            # No one has bet - raise
            # Use blind_amount if available, otherwise use min_raise
            base_raise = self.blind_amount * 3 if self.blind_amount > 0 else round_state.min_raise
            raise_amount = max(round_state.min_raise, base_raise)
            raise_amount = min(raise_amount, round_state.max_raise, remaining_chips)
            
            # Safety check: only raise if amount is valid
            if raise_amount > 0 and raise_amount >= round_state.min_raise:
                return PokerAction.RAISE, raise_amount
            else:
                return PokerAction.CHECK, 0
        else:
            # Someone has bet - re-raise or call
            call_amount = round_state.current_bet - my_bet
            
            if call_amount >= remaining_chips:
                # All-in call
                return PokerAction.CALL, 0
            
            # Calculate re-raise amount (total amount to bet)
            total_raise = round_state.current_bet + round_state.min_raise
            
            # Make sure we don't exceed our chips or max_raise
            total_raise = min(total_raise, remaining_chips)
            
            # Check if we can actually raise
            if total_raise > round_state.current_bet and total_raise >= round_state.current_bet + round_state.min_raise and total_raise <= round_state.max_raise:
                return PokerAction.RAISE, total_raise
            else:
                # Can't raise, just call
                return PokerAction.CALL, 0
    
    def _play_strong(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """Play strong hands with moderate aggression."""
        my_bet = round_state.player_bets.get(str(self.id), 0)
        
        if round_state.current_bet == 0:
            # No one has bet - raise
            base_raise = self.blind_amount * 2 if self.blind_amount > 0 else round_state.min_raise
            raise_amount = max(round_state.min_raise, base_raise)
            raise_amount = min(raise_amount, round_state.max_raise, remaining_chips)
            
            # Safety check
            if raise_amount > 0 and raise_amount >= round_state.min_raise:
                return PokerAction.RAISE, raise_amount
            else:
                return PokerAction.CHECK, 0
        else:
            # Call or fold based on bet size
            call_amount = round_state.current_bet - my_bet
            
            if call_amount >= remaining_chips:
                return PokerAction.CALL, 0
            
            # Call if bet is reasonable (less than 1/3 of our stack)
            if call_amount <= remaining_chips / 3:
                return PokerAction.CALL, 0
            else:
                return PokerAction.FOLD, 0
    
    def _play_medium(self, round_state: RoundStateClient, remaining_chips: int, pot_odds: float) -> Tuple[PokerAction, int]:
        """Play medium hands cautiously."""
        my_bet = round_state.player_bets.get(str(self.id), 0)
        
        if round_state.current_bet == 0:
            # Check or small raise preflop
            if round_state.round_num == 1:  # Preflop
                base_raise = self.blind_amount * 2 if self.blind_amount > 0 else round_state.min_raise
                raise_amount = max(round_state.min_raise, base_raise)
                raise_amount = min(raise_amount, round_state.max_raise, remaining_chips)
                
                if raise_amount > 0 and raise_amount >= round_state.min_raise:
                    return PokerAction.RAISE, raise_amount
            
            return PokerAction.CHECK, 0
        else:
            # Call with good pot odds, fold otherwise
            call_amount = round_state.current_bet - my_bet
            
            if call_amount >= remaining_chips:
                if pot_odds < 0.4:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            
            if pot_odds < 0.3:
                return PokerAction.CALL, 0
            else:
                return PokerAction.FOLD, 0
    
    def _play_weak(self, round_state: RoundStateClient, remaining_chips: int, pot_odds: float) -> Tuple[PokerAction, int]:
        """Play weak hands very cautiously."""
        my_bet = round_state.player_bets.get(str(self.id), 0)
        
        if round_state.current_bet == 0:
            return PokerAction.CHECK, 0
        else:
            call_amount = round_state.current_bet - my_bet
            
            # Only call with very good pot odds and small bets
            if pot_odds < 0.2 and call_amount < self.blind_amount * 2:
                return PokerAction.CALL, 0
            else:
                return PokerAction.FOLD, 0
    
    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the end of each round."""
        pass
    
    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        """Called at the end of the game."""
        pass