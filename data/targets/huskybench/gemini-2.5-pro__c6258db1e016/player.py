import random
from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = []
        self.big_blind = 10 # Default value

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        self.hand = player_hands
        self.big_blind = blind_amount

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        pass

    def _get_hand_strength(self, hand: List[str], community_cards: List[str]) -> int:
        # 10: Straight flush, 9: Quads, 8: Full House, 7: Flush, 6: Straight, 
        # 5: Three of a kind, 4: Two pair, 3: One pair, 1: High card
        
        all_cards = hand + community_cards
        if len(all_cards) < 5:
            ranks = [card[:-1] for card in hand]
            if ranks[0] == ranks[1]: return 3 # Pocket pair
            return 1

        rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        ranks = [card[:-1] for card in all_cards]
        suits = [card[-1] for card in all_cards]
        
        rank_counts = {rank: ranks.count(rank) for rank in set(ranks)}
        counts = list(rank_counts.values())
        
        is_flush = False
        suit_counts = {suit: suits.count(suit) for suit in set(suits)}
        if any(c >= 5 for c in suit_counts.values()):
            is_flush = True

        is_straight = False
        unique_rank_values = sorted(list(set([rank_values.get(r, 0) for r in ranks])))
        if len(unique_rank_values) >= 5:
            for i in range(len(unique_rank_values) - 4):
                if unique_rank_values[i+4] - unique_rank_values[i] == 4:
                    is_straight = True
                    break
        if not is_straight and all(x in unique_rank_values for x in [14, 2, 3, 4, 5]):
            is_straight = True

        if is_straight and is_flush: return 10
        if 4 in counts: return 9
        if (3 in counts and 2 in counts) or counts.count(3) > 1: return 8
        if is_flush: return 7
        if is_straight: return 6
        if 3 in counts: return 5
        
        pairs = counts.count(2)
        if pairs >= 2: return 4
        if pairs == 1: return 3
            
        return 1

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        if not self.hand or self.id is None:
            return PokerAction.CHECK, 0

        amount_to_call = round_state.current_bet - round_state.player_bets.get(self.id, 0)

        # --- Pre-flop Strategy: Counter opponent's "always raise" ---
        if not round_state.community_cards:
            if amount_to_call > 0:
                return PokerAction.CALL, amount_to_call
            else:
                return PokerAction.CHECK, 0

        # --- Post-flop Strategy: Exploit "always check" opponent ---
        # On the flop, if no one has bet, make a minimum bet to take the pot.
        if len(round_state.community_cards) == 3:
            if amount_to_call == 0:
                # Bet the minimum amount (big blind)
                return PokerAction.RAISE, min(self.big_blind, remaining_chips)
            else:
                # This case shouldn't be reached if opponent always checks, but fold just in case.
                return PokerAction.FOLD, 0

        # If we somehow get to the turn or river, just check/fold.
        if len(round_state.community_cards) > 3:
            if amount_to_call > 0:
                return PokerAction.FOLD, 0
            else:
                return PokerAction.CHECK, 0
        
        # Fallback for any unexpected state on the flop if we face a bet
        if amount_to_call > 0:
            return PokerAction.FOLD, 0
        else:
            return PokerAction.CHECK, 0