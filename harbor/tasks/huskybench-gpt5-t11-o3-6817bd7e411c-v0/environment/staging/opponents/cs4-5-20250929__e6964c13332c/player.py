from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    """
    Round 12 Strategy - Fixed and simplified
    
    Opponent pattern (unchanged for 11 rounds):
    - 100% raise preflop
    - 100% check postflop (NEVER bets or raises)
    
    Our strategy:
    - Preflop: Fold truly weak hands (bottom ~30%), play the rest
    - Postflop: Check it down (we can't bet due to game constraints)
    - Win by having better starting hand selection
    """
    def __init__(self):
        super().__init__()
        self.hand = []
        self.starting_chips = 0
        self.blind_amount = 0
        
    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, 
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.starting_chips = starting_chips
        self.blind_amount = blind_amount
        self.hand = player_hands
        
    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def _card_rank(self, card: str) -> int:
        """Convert card rank to numeric value."""
        rank = card[0]
        rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                    '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        return rank_map.get(rank, 0)
    
    def _should_fold_preflop(self) -> bool:
        """
        Determine if we should fold preflop.
        Fold the weakest ~30% of hands.
        """
        if len(self.hand) != 2:
            return False
        
        card1, card2 = self.hand
        rank1 = self._card_rank(card1)
        rank2 = self._card_rank(card2)
        suit1 = card1[1] if len(card1) > 1 else ''
        suit2 = card2[1] if len(card2) > 1 else ''
        
        high_rank = max(rank1, rank2)
        low_rank = min(rank1, rank2)
        is_pair = (rank1 == rank2)
        is_suited = (suit1 == suit2)
        gap = high_rank - low_rank
        
        # Never fold pairs
        if is_pair:
            return False
        
        # Never fold high cards (J or better)
        if high_rank >= 11:
            return False
        
        # Never fold suited aces
        if high_rank == 14 and is_suited:
            return False
        
        # Fold weak offsuit hands with big gaps
        # Examples: 72o, 83o, 94o, T5o, etc.
        if not is_suited:
            # Fold if high card is 9 or lower and gap is 4+
            if high_rank <= 9 and gap >= 4:
                return True
            # Fold if high card is T or lower and gap is 5+
            if high_rank <= 10 and gap >= 5:
                return True
            # Fold really weak hands like 72, 73, 82, 83, 84
            if high_rank <= 8 and low_rank <= 4:
                return True
        
        # Fold weak suited hands with huge gaps
        if is_suited:
            # Fold if high card is 8 or lower and gap is 5+
            if high_rank <= 8 and gap >= 5:
                return True
        
        return False

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """
        Returns the action for the player.
        """
        
        # Preflop strategy (Round 0)
        if round_state.round_num == 0:
            if self._should_fold_preflop():
                # Fold weak hands preflop
                if round_state.current_bet > 0:
                    return PokerAction.FOLD, 0
                else:
                    return PokerAction.CHECK, 0
            
            # Play all other hands
            if round_state.current_bet == 0:
                # We're first to act, raise
                raise_amount = min(self.blind_amount * 2, round_state.max_raise)
                if raise_amount >= round_state.min_raise:
                    return PokerAction.RAISE, raise_amount
                else:
                    return PokerAction.CHECK, 0
            else:
                # Opponent raised, call
                return PokerAction.CALL, 0
        
        # Post-flop strategy (Round 1+)
        else:
            # Simple strategy: just check it down
            # We can't bet anyway due to game constraints (max_raise = 0)
            if round_state.current_bet == 0:
                return PokerAction.CHECK, 0
            else:
                # Opponent bet (shouldn't happen based on their pattern)
                # Call if we have anything decent
                return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the end of the round."""
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, 
                    all_scores: dict, active_players_hands: dict):
        """Called at the end of the game."""
        pass