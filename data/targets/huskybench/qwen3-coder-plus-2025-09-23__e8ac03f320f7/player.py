from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def evaluate_hand_strength(self, hand: List[str]) -> float:
        """Evaluate the strength of the player's hand."""
        if not hand or len(hand) < 2:
            return 0.0

        # Extract ranks and suits
        ranks = []
        suits = []
        for card in hand:
            rank = card[:-1]
            suit = card[-1]
            
            # Convert rank to numerical value
            if rank.isdigit():
                rank_val = int(rank)
            elif rank == 'T':
                rank_val = 10
            elif rank == 'J':
                rank_val = 11
            elif rank == 'Q':
                rank_val = 12
            elif rank == 'K':
                rank_val = 13
            elif rank == 'A':
                rank_val = 14
            else:
                rank_val = 0
            
            ranks.append(rank_val)
            suits.append(suit)

        # Sort ranks in descending order
        ranks.sort(reverse=True)

        # Check for pairs
        if ranks[0] == ranks[1]:
            # Pairs are strong
            if ranks[0] >= 10:  # High pairs (T, J, Q, K, A)
                return 0.9
            elif ranks[0] >= 7:  # Medium pairs (7-9)
                return 0.7
            else:  # Low pairs (2-6)
                return 0.5

        # Check for high cards
        if ranks[0] >= 12 and ranks[1] >= 11:  # AK, AQ, AJ, KQ
            if suits[0] == suits[1]:  # Suited
                return 0.8
            else:
                return 0.7
        elif ranks[0] >= 11 and ranks[1] >= 10:  # KJ, QJ, KT, QT
            if suits[0] == suits[1]:  # Suited
                return 0.7
            else:
                return 0.6
        elif ranks[0] >= 10 and ranks[1] >= 9:  # AT, KT, QT, JT
            if suits[0] == suits[1]:  # Suited
                return 0.6
            else:
                return 0.5

        # Check for suited connectors
        if suits[0] == suits[1] and abs(ranks[0] - ranks[1]) <= 4:  # Suited with gap <= 4
            return 0.6

        # Default for weak hands
        return 0.3

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")

        # Get our hand
        # Note: We don't have direct access to our hand in this method, so we'll use a simplified strategy
        # In a real implementation, we would need to track our hand from on_start and on_round_start
        
        # Check if there's been a raise in the current round
        raised = False
        for player_action in round_state.player_actions.values():
            if player_action == "Raise":
                raised = True
                break

        # Determine our action based on the current game state
        if round_state.current_bet == 0:
            # No bets yet, we can check or raise
            if not raised and round_state.round_num == 0:  # Preflop
                # For now, let's use a simple strategy based on hand strength
                # Since we don't have access to our hand here, we'll use a default approach
                # In a real implementation, we would evaluate our hand strength
                return PokerAction.CHECK, 0
            else:
                # Postflop, if no one has bet yet, we can check or bet
                return PokerAction.CHECK, 0
        else:
            # There's an active bet, we need to decide whether to call, raise, or fold
            if round_state.current_bet > remaining_chips * 0.5:  # If the bet is more than half our chips
                # Fold unless we have a very strong hand (which we can't evaluate without knowing our hand)
                return PokerAction.FOLD, 0
            else:
                # Call to stay in the hand
                return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)