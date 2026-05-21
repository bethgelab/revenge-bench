from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
import eval7

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_hand = []
        self.opponent_aggression = 0
        self.games_played = 0
        
    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        """Called when the game starts."""
        self.my_hand = player_hands
        self.starting_chips = starting_chips
        self.blind_amount = blind_amount
        self.big_blind_player_id = big_blind_player_id
        self.small_blind_player_id = small_blind_player_id
        self.all_players = all_players
        self.games_played += 1

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the start of each round."""
        pass

    def evaluate_hand_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """
        Evaluate hand strength using eval7.
        Returns a value between 0 and 1, where 1 is the best possible hand.
        """
        try:
            # Convert card strings to eval7 Card objects
            hand = [eval7.Card(card) for card in hole_cards]
            board = [eval7.Card(card) for card in community_cards] if community_cards else []
            
            # Combine hand and board
            all_cards = hand + board
            
            # Evaluate the hand
            hand_value = eval7.evaluate(all_cards)
            
            # Normalize to 0-1 range (lower eval7 scores are better)
            # eval7 scores range from 1 (royal flush) to 7462 (high card 7-5-4-3-2)
            normalized_strength = 1.0 - (hand_value / 7462.0)
            
            return normalized_strength
        except Exception as e:
            # Fallback to simple high card evaluation if eval7 fails
            return self.simple_hand_strength(hole_cards)
    
    def simple_hand_strength(self, hole_cards: List[str]) -> float:
        """Simple fallback hand evaluation based on high cards and pairs."""
        ranks = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                 '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        card_ranks = [ranks[card[0]] for card in hole_cards]
        card_suits = [card[1] for card in hole_cards]
        
        # Check for pair
        if card_ranks[0] == card_ranks[1]:
            return 0.5 + (card_ranks[0] / 28.0)  # Pairs are decent
        
        # Check for suited cards
        suited_bonus = 0.05 if card_suits[0] == card_suits[1] else 0
        
        # High card strength
        high_card = max(card_ranks)
        low_card = min(card_ranks)
        
        # Connected cards bonus
        connected_bonus = 0.05 if abs(card_ranks[0] - card_ranks[1]) <= 2 else 0
        
        base_strength = (high_card + low_card * 0.5) / 28.0
        return min(base_strength + suited_bonus + connected_bonus, 0.95)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """Returns the action for the player."""
        
        # Evaluate current hand strength
        hand_strength = self.evaluate_hand_strength(self.my_hand, round_state.community_cards)
        
        # Get pot odds
        pot = round_state.pot
        current_bet = round_state.current_bet
        my_bet = round_state.player_bets.get(str(self.id), 0)
        amount_to_call = current_bet - my_bet
        
        # CRITICAL FIX: Never fold when we can check for free!
        if amount_to_call <= 0:
            amount_to_call = 0
        
        # Calculate pot odds if we need to call
        pot_odds = amount_to_call / (pot + amount_to_call) if amount_to_call > 0 else 0
        
        # Determine if opponent has raised
        opponent_raised = False
        for player_id, action in round_state.player_actions.items():
            if int(player_id) != self.id and action == "RAISE":
                opponent_raised = True
                break
        
        # Decision logic based on hand strength and situation
        
        # Preflop strategy
        if round_state.round_num == 0:
            if hand_strength > 0.7:  # Strong hand
                if not opponent_raised:
                    # Raise with strong hands
                    raise_amount = min(round_state.max_raise, max(round_state.min_raise, pot // 2 + self.blind_amount // 2))
                    return PokerAction.RAISE, raise_amount
                else:
                    # Re-raise or call with very strong hands
                    if hand_strength > 0.85:
                        raise_amount = min(round_state.max_raise, round_state.min_raise)
                        return PokerAction.RAISE, raise_amount
                    else:
                        return PokerAction.CALL, 0
            elif hand_strength > 0.5:  # Medium hand
                if amount_to_call == 0:
                    return PokerAction.CHECK, 0
                elif amount_to_call < remaining_chips * 0.1:  # Small bet
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:  # Weak hand
                if amount_to_call == 0:
                    return PokerAction.CHECK, 0
                else:
                    return PokerAction.FOLD, 0
        
        # Post-flop strategy - CRITICAL: ALWAYS CHECK WHEN AMOUNT_TO_CALL == 0
        else:
            # WINNING STRATEGY: If we can check for free, ALWAYS CHECK (never fold!)
            if amount_to_call == 0:
                return PokerAction.CHECK, 0
            else:
                # NEW STRATEGY: Opponent now raises postflop instead of folding
                # We should CALL their raise because pot odds are favorable
                # Pot is typically 15 from preflop + 10 from opponent = 25
                # We need to call 10 to win 25, which is 2.5:1 pot odds
                # This is profitable even with weak hands
                return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the end of the round."""
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        """Called at the end of the game."""
        pass