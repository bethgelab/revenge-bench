from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards = []  # Store the player's hole cards

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        
        # Store the player's hole cards
        self.hole_cards = player_hands

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def evaluate_hand_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """Evaluate the strength of the hand based on hole cards and community cards."""
        # This is a simplified hand evaluation
        # In a real implementation, you'd want a more sophisticated hand evaluator
        
        # Extract ranks and suits
        all_cards = hole_cards + community_cards
        ranks = []
        suits = []
        
        for card in all_cards:
            rank = card[:-1]  # All characters except the last one (suit)
            suit = card[-1]   # Last character is the suit
            
            # Convert rank to numerical value
            if rank == 'A':
                rank_val = 14
            elif rank == 'K':
                rank_val = 13
            elif rank == 'Q':
                rank_val = 12
            elif rank == 'J':
                rank_val = 11
            elif rank == 'T':
                rank_val = 10
            else:
                rank_val = int(rank)
                
            ranks.append(rank_val)
            suits.append(suit)
        
        # Count pairs, trips, etc.
        rank_counts = {}
        for rank in ranks:
            rank_counts[rank] = rank_counts.get(rank, 0) + 1
        
        # Check for pairs, trips, quads
        pairs = 0
        trips = 0
        quads = 0
        for count in rank_counts.values():
            if count == 2:
                pairs += 1
            elif count == 3:
                trips += 1
            elif count == 4:
                quads += 1
        
        # Check for flush
        suit_counts = {}
        for suit in suits:
            suit_counts[suit] = suit_counts.get(suit, 0) + 1
        flush = any(count >= 5 for count in suit_counts.values())
        
        # Check for straight
        unique_ranks = sorted(set(ranks))
        straight = False
        if len(unique_ranks) >= 5:
            # Check for regular straight
            for i in range(len(unique_ranks) - 4):
                if unique_ranks[i+4] - unique_ranks[i] == 4:
                    straight = True
                    break
            # Check for low straight (A-2-3-4-5)
            if 14 in unique_ranks and 2 in unique_ranks and 3 in unique_ranks and 4 in unique_ranks and 5 in unique_ranks:
                straight = True
        
        # Calculate strength based on hand combinations
        strength = 0.0
        
        # High card
        if len(ranks) > 0:
            strength = max(ranks) / 14.0  # Normalize to 0-1
        
        # Pairs
        if pairs >= 1:
            strength = 0.3 + (max(rank_counts.keys()) / 14.0) * 0.1
        if pairs >= 2:
            strength = 0.4 + (max(rank_counts.keys()) / 14.0) * 0.1
        
        # Trips
        if trips >= 1:
            strength = 0.5 + (max(rank_counts.keys()) / 14.0) * 0.1
        
        # Straight
        if straight:
            strength = 0.6 + (max(ranks) / 14.0) * 0.1
        
        # Flush
        if flush:
            strength = 0.7 + (max(ranks) / 14.0) * 0.1
        
        # Full house
        if trips >= 1 and pairs >= 1:
            strength = 0.8 + (max(rank_counts.keys()) / 14.0) * 0.1
        
        # Quads
        if quads >= 1:
            strength = 0.9 + (max(rank_counts.keys()) / 14.0) * 0.1
        
        # Straight flush
        if straight and flush:
            strength = 0.95 + (max(ranks) / 14.0) * 0.05
        
        return min(strength, 1.0)  # Cap at 1.0

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        
        # Use the stored hole cards to evaluate hand strength
        hand_strength = self.evaluate_hand_strength(self.hole_cards, round_state.community_cards)
        
        # Basic strategy based on hand strength
        pot_size = round_state.pot
        current_bet = round_state.current_bet
        min_raise = round_state.min_raise
        max_raise = round_state.max_raise
        
        # Determine action based on game state and hand strength
        if current_bet == 0:
            # No bet to call, we can check or bet
            if hand_strength > 0.6:
                # Strong hand, make a bet
                bet_amount = min(pot_size // 2, remaining_chips, max_raise)
                if bet_amount > 0:
                    return PokerAction.RAISE, bet_amount
                else:
                    return PokerAction.CHECK, 0
            else:
                # Weak hand, just check
                return PokerAction.CHECK, 0
        else:
            # There's a bet to call
            pot_odds = current_bet / (pot_size + current_bet)
            
            if hand_strength > pot_odds + 0.2:  # Add buffer for position/reads
                # Hand is strong enough to call or raise
                if hand_strength > 0.8 and remaining_chips > current_bet * 2:
                    # Very strong hand, raise
                    raise_amount = min(current_bet * 2, remaining_chips, max_raise)
                    return PokerAction.RAISE, raise_amount
                else:
                    # Just call
                    return PokerAction.CALL, 0
            else:
                # Hand is not strong enough, fold
                return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)