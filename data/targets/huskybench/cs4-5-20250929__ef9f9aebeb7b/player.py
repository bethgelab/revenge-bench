from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
from collections import Counter

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.starting_chips = 0
        self.blind_amount = 0
        self.my_hands = []
        self.is_big_blind = False
        
    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.starting_chips = starting_chips
        self.my_hands = player_hands
        self.blind_amount = blind_amount
        self.is_big_blind = (self.id == big_blind_player_id)
        
    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass
        
    def card_rank(self, card: str) -> int:
        """Convert card rank to numerical value (2-14, where 14 is Ace)"""
        rank = card[:-1]
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
    
    def evaluate_preflop_equity(self, cards: List[str]) -> float:
        """Evaluate preflop hand equity against a random hand."""
        if len(cards) != 2:
            return 0.0
            
        rank1 = self.card_rank(cards[0])
        rank2 = self.card_rank(cards[1])
        suit1 = cards[0][-1]
        suit2 = cards[1][-1]
        
        high_card = max(rank1, rank2)
        low_card = min(rank1, rank2)
        is_pair = (rank1 == rank2)
        is_suited = (suit1 == suit2)
        gap = high_card - low_card
        
        equity = 0.0
        
        if is_pair:
            equity = 0.50 + (rank1 / 28.0) * 0.35
            return min(equity, 1.0)
        
        if high_card == 14:
            equity += 0.30
            if low_card >= 10:
                equity += 0.15
            elif low_card >= 7:
                equity += 0.08
            else:
                equity += 0.03
        elif high_card == 13:
            equity += 0.20
            if low_card >= 10:
                equity += 0.12
            elif low_card >= 7:
                equity += 0.05
        elif high_card == 12:
            equity += 0.15
            if low_card >= 10:
                equity += 0.10
            elif low_card >= 7:
                equity += 0.03
        elif high_card >= 10:
            equity += 0.10
            if low_card >= 8:
                equity += 0.05
        else:
            equity += 0.05
            if low_card >= 7:
                equity += 0.02
        
        if is_suited:
            equity += 0.05
        
        if gap == 0:
            equity += 0.05
        elif gap == 1:
            equity += 0.03
        elif gap == 2:
            equity += 0.01
            
        return min(equity, 1.0)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """
        ROUND 15 STRATEGY: AGGRESSIVE COUNTER-ADAPTATION
        
        Opponents clearly adapted after Round 11 and crushed us in rounds 12-14.
        New approach: Be more aggressive and less predictable.
        Play tighter preflop but more aggressive postflop.
        """
        
        call_amount = round_state.current_bet - round_state.player_bets.get(str(self.id), 0)
        can_raise = round_state.min_raise > 0 and round_state.max_raise >= round_state.min_raise
        equity = self.evaluate_preflop_equity(self.my_hands)
        our_investment = round_state.player_bets.get(str(self.id), 0)
        pot_size = round_state.pot
        
        # Preflop - play tighter, raise bigger
        if round_state.round == 1:
            if equity >= 0.75:  # Premium hands - raise big
                if can_raise:
                    raise_amount = min(round_state.max_raise, max(round_state.min_raise, self.blind_amount * 6))
                    return PokerAction.RAISE, raise_amount
                return PokerAction.CALL, 0 if call_amount > 0 else PokerAction.CHECK, 0
            
            elif equity >= 0.65:  # Strong hands - raise medium
                if can_raise:
                    raise_amount = min(round_state.max_raise, max(round_state.min_raise, self.blind_amount * 3))
                    return PokerAction.RAISE, raise_amount
                return PokerAction.CALL, 0 if call_amount > 0 else PokerAction.CHECK, 0
            
            elif equity >= 0.50:  # Decent hands - call small bets
                if call_amount == 0:
                    return PokerAction.CHECK, 0
                elif call_amount <= self.blind_amount * 5:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            
            else:  # Weak hands - fold to any bet
                if call_amount == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.FOLD, 0
        
        # Postflop - be more aggressive
        else:
            if equity >= 0.55:  # Strong - always aggressive
                if call_amount == 0:
                    if can_raise:
                        bet_size = max(round_state.min_raise, pot_size // 2)
                        raise_amount = min(bet_size, round_state.max_raise)
                        return PokerAction.RAISE, raise_amount
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.CALL, 0
            
            elif equity >= 0.45:  # Decent - call or raise
                if call_amount == 0:
                    if can_raise and equity >= 0.50:
                        bet_size = max(round_state.min_raise, pot_size // 3)
                        raise_amount = min(bet_size, round_state.max_raise)
                        return PokerAction.RAISE, raise_amount
                    return PokerAction.CHECK, 0
                else:
                    if call_amount <= pot_size:
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
            
            elif equity >= 0.35:  # Marginal - check/call small
                if call_amount == 0:
                    return PokerAction.CHECK, 0
                elif call_amount <= self.blind_amount * 2 or our_investment >= self.blind_amount * 10:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            
            else:  # Weak - check/fold
                if call_amount == 0:
                    return PokerAction.CHECK, 0
                elif our_investment >= self.blind_amount * 15:
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass