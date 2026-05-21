from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_cards = []
        self.position = None  # 'small_blind' or 'big_blind'
        
    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        
        self.my_cards = player_hands
        self.position = 'small_blind' if self.id == small_blind_player_id else 'big_blind'

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def card_value(self, card):
        """Convert card rank to numeric value for comparison"""
        rank = card[0]
        if rank == 'A':
            return 14
        elif rank == 'K':
            return 13
        elif rank == 'Q':
            return 12
        elif rank == 'J':
            return 11
        elif rank == 'T':
            return 10
        else:
            return int(rank)
    
    def evaluate_preflop_hand(self):
        """Evaluate preflop hand strength (0-1 scale)"""
        if len(self.my_cards) != 2:
            return 0.5
            
        card1, card2 = self.my_cards
        val1, val2 = self.card_value(card1), self.card_value(card2)
        suit1, suit2 = card1[1], card2[1]
        
        # Pair bonus
        if val1 == val2:
            if val1 >= 10:  # High pairs (TT+)
                return 0.9
            elif val1 >= 7:  # Medium pairs (77-99)
                return 0.7
            else:  # Low pairs
                return 0.6
        
        # High cards
        high_card = max(val1, val2)
        low_card = min(val1, val2)
        
        # Suited bonus
        suited_bonus = 0.1 if suit1 == suit2 else 0
        
        # Connected cards bonus
        connected_bonus = 0.05 if abs(val1 - val2) == 1 else 0
        
        # Base strength from high card
        if high_card == 14:  # Ace
            base_strength = 0.8 if low_card >= 10 else 0.6
        elif high_card >= 12:  # King or Queen
            base_strength = 0.6 if low_card >= 9 else 0.4
        elif high_card >= 10:  # Jack or Ten
            base_strength = 0.5 if low_card >= 8 else 0.3
        else:
            base_strength = 0.2
            
        return min(0.95, base_strength + suited_bonus + connected_bonus)
    
    def check_straight(self, values):
        """Check if values form a straight"""
        unique_values = sorted(set(values))
        if len(unique_values) < 5:
            return False
            
        # Check for regular straights
        for i in range(len(unique_values) - 4):
            if unique_values[i+4] - unique_values[i] == 4:
                return True
        
        # Check for A-2-3-4-5 straight (wheel)
        if set([14, 2, 3, 4, 5]).issubset(set(unique_values)):
            return True
            
        return False
    
    def check_flush(self, suits):
        """Check if suits form a flush"""
        suit_counts = {}
        for suit in suits:
            suit_counts[suit] = suit_counts.get(suit, 0) + 1
        return max(suit_counts.values()) >= 5

    def count_outs(self, community_cards):
        """Count potential outs for draws"""
        all_cards = self.my_cards + community_cards
        values = [self.card_value(card) for card in all_cards]
        suits = [card[1] for card in all_cards]
        
        outs = 0
        
        # Flush draw outs
        suit_counts = {}
        for suit in suits:
            suit_counts[suit] = suit_counts.get(suit, 0) + 1
            if suit_counts.get(suit, 0) == 4:  # 4-card flush draw
                outs += 9  # 13 cards in suit - 4 already seen
        
        # Straight draw outs (simplified)
        unique_values = sorted(set(values))
        if len(unique_values) >= 4:
            # Check for open-ended straight draws
            for i in range(len(unique_values) - 3):
                if unique_values[i+3] - unique_values[i] == 3:
                    outs += 8  # Open-ended straight draw
                elif unique_values[i+3] - unique_values[i] == 4:
                    outs += 4  # Gutshot straight draw
        
        return outs
    
    def evaluate_postflop_hand(self, community_cards):
        """Enhanced postflop hand evaluation"""
        all_cards = self.my_cards + community_cards
        if len(all_cards) < 5:
            return self.evaluate_preflop_hand()
            
        values = [self.card_value(card) for card in all_cards]
        suits = [card[1] for card in all_cards]
        
        # Check for made hands
        value_counts = {}
        for val in values:
            value_counts[val] = value_counts.get(val, 0) + 1
        
        pairs = sum(1 for count in value_counts.values() if count == 2)
        trips = sum(1 for count in value_counts.values() if count == 3)
        quads = sum(1 for count in value_counts.values() if count == 4)
        
        # Check for straight and flush
        has_straight = self.check_straight(values)
        has_flush = self.check_flush(suits)
        
        # Evaluate made hands
        if has_straight and has_flush:
            return 0.98  # Straight flush
        elif quads > 0:
            return 0.95  # Four of a kind
        elif trips > 0 and pairs > 0:
            return 0.90  # Full house
        elif has_flush:
            return 0.85  # Flush
        elif has_straight:
            return 0.80  # Straight
        elif trips > 0:
            return 0.75  # Three of a kind
        elif pairs >= 2:
            return 0.70  # Two pair
        elif pairs == 1:
            # Check if it's top pair
            my_values = [self.card_value(card) for card in self.my_cards]
            community_values = [self.card_value(card) for card in community_cards]
            pair_value = max([val for val, count in value_counts.items() if count == 2])
            
            if pair_value in my_values and pair_value >= max(community_values):
                return 0.65  # Top pair
            else:
                return 0.55  # Lower pair
        else:
            # High card or draws
            my_values = [self.card_value(card) for card in self.my_cards]
            community_values = [self.card_value(card) for card in community_cards]
            
            # Count outs for potential draws
            outs = self.count_outs(community_cards)
            
            if outs >= 12:  # Strong draw (flush + straight possibilities)
                return 0.60
            elif outs >= 8:  # Good draw (open-ended straight or flush draw)
                return 0.50
            elif outs >= 4:  # Weak draw (gutshot)
                return 0.40
            elif max(my_values) >= max(community_values):
                return 0.35  # Overcards
            else:
                return 0.25  # Undercards

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        
        # Evaluate hand strength
        if round_state.round == 'Preflop':
            hand_strength = self.evaluate_preflop_hand()
        else:
            hand_strength = self.evaluate_postflop_hand(round_state.community_cards)
        
        print(f"Hand strength: {hand_strength:.2f}")
        
        # Position-based adjustment for preflop play
        if round_state.round == 'Preflop':
            if self.position == 'big_blind':
                # More aggressive in big blind (acts last preflop)
                hand_strength += 0.05
            elif self.position == 'small_blind':
                # Slightly tighter in small blind (acts first postflop)
                hand_strength -= 0.02
        
        # Cap hand strength at 0.95
        hand_strength = min(0.95, hand_strength)
        
        # Get pot odds and betting info
        pot_size = round_state.pot
        # Fix pot size calculation when main pot is 0
        if pot_size == 0 and round_state.side_pots:
            pot_size = sum(side_pot["amount"] for side_pot in round_state.side_pots)
        current_bet = round_state.current_bet
        min_raise = round_state.min_raise
        max_raise = round_state.max_raise
        
        # Calculate how much we need to call
        my_bet = round_state.player_bets.get(str(self.id), 0)
        call_amount = current_bet - my_bet
        
        print(f"Current bet: {current_bet}, Call amount: {call_amount}, Pot size: {pot_size}")
        
        # Aggressive play with strong hands
        if hand_strength >= 0.85:  # Very strong hands (full house, etc.)
            if current_bet == 0:
                # Bet for value
                bet_size = min(max_raise, max(min_raise, pot_size // 2)) if min_raise > 0 else 0
                if bet_size > 0:
                    return PokerAction.RAISE, bet_size
                else:
                    return PokerAction.CHECK, 0
            elif call_amount <= remaining_chips // 2:  # Willing to risk half stack
                # Raise for value if possible, otherwise call
                if call_amount + min_raise <= max_raise:
                    raise_size = min(max_raise, call_amount + min_raise)
                    return PokerAction.RAISE, raise_size
                else:
                    return PokerAction.CALL, 0
            else:
                return PokerAction.CALL, 0
                
        elif hand_strength >= 0.8:  # Strong hands
            if current_bet == 0:
                bet_size = min(max_raise, max(min_raise, pot_size // 2)) if min_raise > 0 else 0
                if bet_size > 0:
                    return PokerAction.RAISE, bet_size
                else:
                    return PokerAction.CHECK, 0
            elif call_amount <= remaining_chips // 3:  # Willing to risk third of stack
                # Raise for value if possible, otherwise call
                if call_amount + min_raise <= max_raise:
                    raise_size = min(max_raise, call_amount + min_raise)
                    return PokerAction.RAISE, raise_size
                else:
                    return PokerAction.CALL, 0
            else:
                return PokerAction.CALL, 0
                
        # Medium strength hands and strong draws
        elif hand_strength >= 0.55:
            if current_bet == 0:
                # Small bet for value or to build pot
                bet_size = min(max_raise, max(min_raise, pot_size // 3 if pot_size > 0 else min_raise)) if min_raise > 0 else 0
                if bet_size > 0:
                    return PokerAction.RAISE, bet_size
                else:
                    return PokerAction.CHECK, 0
            elif call_amount <= pot_size // 4:  # Very good pot odds
                return PokerAction.CALL, 0
            else:
                return PokerAction.FOLD, 0
        
        # Weak hands and weak draws
        elif hand_strength >= 0.4:
            if current_bet == 0:
                # Small probe bet with weak hands when no action
                if hand_strength >= 0.45:
                    bet_size = min(max_raise, max(min_raise, pot_size // 4 if pot_size > 0 else min_raise)) if min_raise > 0 else 0
                    if bet_size > 0:
                        return PokerAction.RAISE, bet_size
                    else:
                        return PokerAction.CHECK, 0
                else:
                    return PokerAction.CHECK, 0
            elif call_amount <= pot_size // 6:  # Excellent pot odds
                return PokerAction.CALL, 0
            else:
                return PokerAction.FOLD, 0
        
        # Very weak hands
        else:
            if current_bet == 0:
                return PokerAction.CHECK, 0
            else:
                return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)