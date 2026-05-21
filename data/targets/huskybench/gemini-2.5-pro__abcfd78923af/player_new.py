from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.big_blind = 0

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.big_blind = blind_amount
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

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        card1, card2 = self.hand[0], self.hand[1]
        rank1, suit1 = card1[:-1], card1[-1]
        rank2, suit2 = card2[:-1], card2[-1]

        ranks = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        try:
            rank1_val = int(rank1)
        except ValueError:
            rank1_val = ranks.get(rank1, 0)
        
        try:
            rank2_val = int(rank2)
        except ValueError:
            rank2_val = ranks.get(rank2, 0)

        # Pre-flop strategy
        if round_state.round_num == 1:
            # Pocket pairs
            if rank1 == rank2:
                return PokerAction.RAISE, 2 * self.big_blind

            # Suited connectors or high cards
            if suit1 == suit2 or rank1_val >= 10 or rank2_val >= 10:
                if round_state.current_bet > 0:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.CHECK, 0
            
            # Fold weak hands
            if round_state.current_bet > 3 * self.big_blind:
                return PokerAction.FOLD, 0
            else:
                return PokerAction.CHECK, 0

        # Post-flop strategy (simple for now)
        if round_state.current_bet > 0:
            return PokerAction.CALL, 0
        else:
            return PokerAction.CHECK, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)