import sys
import logging
import random
sys.path.insert(0, './client/lib')

from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient
from deuces import Card, Evaluator

class SimplePlayer(Bot):
    def is_suited(self) -> bool:
        if not self.hand or len(self.hand) != 2:
            return False
        return self.hand[0][1] == self.hand[1][1]

    def is_connector(self) -> bool:
        if not self.hand or len(self.hand) != 2:
            return False
        rank1 = self.rank_values.get(self.hand[0][0], 0)
        rank2 = self.rank_values.get(self.hand[1][0], 0)
        if abs(rank1 - rank2) == 1:
            return True
        # Ace-2 connector (wheel)
        if (rank1 == 14 and rank2 == 2) or (rank1 == 2 and rank2 == 14):
            return True
        return False

    def get_all_cards(self, round_state: RoundStateClient) -> List[str]:
        return self.hand + round_state.community_cards

    def evaluate_hand(self, round_state: RoundStateClient) -> int:
        board = [Card.new(c) for c in round_state.community_cards]
        hand = [Card.new(c) for c in self.hand]
        evaluator = Evaluator()
        return evaluator.evaluate(board, hand)

    def get_pair_rank(self) -> str | None:
        if not self.hand or len(self.hand) != 2:
            return None
        if self.hand[0][0] == self.hand[1][0]:
            return self.hand[0][0]
        return None

    def has_flush_draw(self, round_state: RoundStateClient) -> bool:
        all_cards = self.get_all_cards(round_state)
        suits = [card[1] for card in all_cards]
        for suit in "shdc":
            if suits.count(suit) == 4:
                return True
        return False

    def has_straight_draw(self, round_state: RoundStateClient) -> bool:
        all_cards = self.get_all_cards(round_state)
        ranks = sorted(list(set([self.rank_values[card[0]] for card in all_cards])))
        if len(ranks) < 4:
            return False
        for i in range(len(ranks) - 3):
            if ranks[i+3] - ranks[i] == 3:
                return True
        # Ace-low straight
        if all(x in ranks for x in [2, 3, 4, 14]):
            return True
        return False

    def get_outs(self, round_state: RoundStateClient) -> int:
        outs = 0
        if self.has_flush_draw(round_state):
            outs += 9
        if self.has_straight_draw(round_state):
            # Be careful not to double count cards that complete both a straight and a flush
            all_cards = self.get_all_cards(round_state)
            suits = [card[1] for card in all_cards]
            flush_suit = ""
            for suit in "shdc":
                if suits.count(suit) == 4:
                    flush_suit = suit
                    break
            ranks = sorted(list(set([self.rank_values[card[0]] for card in all_cards])))
            potential_straight_cards = []
            for i in range(len(ranks) - 3):
                if ranks[i+3] - ranks[i] == 3:
                    low_rank = ranks[i]
                    high_rank = ranks[i+3]
                    if low_rank > 1:
                        potential_straight_cards.append(low_rank - 1)
                    if high_rank < 14:
                        potential_straight_cards.append(high_rank + 1)
            # Ace-low straight
            if all(x in ranks for x in [2, 3, 4, 14]):
                potential_straight_cards.append(5)
            
            straight_outs = 0
            for rank in potential_straight_cards:
                is_flush_card = False
                for card_rank, card_suit in self.hand + round_state.community_cards:
                    if self.rank_values[card_rank] == rank and card_suit == flush_suit:
                        is_flush_card = True
                        break
                if not is_flush_card:
                    straight_outs += 1
            outs += straight_outs
        return outs

    def __init__(self):
        self.hand: List[str] = []
        self.rank_values = {'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10, '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}
        super().__init__()
        self.opponent_stats = {}
        self.hands_played = 0
        self.blind_amount = 0
        self.STRAIGHT_FLUSH = 1
        self.FOUR_OF_A_KIND = 2
        self.FULL_HOUSE = 3
        self.FLUSH = 4
        self.STRAIGHT = 5
        self.THREE_OF_A_KIND = 6
        self.TWO_PAIR = 7
        self.PAIR = 8
        self.HIGH_CARD = 9

    def update_opponent_stats(self, round_state: RoundStateClient):
        """Placeholder for updating opponent statistics."""
        # Future implementation will parse round_state.actions
        # to track opponent's VPIP, PFR, aggression factor, etc.
        pass

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print(f"Player hands: {player_hands}")
        print(f"Blind: {blind_amount}")
        print(f"Big blind player id: {big_blind_player_id}")
        print(f"Small blind player id: {small_blind_player_id}")
        print(f"All players in game: {all_players}")
        print(f"My id: {self.id}")
        self.hand = player_hands
        self.blind_amount = blind_amount

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print(f"Round state: {round_state}")
        self.hands_played += 1

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        print("Player called get action")
        print(f"Round state for analysis: {round_state}") # Added for opponent modeling
        self.update_opponent_stats(round_state)

        # Pre-flop logic
        if not round_state.community_cards:
            pair_rank = self.get_pair_rank()
            suited = self.is_suited()
            connector = self.is_connector()

            if pair_rank:
                raise_amount = self.blind_amount * 3 if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount
            
            if suited and connector:
                raise_amount = self.blind_amount * 4 if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount
            
            if suited:
                raise_amount = self.blind_amount * 3 if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount
            
            if connector:
                raise_amount = int(self.blind_amount * 2.5) if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount
            
            # Weak hands
            if round_state.current_bet > self.blind_amount:
                return PokerAction.FOLD, 0
            return PokerAction.CHECK, 0

        # Post-flop logic
        else:
            score = self.evaluate_hand(round_state)
            evaluator = Evaluator()
            rank_class = evaluator.get_rank_class(score)

            # Very strong hands (Full House or better)
            if rank_class <= self.FULL_HOUSE:
                raise_amount = max(self.blind_amount, round_state.pot)
                return PokerAction.RAISE, raise_amount

            # Strong hands (Flush or Straight)
            elif rank_class <= self.STRAIGHT:
                raise_amount = max(self.blind_amount, int(round_state.pot * 0.75))
                return PokerAction.RAISE, raise_amount

            # Three of a kind
            elif rank_class == self.THREE_OF_A_KIND:
                raise_amount = max(self.blind_amount, int(round_state.pot * 0.60))
                return PokerAction.RAISE, raise_amount
            
            # Two pair
            elif rank_class == self.TWO_PAIR:
                raise_amount = max(self.blind_amount, int(round_state.pot * 0.5))
                return PokerAction.RAISE, raise_amount

            # One pair - tiered logic based on score
            elif rank_class == self.PAIR:
                # Strong Pair (Top 1/3 of pairs, score <= 4278)
                if score <= 4278:
                    if round_state.current_bet == 0:
                        # Bet for value
                        raise_amount = max(self.blind_amount, int(round_state.pot * 0.5))
                        return PokerAction.RAISE, raise_amount
                    elif round_state.current_bet <= round_state.pot:
                        # Call bets up to pot size
                        return PokerAction.CALL, 0
                    else:
                        return PokerAction.FOLD, 0
                # Medium Pair (Middle 1/3 of pairs, score <= 5231)
                elif score <= 5231:
                    if round_state.current_bet > (round_state.pot / 2):
                        return PokerAction.FOLD, 0
                    if round_state.current_bet == 0:
                        return PokerAction.CHECK, 0
                    return PokerAction.CALL, 0
                # Weak Pair (Bottom 1/3 of pairs)
                else:
                    if round_state.current_bet > (round_state.pot / 4):
                        return PokerAction.FOLD, 0
                    if round_state.current_bet == 0:
                        return PokerAction.CHECK, 0
                    return PokerAction.CALL, 0
            
            # High card
            else:
                outs = self.get_outs(round_state)

                if outs > 0:
                    # We have a draw
                    num_community_cards = len(round_state.community_cards)
                    # Equity approximation: (outs * 4) / 100 on flop, (outs * 2) / 100 on turn
                    equity = 0
                    if num_community_cards == 3: # Flop
                        equity = (outs * 4) / 100.0
                    elif num_community_cards == 4: # Turn
                        equity = (outs * 2) / 100.0

                    if round_state.current_bet == 0:
                        # Semi-bluff bet
                        bet_amount = 0
                        if outs >= 12: # Combo draw
                            bet_amount = int(round_state.pot * 0.75)
                        elif outs >= 8: # Strong draw
                            bet_amount = int(round_state.pot * 0.60)
                        else: # Weak draw
                            bet_amount = int(round_state.pot * 0.40)
                        return PokerAction.RAISE, max(self.blind_amount, bet_amount)
                    else:
                        # Facing a bet
                        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)

                        if equity > pot_odds:
                            # It's profitable to call based on odds
                            # Let's consider re-raising as a semi-bluff
                            raise_chance = 0
                            if outs >= 12: # Combo draw
                                raise_chance = 0.40
                            elif outs >= 8: # Strong draw
                                raise_chance = 0.25
                            
                            if random.random() < raise_chance:
                                raise_amount = round_state.current_bet * 3
                                return PokerAction.RAISE, raise_amount
                            
                            return PokerAction.CALL, 0
                        else:
                            # Not profitable to call, but maybe we can bluff
                            # For now, just fold
                            return PokerAction.FOLD, 0
                else:
                    # No draw, high card logic
                    if round_state.current_bet == 0:
                        # Bluff heads-up with a 15% chance
                        if sum(1 for action in round_state.player_actions.values() if action != "fold") == 2 and random.random() < 0.15:
                            raise_amount = max(self.blind_amount, int(round_state.pot * 0.5))
                            return PokerAction.RAISE, raise_amount
                        return PokerAction.CHECK, 0
                    return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print(f"Player called on end game, with player score: {player_score}")
        print(f"All final scores: {all_scores}")
        print(f"Active players hands: {active_players_hands}")