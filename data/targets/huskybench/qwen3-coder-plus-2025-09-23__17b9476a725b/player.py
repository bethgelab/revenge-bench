from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction, PokerRound
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hole_cards = []
        self.opponent_stats = {
            'fold_to_bet': 0.0,
            'fold_to_raise': 0.0,
            'aggression_factor': 0.0,
            'call_frequency': 0.0,
            'raise_frequency': 0.0,
            'bet_when_strong': 0.0,
            'bet_when_weak': 0.0,
            'total_hands': 0,
            'folded_to_bet': 0,
            'folded_to_raise': 0,
            'faced_bets': 0,
            'faced_raises': 0,
            'opponent_calls': 0,
            'opponent_raises': 0,
            'opponent_actions': 0
        }
        self.game_history = []
        self.bluff_counter = 0
        self.bluff_frequency = 0.1  # 10% of hands
        self.previous_round_state = None

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        print("My id: ", self.id)
        # Store our hole cards
        self.hole_cards = player_hands

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)

    def evaluate_hand_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """Evaluate the strength of the hand based on hole cards and community cards."""
        # This is a simplified hand strength evaluator
        # In a real implementation, you'd want a more sophisticated evaluator
        
        # Extract ranks and suits
        all_cards = hole_cards + community_cards
        ranks = []
        suits = []
        
        for card in all_cards:
            rank = card[:-1]  # Get rank (e.g., 'A', 'K', 'Q', 'J', 'T', '9', etc.)
            suit = card[-1]   # Get suit (e.g., 'h', 'd', 'c', 's')
            
            # Convert rank to numeric value
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
        
        # Evaluate hand strength based on various factors
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
        has_flush = any(count >= 5 for count in suit_counts.values())
        
        # Check for straight
        unique_ranks = sorted(set(ranks))
        has_straight = False
        if len(unique_ranks) >= 5:
            # Check for straight
            for i in range(len(unique_ranks) - 4):
                if unique_ranks[i+4] - unique_ranks[i] == 4:
                    has_straight = True
                    break
            # Check for low straight (A-2-3-4-5)
            if 14 in unique_ranks and all(rank in unique_ranks for rank in [2, 3, 4, 5]):
                has_straight = True
        
        # Check for potential straights and flushes (draws)
        has_straight_draw = False
        has_flush_draw = False
        if len(community_cards) >= 3 and len(community_cards) < 5:
            # Check for flush draw (4 cards of same suit)
            if any(count == 4 for count in suit_counts.values()):
                has_flush_draw = True
            # Check for straight draw possibilities
            if len(unique_ranks) >= 4:
                # Check for open-ended straight draw
                for i in range(len(unique_ranks) - 3):
                    if unique_ranks[i+3] - unique_ranks[i] <= 4:
                        has_straight_draw = True
                        break
        
        # Calculate strength score
        strength = 0.0
        
        # High card strength
        if len(hole_cards) >= 2:
            hole_ranks = [ranks[i] for i in range(2)]  # First 2 are hole cards
            strength += max(hole_ranks) / 14.0  # Normalize to 0-1 range
            strength += min(hole_ranks) / 28.0  # Add smaller card value
        
        # Pair strength
        if pairs > 0:
            strength += 0.3
        if pairs > 1:  # Two pair
            strength += 0.2
        if trips > 0:
            strength += 0.5
        if quads > 0:
            strength += 0.8
        
        # Straight and flush strength
        if has_straight:
            strength += 0.6
        if has_flush:
            strength += 0.6
        
        # Draw strength (potential for improvement)
        if has_straight_draw:
            strength += 0.15
        if has_flush_draw:
            strength += 0.15
        
        # Cap the strength at 1.0
        strength = min(strength, 1.0)
        
        return strength

    def update_opponent_stats(self, round_state: RoundStateClient):
        """Update opponent statistics based on their actions."""
        # Only update stats if we have a previous state to compare with
        if self.previous_round_state is not None:
            # Identify opponent player ID (not our ID)
            opponent_id = None
            for player_id in round_state.player_actions:
                if player_id != self.id:
                    opponent_id = player_id
                    break
            
            if opponent_id is not None:
                # Update stats based on opponent's action
                opponent_action = round_state.player_actions[opponent_id]
                
                # Update total hands
                self.opponent_stats['total_hands'] += 1
                
                # Track opponent aggression
                if opponent_action in ['BET', 'RAISE']:
                    self.opponent_stats['opponent_raises'] += 1
                    self.opponent_stats['opponent_actions'] += 1
                elif opponent_action == 'CALL':
                    self.opponent_stats['opponent_calls'] += 1
                    self.opponent_stats['opponent_actions'] += 1
                
                # Track how often opponent folds to our bets/raises
                prev_opponent_action = self.previous_round_state.player_actions.get(opponent_id)
                if prev_opponent_action == 'FOLD':
                    # Check if we bet or raised in the previous round
                    if 'Raise' in self.previous_round_state.player_actions.values() or \
                       'Bet' in self.previous_round_state.player_actions.values():
                        if any(action in ['BET', 'RAISE'] for action in self.previous_round_state.player_actions.values()):
                            # Determine if the fold was to a bet or raise
                            if 'Raise' in [v for k, v in self.previous_round_state.player_actions.items() if k != opponent_id]:
                                self.opponent_stats['folded_to_raise'] += 1
                                self.opponent_stats['faced_raises'] += 1
                            elif 'Bet' in [v for k, v in self.previous_round_state.player_actions.items() if k != opponent_id]:
                                self.opponent_stats['folded_to_bet'] += 1
                                self.opponent_stats['faced_bets'] += 1
                
                # Update frequencies
                if self.opponent_stats['faced_bets'] > 0:
                    self.opponent_stats['fold_to_bet'] = self.opponent_stats['folded_to_bet'] / self.opponent_stats['faced_bets']
                if self.opponent_stats['faced_raises'] > 0:
                    self.opponent_stats['fold_to_raise'] = self.opponent_stats['folded_to_raise'] / self.opponent_stats['faced_raises']
                if self.opponent_stats['opponent_actions'] > 0:
                    self.opponent_stats['aggression_factor'] = self.opponent_stats['opponent_raises'] / self.opponent_stats['opponent_actions']
                    self.opponent_stats['call_frequency'] = self.opponent_stats['opponent_calls'] / self.opponent_stats['opponent_actions']
                    self.opponent_stats['raise_frequency'] = self.opponent_stats['opponent_raises'] / self.opponent_stats['opponent_actions']
        
        # Store current state for next comparison
        self.previous_round_state = round_state

    def should_bluff(self, round_state: RoundStateClient, hand_strength: float) -> bool:
        """Determine if we should bluff based on game state and hand strength."""
        # Only bluff with weak hands
        if hand_strength > 0.4:
            return False
            
        # Consider opponent tendencies in bluffing decision
        fold_to_bet = self.opponent_stats['fold_to_bet']
        fold_to_raise = self.opponent_stats['fold_to_raise']
        
        # Adjust bluffing frequency based on opponent's folding tendencies
        adjusted_bluff_freq = self.bluff_frequency
        
        # If opponent folds frequently to bets, increase bluffing
        if fold_to_bet > 0.6:
            adjusted_bluff_freq *= 1.5
        elif fold_to_bet < 0.3:
            adjusted_bluff_freq *= 0.7  # Bluff less against calling stations
            
        # If opponent folds frequently to raises, increase bluff raises
        if fold_to_raise > 0.6:
            adjusted_bluff_freq *= 1.3
        elif fold_to_raise < 0.3:
            adjusted_bluff_freq *= 0.8
            
        import random
        
        # Bluff more on the river when the opponent might fold to a bet
        if round_state.round == "River":
            return random.random() < adjusted_bluff_freq * 1.5  # 15% base bluff frequency on river
            
        # Bluff on turn if the opponent folds frequently
        elif round_state.round == "Turn":
            return random.random() < adjusted_bluff_freq * 1.2  # 12% base bluff frequency on turn
            
        # Bluff less on flop
        else:
            return random.random() < adjusted_bluff_freq  # 10% base bluff frequency on flop

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player based on hand strength and game situation. """
        print("Player called get action")
        
        # Update opponent stats based on previous actions
        self.update_opponent_stats(round_state)
        
        # Calculate hand strength using our stored hole cards and the community cards
        hand_strength = self.evaluate_hand_strength(self.hole_cards, round_state.community_cards)
        
        # Calculate pot odds
        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet) if (round_state.pot + round_state.current_bet) > 0 else 0
        
        # Get opponent stats
        fold_to_bet = self.opponent_stats['fold_to_bet']
        fold_to_raise = self.opponent_stats['fold_to_raise']
        aggression_factor = self.opponent_stats['aggression_factor']
        
        # Check if we should bluff
        should_bluff = self.should_bluff(round_state, hand_strength)
        
        # Adjust strategy based on hand strength and bluffing decision
        if round_state.round == "Preflop":
            # In preflop, be more selective with starting hands
            if hand_strength > 0.7:  # Strong starting hand
                if round_state.current_bet == 0:
                    # Adjust raise size based on opponent aggression
                    base_raise = 100
                    if aggression_factor > 0.5:  # Aggressive opponent, be more cautious
                        return PokerAction.RAISE, min(base_raise * 1.5, remaining_chips)
                    else:  # Passive opponent, be more aggressive
                        return PokerAction.RAISE, min(base_raise, remaining_chips)
                else:
                    return PokerAction.RAISE, min(round_state.min_raise * 2, remaining_chips)
            elif hand_strength > 0.4:  # Medium starting hand
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                elif pot_odds < 0.3:  # Good pot odds, call
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:  # Weak starting hand
                # Consider bluffing with weak hands in certain situations
                if should_bluff and round_state.current_bet == 0:
                    return PokerAction.RAISE, min(50, remaining_chips)  # Small bluff raise
                elif round_state.current_bet == 0:
                    return PokerAction.FOLD, 0
                elif pot_odds < 0.15:  # Very good pot odds needed to continue
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
                    
        elif round_state.round in ["Flop", "Turn", "River"]:
            # Post-flop strategy based on hand strength and bluffing
            if hand_strength > 0.8:  # Very strong hand
                # Adjust bet size based on pot size and opponent tendencies
                pot_size = round_state.pot
                if round_state.current_bet == 0:
                    # Bet size as percentage of pot based on hand strength and opponent
                    bet_percentage = 0.5  # Default 50% of pot
                    if aggression_factor < 0.3:  # Passive opponent, extract more value
                        bet_percentage = 0.7
                    elif aggression_factor > 0.6:  # Aggressive opponent, be careful
                        bet_percentage = 0.4
                    
                    bet_amount = min(int(pot_size * bet_percentage), remaining_chips)
                    return PokerAction.RAISE, max(bet_amount, 50)  # Bet to build pot
                else:
                    # When facing a bet, adjust raise size based on opponent
                    raise_multiplier = 3
                    if fold_to_raise > 0.7:  # Opponent folds to raises often
                        raise_multiplier = 4  # Raise more to maximize fold equity
                    elif fold_to_raise < 0.3:  # Opponent calls raises often
                        raise_multiplier = 2  # Min raise to keep them in hand
                    return PokerAction.RAISE, min(round_state.min_raise * raise_multiplier, remaining_chips)  # Raise to maximize value
            elif hand_strength > 0.6:  # Strong hand
                if round_state.current_bet == 0:
                    # Smaller bet with medium-strength hand
                    pot_size = round_state.pot
                    bet_percentage = 0.3  # Default 30% of pot
                    if fold_to_bet > 0.6:  # Opponent folds to bets often
                        bet_percentage = 0.4  # Bet more to get folds
                    elif fold_to_bet < 0.3:  # Opponent calls lots
                        bet_percentage = 0.2  # Smaller bet to keep them in hand
                    bet_amount = min(int(pot_size * bet_percentage), remaining_chips)
                    return PokerAction.RAISE, max(bet_amount, 30)  # Bet for value
                else:
                    return PokerAction.CALL, 0  # Call to see if we can improve or get value
            elif hand_strength > 0.4:  # Moderate hand
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0  # Check to see free cards
                elif pot_odds < 0.25:  # Decent pot odds, call
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:  # Weak hand - consider bluffing
                if should_bluff:
                    # Bluff with a bet or raise, adjusting size based on opponent
                    if round_state.current_bet == 0:
                        pot_size = round_state.pot
                        # Bluff bet size based on opponent fold stats
                        if fold_to_bet > 0.6:  # Opponent folds often, bet bigger
                            bet_percentage = 0.6
                        elif fold_to_bet > 0.4:  # Moderate fold rate, standard bluff
                            bet_percentage = 0.4
                        else:  # Low fold rate, small bluff
                            bet_percentage = 0.25
                        bet_amount = min(int(pot_size * bet_percentage), remaining_chips)
                        return PokerAction.BET, max(bet_amount, 40)  # Bluff bet
                    else:
                        # Only bluff raise if we have enough chips and it makes sense
                        if remaining_chips >= round_state.min_raise * 2:
                            # Adjust raise size based on opponent fold to raise
                            if fold_to_raise > 0.6:  # Opponent folds to raises often
                                raise_multiplier = 3
                            elif fold_to_raise > 0.4:  # Moderate fold rate
                                raise_multiplier = 2
                            else:  # Low fold rate
                                raise_multiplier = 2  # Still try to bluff but be cautious
                            return PokerAction.RAISE, min(round_state.min_raise * raise_multiplier, remaining_chips)  # Bluff raise
                        else:
                            return PokerAction.FOLD, 0  # Can't bluff raise, so fold
                else:
                    if round_state.current_bet == 0:
                        return PokerAction.CHECK, 0  # Check to see free cards
                    else:
                        return PokerAction.FOLD, 0  # Fold with weak hand

        # Default action if other conditions aren't met
        if round_state.current_bet == 0:
            return PokerAction.CHECK, 0
        else:
            return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")
        # Store round data for future analysis
        round_data = {
            'round_state': round_state,
            'remaining_chips': remaining_chips,
            'hole_cards': self.hole_cards,
            'hand_strength': self.evaluate_hand_strength(self.hole_cards, round_state.community_cards)
        }
        self.game_history.append(round_data)

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)