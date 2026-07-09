from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
from collections import Counter

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.my_hand = []
        
    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        self.my_hand = player_hands
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def card_rank(self, card: str) -> int:
        """Convert card rank to numeric value (2-14, where 14 is Ace)"""
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
    
    def card_suit(self, card: str) -> str:
        """Get card suit"""
        return card[1]
    
    def evaluate_poker_hand(self, hole_cards: List[str], community_cards: List[str]) -> Tuple[int, List[int]]:
        """
        Evaluate poker hand strength using standard poker hand rankings.
        Returns (hand_rank, kickers) where:
        - hand_rank: 0=high card, 1=pair, 2=two pair, 3=trips, 4=straight, 5=flush, 
                     6=full house, 7=quads, 8=straight flush
        - kickers: list of card ranks in descending order for tie-breaking
        """
        all_cards = hole_cards + community_cards
        if len(all_cards) < 2:
            # Pre-flop or invalid state
            ranks = sorted([self.card_rank(c) for c in hole_cards], reverse=True)
            return (0, ranks)
        
        ranks = [self.card_rank(c) for c in all_cards]
        suits = [self.card_suit(c) for c in all_cards]
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        
        # Sort ranks by frequency, then by rank value
        sorted_ranks = sorted(rank_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
        
        # Check for flush
        is_flush = max(suit_counts.values()) >= 5
        flush_suit = None
        if is_flush:
            flush_suit = max(suit_counts, key=suit_counts.get)
            flush_ranks = sorted([self.card_rank(c) for c in all_cards if self.card_suit(c) == flush_suit], reverse=True)
        
        # Check for straight
        unique_ranks = sorted(set(ranks), reverse=True)
        is_straight = False
        straight_high = 0
        
        # Check for regular straight
        for i in range(len(unique_ranks) - 4):
            if unique_ranks[i] - unique_ranks[i+4] == 4:
                is_straight = True
                straight_high = unique_ranks[i]
                break
        
        # Check for wheel (A-2-3-4-5)
        if not is_straight and 14 in unique_ranks and 2 in unique_ranks and 3 in unique_ranks and 4 in unique_ranks and 5 in unique_ranks:
            is_straight = True
            straight_high = 5  # In a wheel, 5 is the high card
        
        # Check for straight flush
        if is_flush and is_straight:
            # Need to verify the straight is in the flush suit
            flush_ranks_set = set([self.card_rank(c) for c in all_cards if self.card_suit(c) == flush_suit])
            sf_high = 0
            for i in range(len(unique_ranks) - 4):
                if all(r in flush_ranks_set for r in range(unique_ranks[i] - 4, unique_ranks[i] + 1)):
                    sf_high = unique_ranks[i]
                    break
            if 14 in flush_ranks_set and all(r in flush_ranks_set for r in [2, 3, 4, 5]):
                sf_high = 5
            if sf_high > 0:
                return (8, [sf_high])
        
        # Four of a kind
        if sorted_ranks[0][1] == 4:
            quad_rank = sorted_ranks[0][0]
            kicker = max([r for r in ranks if r != quad_rank])
            return (7, [quad_rank, kicker])
        
        # Full house
        if sorted_ranks[0][1] == 3 and sorted_ranks[1][1] >= 2:
            trips_rank = sorted_ranks[0][0]
            pair_rank = sorted_ranks[1][0]
            return (6, [trips_rank, pair_rank])
        
        # Flush
        if is_flush:
            return (5, flush_ranks[:5])
        
        # Straight
        if is_straight:
            return (4, [straight_high])
        
        # Three of a kind
        if sorted_ranks[0][1] == 3:
            trips_rank = sorted_ranks[0][0]
            kickers = sorted([r for r in ranks if r != trips_rank], reverse=True)[:2]
            return (3, [trips_rank] + kickers)
        
        # Two pair
        if sorted_ranks[0][1] == 2 and sorted_ranks[1][1] == 2:
            pair1 = sorted_ranks[0][0]
            pair2 = sorted_ranks[1][0]
            kicker = max([r for r in ranks if r != pair1 and r != pair2])
            return (2, [max(pair1, pair2), min(pair1, pair2), kicker])
        
        # One pair
        if sorted_ranks[0][1] == 2:
            pair_rank = sorted_ranks[0][0]
            kickers = sorted([r for r in ranks if r != pair_rank], reverse=True)[:3]
            return (1, [pair_rank] + kickers)
        
        # High card
        kickers = sorted(ranks, reverse=True)[:5]
        return (0, kickers)
    
    def evaluate_hand_strength(self, round_state: RoundStateClient) -> float:
        """
        Evaluate hand strength on a 0-1 scale.
        Pre-flop: Based on hole cards only
        Post-flop: Based on actual poker hand rank
        """
        hole_cards = self.my_hand
        community_cards = round_state.community_cards if round_state.community_cards else []
        
        hand_rank, kickers = self.evaluate_poker_hand(hole_cards, community_cards)
        
        # Pre-flop evaluation - use round field to determine
        is_preflop = (round_state.round == 'Preflop' or len(community_cards) == 0)
        
        if is_preflop:
            rank1 = self.card_rank(hole_cards[0])
            rank2 = self.card_rank(hole_cards[1])
            suit1 = self.card_suit(hole_cards[0])
            suit2 = self.card_suit(hole_cards[1])
            
            high_rank = max(rank1, rank2)
            low_rank = min(rank1, rank2)
            is_suited = suit1 == suit2
            is_pair = rank1 == rank2
            
            # In heads-up, ANY two cards are playable - start higher
            # Base strength on high card (very generous)
            strength = 0.40 + (high_rank / 14.0) * 0.35  # Range: 0.45-0.75
            
            # Huge boost for pairs
            if is_pair:
                strength = 0.70 + (high_rank / 14.0) * 0.30  # Range: 0.75-1.0
            
            # Boost for any face card or ten
            if high_rank >= 10:
                strength += 0.12
            
            # Boost for suited (flush potential)
            if is_suited:
                strength += 0.10
            
            # Boost for connected cards (straight potential)
            gap = abs(rank1 - rank2)
            if gap == 0:  # Pair already handled above
                pass
            elif gap <= 1:
                strength += 0.10
            elif gap == 2:
                strength += 0.07
            elif gap == 3:
                strength += 0.04
            
            # Boost for broadway cards (both cards T+)
            if low_rank >= 10:
                strength += 0.12
            
            # Boost for ace-high
            if high_rank == 14:
                strength += 0.08
            
            return min(strength, 1.0)
        
        # Post-flop evaluation based on actual hand rank
        # Map hand ranks to strength values
        base_strengths = {
            0: 0.25,  # High card - still playable in heads-up
            1: 0.50,  # One pair - decent hand
            2: 0.70,  # Two pair - strong
            3: 0.80,  # Three of a kind - very strong
            4: 0.88,  # Straight
            5: 0.91,  # Flush
            6: 0.95,  # Full house
            7: 0.98,  # Four of a kind
            8: 0.99,  # Straight flush
        }
        
        strength = base_strengths[hand_rank]
        
        # Adjust based on kicker strength for hands where kickers matter
        if hand_rank <= 3 and kickers:  # High card, pair, two pair, trips
            # Normalize top kicker to add up to 0.15 bonus
            kicker_bonus = (kickers[0] / 14.0) * 0.15
            strength += kicker_bonus
        
        return min(strength, 1.0)

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        
        hand_strength = self.evaluate_hand_strength(round_state)
        # Use round field to determine if pre-flop
        is_preflop = (round_state.round == 'Preflop')
        
        print(f"Hand strength: {hand_strength:.3f}, Pre-flop: {is_preflop}, Round: {round_state.round}")
        
        # In heads-up poker, be very aggressive
        # If no one has bet, we should often bet
        if round_state.current_bet == 0:
            if hand_strength > 0.25:  # Even lower threshold for betting
                # Bet with most hands
                bet_size = min(int(round_state.pot * 0.6) + round_state.min_raise, remaining_chips)
                if bet_size >= round_state.min_raise:
                    return PokerAction.RAISE, bet_size
            return PokerAction.CHECK, 0
        
        # Someone has bet - decide whether to call, raise, or fold
        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet) if round_state.pot > 0 else 1.0
        
        # Very strong hands - raise
        if hand_strength > 0.85:
            raise_amount = min(round_state.current_bet * 2, remaining_chips)
            if raise_amount >= round_state.min_raise:
                return PokerAction.RAISE, raise_amount
            return PokerAction.CALL, 0
        
        # Strong hands - raise
        if hand_strength > 0.75:
            raise_amount = min(int(round_state.current_bet * 1.5), remaining_chips)
            if raise_amount >= round_state.min_raise:
                return PokerAction.RAISE, raise_amount
            return PokerAction.CALL, 0
        
        # Good hands - call
        if hand_strength > 0.55:
            return PokerAction.CALL, 0
        
        # Pre-flop: be much more willing to call
        # In heads-up, you should defend your blinds aggressively
        if is_preflop:
            # Call with almost any hand pre-flop (only fold the worst ~20%)
            if hand_strength > 0.30:
                return PokerAction.CALL, 0
            # Even with weak hands, call if pot odds are good
            if pot_odds < 0.4:
                return PokerAction.CALL, 0
        else:
            # Post-flop: be more selective but still aggressive
            if hand_strength > 0.35:
                return PokerAction.CALL, 0
            # Call with marginal hands if pot odds are very good
            if hand_strength > 0.25 and pot_odds < 0.3:
                return PokerAction.CALL, 0
        
        # Weak hands - fold
        return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)