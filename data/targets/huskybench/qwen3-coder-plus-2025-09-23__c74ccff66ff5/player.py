from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction, PokerRound
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_hand = None

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        # Store our hand for later use
        self.my_hand = player_hands

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def evaluate_hand_strength(self, player_hands: List[str]) -> float:
        """Evaluate the strength of the player's hand based on basic poker principles."""
        if len(player_hands) < 2:
            return 0.0

        card1, card2 = player_hands[0], player_hands[1]
        
        # Extract ranks and suits
        rank1, suit1 = card1[:-1], card1[-1]
        rank2, suit2 = card2[:-1], card2[-1]
        
        # Convert ranks to numerical values for comparison
        rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        rank1_val = rank_values[rank1]
        rank2_val = rank_values[rank2]
        
        # Calculate hand strength
        strength = 0.0
        
        # Check for pocket pair
        if rank1 == rank2:
            strength += 3.0  # Pocket pairs are strong
            # Higher pairs get more strength
            strength += rank1_val / 10.0
        else:
            # Add strength for high cards
            strength += max(rank1_val, rank2_val) / 10.0
            
            # Check for suited cards
            if suit1 == suit2:
                strength += 1.0  # Suited cards have potential
            
            # Check for connected cards
            if abs(rank1_val - rank2_val) == 1:
                strength += 0.5  # Connected cards have potential
            elif abs(rank1_val - rank2_val) == 2:
                strength += 0.3  # One-gappers have some potential
        
        # Bonus for high card combinations
        if rank1_val >= 10 and rank2_val >= 10:  # Both cards are T or higher
            strength += 1.0
        
        return strength

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        print("Current round:", round_state.round)
        print("Current bet:", round_state.current_bet)
        print("Pot:", round_state.pot)

        # First, check if we have our hand stored
        if self.my_hand is None:
            # Fallback if we don't have our hand
            if round_state.current_bet == 0:
                return PokerAction.CHECK, 0
            else:
                return PokerAction.CALL, 0

        # Evaluate our hand strength
        hand_strength = self.evaluate_hand_strength(self.my_hand)
        print("Hand strength:", hand_strength)

        # Preflop strategy
        if round_state.round == "preflop":
            if round_state.current_bet == 0:
                # If no one has bet yet, decide based on hand strength
                if hand_strength >= 4.0:  # Strong hands (pocket pairs, high cards)
                    return PokerAction.RAISE, min(100, remaining_chips)  # Raise with strong hands
                elif hand_strength >= 2.5:  # Medium strength hands
                    return PokerAction.CHECK, 0  # Check or call
                else:  # Weak hands
                    return PokerAction.FOLD, 0  # Fold weak hands
            else:
                # Someone has already bet
                pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                
                if hand_strength >= 4.0:  # Strong hands
                    if round_state.current_bet <= remaining_chips * 0.2:  # Bet is less than 20% of our chips
                        return PokerAction.RAISE, min(round_state.current_bet * 2, remaining_chips)  # Re-raise
                    else:
                        return PokerAction.CALL, 0  # Call with strong hands
                elif hand_strength >= 2.5 and pot_odds < 0.25:  # Medium strength with good pot odds
                    return PokerAction.CALL, 0
                else:  # Weak hands or poor pot odds
                    return PokerAction.FOLD, 0  # Fold with weak hands and poor pot odds

        # Post-flop strategy (flop, turn, river)
        elif round_state.round in ["flop", "turn", "river"]:
            # For now, we'll implement a simple strategy based on pot odds and our initial hand strength
            if round_state.current_bet == 0:
                return PokerAction.CHECK, 0
            else:
                pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                
                # If we have a strong starting hand, we might continue with it post-flop
                if hand_strength >= 4.0:  # Strong starting hand
                    return PokerAction.CALL, 0  # Continue with strong hands
                elif hand_strength >= 2.5 and pot_odds < 0.25:  # Medium strength with good pot odds
                    return PokerAction.CALL, 0
                elif pot_odds < 0.15:  # Very good pot odds regardless of hand
                    return PokerAction.CALL, 0
                else:
                    # In situations with poor pot odds and weak starting hand, fold
                    return PokerAction.FOLD, 0

        # Default action if we don't have a specific strategy
        if round_state.current_bet == 0:
            return PokerAction.CHECK, 0
        else:
            return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)