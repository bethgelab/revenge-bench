from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
import eval7

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_hand = []
        
    def evaluate_hand_strength(self, cards: List[str]) -> float:
        """
        Evaluate preflop hand strength (0-1 scale)
        Higher is better
        """
        if len(cards) != 2:
            return 0.5
        
        # Parse cards
        ranks = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                 '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        rank1 = ranks.get(cards[0][0], 0)
        rank2 = ranks.get(cards[1][0], 0)
        suit1 = cards[0][1] if len(cards[0]) > 1 else ''
        suit2 = cards[1][1] if len(cards[1]) > 1 else ''
        
        high = max(rank1, rank2)
        low = min(rank1, rank2)
        
        # Pocket pairs are strong
        if rank1 == rank2:
            return 0.6 + (rank1 / 14) * 0.4  # 0.6-1.0 for pairs
        
        # High cards
        high_card_value = (high / 14) * 0.4
        
        # Suited bonus
        suited_bonus = 0.1 if suit1 == suit2 else 0
        
        # Connected cards bonus (for straight potential)
        gap = abs(rank1 - rank2)
        connected_bonus = 0.05 if gap <= 2 else 0
        
        # Face cards bonus
        face_bonus = 0.1 if high >= 11 else 0
        
        return min(1.0, high_card_value + suited_bonus + connected_bonus + face_bonus)
    
    def evaluate_postflop_hand(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """
        Evaluate hand strength with community cards using eval7
        Returns a value between 0 and 1 (normalized)
        """
        if not community_cards:
            return self.evaluate_hand_strength(hole_cards)
        
        try:
            # Convert cards to eval7 format
            all_cards = hole_cards + community_cards
            eval7_cards = [eval7.Card(card) for card in all_cards]
            
            # Evaluate hand (lower is better in eval7, range is 1-7462)
            hand_value = eval7.evaluate(eval7_cards)
            
            # Normalize to 0-1 scale where 1 is best
            # eval7: 1 = best (royal flush), 7462 = worst (7-high)
            normalized = (7462 - hand_value) / 7461.0
            
            return max(0.0, min(1.0, normalized))
        except Exception as e:
            print(f"Error evaluating hand: {e}")
            return self.evaluate_hand_strength(hole_cards)

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, 
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.my_hand = player_hands

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        
        # Evaluate hand strength based on round
        if round_state.round_num == 0:  # Preflop
            hand_strength = self.evaluate_hand_strength(self.my_hand)
        else:  # Post-flop
            hand_strength = self.evaluate_postflop_hand(self.my_hand, round_state.community_cards)
        
        # ROUND 15 STRATEGY - OPTIMIZED WINNING APPROACH
        # Round 14 results: 61.0% win rate, +2.15 avg score (BEST EVER!)
        # - Strategy is working excellently
        # - CHECK 59.7%, RAISE 40.3%, FOLD 0.0%
        # - Opponent never folds, so value betting is profitable
        # 
        # Key opponent patterns (consistent):
        # - Opponent NEVER folds (0.0%)
        # - Opponent NEVER calls (0.0%)
        # - Opponent raises ~48% of the time, checks ~52%
        # - Cannot be bluffed, pays off our value bets
        # 
        # Round 15 optimization:
        # 1. Keep the winning strategy mostly intact
        # 2. Slightly more aggressive with premium hands (opponent never folds)
        # 3. Extract more value from very strong hands
        # 4. Maintain pot control with medium hands
        
        # Preflop strategy
        if round_state.round_num == 0:
            if hand_strength >= 0.75:  # Premium hands (top 12%)
                if round_state.current_bet == 0:
                    # Raise bigger with premium hands (opponent never folds)
                    return PokerAction.RAISE, min(120, remaining_chips)
                else:
                    # Re-raise aggressively with premium hands
                    raise_amount = min(round_state.current_bet * 3.0, remaining_chips)
                    if raise_amount >= round_state.min_raise:
                        return PokerAction.RAISE, raise_amount
                    return PokerAction.CALL, 0
            
            elif hand_strength >= 0.55:  # Good hands (top 40%)
                if round_state.current_bet == 0:
                    # Raise with good hands
                    return PokerAction.RAISE, min(80, remaining_chips)
                else:
                    # Call their raises with good hands
                    return PokerAction.CALL, 0
            
            elif hand_strength >= 0.40:  # Medium hands
                if round_state.current_bet == 0:
                    # Check with medium hands
                    return PokerAction.CHECK, 0
                else:
                    # Call small raises, fold to larger ones
                    if round_state.current_bet > 10:
                        return PokerAction.FOLD, 0
                    return PokerAction.CALL, 0
            
            elif hand_strength >= 0.30:  # Medium-weak hands
                if round_state.current_bet == 0:
                    # Check with medium-weak hands
                    return PokerAction.CHECK, 0
                else:
                    # Fold to any raise with medium-weak hands
                    if round_state.current_bet > 5:
                        return PokerAction.FOLD, 0
                    return PokerAction.CALL, 0
            
            else:  # Weak hands (< 0.30)
                if round_state.current_bet == 0:
                    # Check with weak hands
                    return PokerAction.CHECK, 0
                else:
                    # Always fold weak hands to any raise
                    return PokerAction.FOLD, 0
        
        # Post-flop strategy
        else:
            if hand_strength >= 0.75:  # Very strong hands
                if round_state.current_bet == 0:
                    # Bet bigger for value (opponent never folds)
                    bet_size = min(int(round_state.pot * 0.8), remaining_chips)
                    if bet_size >= round_state.min_raise:
                        return PokerAction.RAISE, bet_size
                    return PokerAction.CHECK, 0
                else:
                    # Re-raise aggressively with very strong hands
                    raise_amount = min(round_state.current_bet * 2.5, remaining_chips)
                    if raise_amount >= round_state.min_raise:
                        return PokerAction.RAISE, raise_amount
                    return PokerAction.CALL, 0
            
            elif hand_strength >= 0.60:  # Good hands
                if round_state.current_bet == 0:
                    # Bet medium for value
                    bet_size = min(int(round_state.pot * 0.6), remaining_chips)
                    if bet_size >= round_state.min_raise:
                        return PokerAction.RAISE, bet_size
                    return PokerAction.CHECK, 0
                else:
                    # Call with good hands - opponent often bluffs
                    return PokerAction.CALL, 0
            
            elif hand_strength >= 0.45:  # Medium-good hands
                if round_state.current_bet == 0:
                    # Check with medium hands
                    return PokerAction.CHECK, 0
                else:
                    # Call small bets, fold to larger bets
                    if round_state.current_bet > 15:
                        return PokerAction.FOLD, 0
                    return PokerAction.CALL, 0
            
            elif hand_strength >= 0.35:  # Medium-weak hands
                if round_state.current_bet == 0:
                    # Check with medium-weak hands
                    return PokerAction.CHECK, 0
                else:
                    # Fold to any significant bet
                    if round_state.current_bet > 10:
                        return PokerAction.FOLD, 0
                    return PokerAction.CALL, 0
            
            else:  # Weak hands (< 0.35)
                if round_state.current_bet == 0:
                    # Check with weak hands
                    return PokerAction.CHECK, 0
                else:
                    # Always fold weak hands to any bet
                    return PokerAction.FOLD, 0
        
        # Default: check if possible, otherwise call
        if round_state.current_bet == 0:
            return PokerAction.CHECK, 0
        return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass