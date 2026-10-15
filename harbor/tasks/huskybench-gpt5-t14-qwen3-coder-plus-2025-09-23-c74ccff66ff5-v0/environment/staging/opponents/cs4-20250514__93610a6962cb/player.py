from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_cards = []
        
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
    
    def card_suit(self, card):
        """Get the suit of a card"""
        return card[1]
    
    def evaluate_hand_with_community(self, hole_cards, community_cards):
        """Evaluate hand strength considering community cards"""
        all_cards = hole_cards + community_cards
        if len(all_cards) < 2:
            return self.evaluate_hand_strength(hole_cards)
        
        # Convert cards to values and suits
        card_values = [self.card_value(card) for card in all_cards]
        card_suits = [self.card_suit(card) for card in all_cards]
        
        # Count occurrences of each value and suit
        value_counts = {}
        suit_counts = {}
        for value in card_values:
            value_counts[value] = value_counts.get(value, 0) + 1
        for suit in card_suits:
            suit_counts[suit] = suit_counts.get(suit, 0) + 1
        
        # Sort values by count and value
        sorted_values = sorted(value_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
        
        # Check for flush
        has_flush = any(count >= 5 for count in suit_counts.values())
        
        # Check for straight
        unique_values = sorted(set(card_values), reverse=True)
        has_straight = False
        straight_high = 0
        
        # Check for regular straight
        for i in range(len(unique_values) - 4):
            if unique_values[i] - unique_values[i+4] == 4:
                has_straight = True
                straight_high = unique_values[i]
                break
        
        # Check for A-2-3-4-5 straight (wheel)
        if set([14, 2, 3, 4, 5]).issubset(set(unique_values)):
            has_straight = True
            straight_high = 5  # 5-high straight
        
        # Hand rankings (higher is better)
        if has_straight and has_flush:
            return 0.95  # Straight flush
        elif sorted_values[0][1] == 4:
            return 0.9   # Four of a kind
        elif sorted_values[0][1] == 3 and sorted_values[1][1] == 2:
            return 0.85  # Full house
        elif has_flush:
            return 0.8   # Flush
        elif has_straight:
            return 0.75  # Straight
        elif sorted_values[0][1] == 3:
            return 0.7   # Three of a kind
        elif sorted_values[0][1] == 2 and sorted_values[1][1] == 2:
            return 0.65  # Two pair
        elif sorted_values[0][1] == 2:
            # One pair - adjust based on pair value
            pair_value = sorted_values[0][0]
            if pair_value >= 10:
                return 0.6   # High pair
            else:
                return 0.55  # Low pair
        else:
            # High card - consider the highest card
            high_card = max(card_values)
            if high_card == 14:  # Ace high
                return 0.5
            elif high_card >= 12:  # King or Queen high
                return 0.45
            else:
                return 0.4
    
    def evaluate_hand_strength(self, cards):
        """Basic hand strength evaluation for hole cards only"""
        if len(cards) != 2:
            return 0.5  # neutral strength
            
        card1_val = self.card_value(cards[0])
        card2_val = self.card_value(cards[1])
        card1_suit = cards[0][1]
        card2_suit = cards[1][1]
        
        # Pair strength
        if card1_val == card2_val:
            if card1_val >= 10:  # TT, JJ, QQ, KK, AA
                return 0.9
            elif card1_val >= 7:  # 77, 88, 99
                return 0.7
            else:  # 22-66
                return 0.6
        
        # High cards
        high_card = max(card1_val, card2_val)
        low_card = min(card1_val, card2_val)
        
        # Suited bonus
        suited_bonus = 0.1 if card1_suit == card2_suit else 0
        
        # Connected bonus (for straights)
        connected_bonus = 0.05 if abs(card1_val - card2_val) == 1 else 0
        
        # Base strength from high card
        if high_card == 14:  # Ace
            if low_card >= 10:  # AK, AQ, AJ, AT
                return 0.8 + suited_bonus
            elif low_card >= 7:  # A9, A8, A7
                return 0.6 + suited_bonus
            else:  # A6 and below
                return 0.5 + suited_bonus
        elif high_card >= 12:  # King or Queen
            if low_card >= 10:  # KQ, KJ, KT, QJ, QT
                return 0.7 + suited_bonus + connected_bonus
            elif low_card >= 7:  # K9-K7, Q9-Q7
                return 0.5 + suited_bonus
            else:
                return 0.4 + suited_bonus
        elif high_card >= 10:  # Jack or Ten
            if low_card >= 8:  # JT, J9, T9, T8
                return 0.6 + suited_bonus + connected_bonus
            else:
                return 0.4 + suited_bonus
        else:
            # Low cards
            if connected_bonus > 0 and suited_bonus > 0:  # suited connectors
                return 0.4 + suited_bonus + connected_bonus
            else:
                return 0.3 + suited_bonus

    def calculate_pot_odds(self, call_amount, pot_size):
        """Calculate pot odds for calling"""
        if call_amount == 0:
            return float('inf')  # Free to call
        return pot_size / call_amount

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        
        # Store our cards for decision making
        self.my_cards = player_hands

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        
        # Evaluate hand strength based on round
        if round_state.round == "preflop":
            hand_strength = self.evaluate_hand_strength(self.my_cards)
        else:
            # Post-flop: use community cards
            hand_strength = self.evaluate_hand_with_community(self.my_cards, round_state.community_cards)
        
        print(f"Hand strength: {hand_strength:.2f} for cards {self.my_cards} with community {round_state.community_cards}")
        
        # Check if anyone has raised
        raised = False
        for player_action in round_state.player_actions.values():
            if player_action == "Raise":
                raised = True
                break
        
        # Determine pot odds and betting strategy
        pot_size = round_state.pot
        current_bet = round_state.current_bet
        call_amount = current_bet - round_state.player_bets.get(str(self.id), 0)
        
        # Calculate pot odds if we need to call
        pot_odds = self.calculate_pot_odds(call_amount, pot_size) if call_amount > 0 else float('inf')
        
        # Preflop strategy
        if round_state.round == "preflop":
            if hand_strength >= 0.8:  # Premium hands
                if not raised:
                    # Raise with premium hands
                    raise_amount = min(max(round_state.min_raise, pot_size // 2), remaining_chips // 8)
                    return PokerAction.RAISE, raise_amount
                else:
                    # Re-raise or call with premium hands
                    if hand_strength >= 0.9 and call_amount <= remaining_chips // 4:
                        raise_amount = min(max(round_state.min_raise, call_amount * 2), remaining_chips // 4)
                        return PokerAction.RAISE, raise_amount
                    elif call_amount <= remaining_chips // 6:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
            elif hand_strength >= 0.6:  # Good hands
                if not raised:
                    if hand_strength >= 0.7:
                        raise_amount = min(max(round_state.min_raise, pot_size // 3), remaining_chips // 15)
                        return PokerAction.RAISE, raise_amount
                    else:
                        return PokerAction.CHECK if current_bet == 0 else PokerAction.CALL, 0
                else:
                    # Call with good hands if not too expensive
                    if call_amount <= remaining_chips // 10:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
            elif hand_strength >= 0.4:  # Marginal hands
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                elif call_amount <= remaining_chips // 20:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:  # Weak hands
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.FOLD, 0
        
        # Post-flop strategy (improved with actual hand evaluation)
        else:
            if hand_strength >= 0.8:  # Very strong hands (flush, straight, etc.)
                if current_bet == 0:
                    # Bet for value
                    raise_amount = min(max(round_state.min_raise, pot_size * 2 // 3), remaining_chips // 5)
                    return PokerAction.RAISE, raise_amount
                else:
                    # Call or raise depending on pot odds
                    if pot_odds >= 2:  # Good pot odds
                        return PokerAction.CALL, 0
                    elif call_amount <= remaining_chips // 4:
                        raise_amount = min(max(round_state.min_raise, call_amount * 2), remaining_chips // 3)
                        return PokerAction.RAISE, raise_amount
                    else:
                        return PokerAction.CALL, 0
            elif hand_strength >= 0.65:  # Strong hands (two pair, trips)
                if current_bet == 0:
                    raise_amount = min(max(round_state.min_raise, pot_size // 2), remaining_chips // 8)
                    return PokerAction.RAISE, raise_amount
                else:
                    if pot_odds >= 3 or call_amount <= remaining_chips // 8:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
            elif hand_strength >= 0.55:  # Medium hands (pair)
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                elif pot_odds >= 4 or call_amount <= remaining_chips // 15:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:  # Weak hands
                if current_bet == 0:
                    return PokerAction.CHECK, 0
                elif pot_odds >= 6 and call_amount <= remaining_chips // 20:
                    return PokerAction.CALL, 0  # Bluff catcher with good odds
                else:
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)