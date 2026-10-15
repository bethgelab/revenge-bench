import random
from collections import Counter
from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()
        self.hand = None
        self.position = 0
        self.opponent_stats = {}
        self.opponent_raises = 0
        self.blind = 0
        self.preflop_raised = False

    def get_max_vpip(self):
        max_vpip = 0
        for stats in self.opponent_stats.values():
            actions = stats["actions"]
            if actions > 0:
                vpip = stats["raises"] / actions
                if vpip > max_vpip:
                    max_vpip = vpip
        return max_vpip

    def calculate_pot_odds(self, call_amount, estimated_pot):
        if call_amount == 0:
            return float("inf")
        return estimated_pot / call_amount

    def should_call_on_pot_odds(self, call_amount, estimated_pot, hand_strength):
        odds = self.calculate_pot_odds(call_amount, estimated_pot)
        if hand_strength < 200:
            return odds > 4  # 1:4 odds for weak hands
        elif hand_strength < 300:
            return odds > 3  # 1:3 for medium
        return False

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int, big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        print("Player called on game start")
        print("Player hands: ", player_hands)
        print("Blind: ", blind_amount)
        print("Big blind player id: ", big_blind_player_id)
        print("Small blind player id: ", small_blind_player_id)
        print("All players in game: ", all_players)
        self.opponent_raises = 0
        self.blind = blind_amount
        self.preflop_raised = False
        self.hand = player_hands[all_players.index(self.id)]
        self.all_players = all_players
        self.position = all_players.index(self.id)
        for pid in all_players:
            if pid != self.id:
                self.opponent_stats[pid] = {"raises": 0, "actions": 0}

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        print("Player called on round start")
        print("Round state: ", round_state)
        self.preflop_raised = False

    def evaluate_preflop_hand(self):
        if not self.hand:
            return 0
        cards = self.hand.split()
        if len(cards) != 2:
            return 0
        ranks = []
        suits = []
        for card in cards:
            rank = card[0]
            suit = card[1]
            if rank == 'A':
                rank = 14
            elif rank == 'K':
                rank = 13
            elif rank == 'Q':
                rank = 12
            elif rank == 'J':
                rank = 11
            elif rank == 'T':
                rank = 10
            else:
                rank = int(rank)
            ranks.append(rank)
            suits.append(suit)
        ranks.sort(reverse=True)
        if ranks[0] == ranks[1]:
            score = 100 + ranks[0]
        else:
            score = ranks[0] * 10 + ranks[1]
            if suits[0] == suits[1]:
                score += 1
            if abs(ranks[0] - ranks[1]) == 1:
                score += 2
        return score

    def is_straight(self, ranks):
        unique_ranks = list(set(ranks))
        unique_ranks.sort(reverse=True)
        for i in range(len(unique_ranks)-4):
            if unique_ranks[i] - unique_ranks[i+4] == 4:
                return True
        if 14 in unique_ranks and all(r in unique_ranks for r in [2,3,4,5]):
            return True
        return False

    def evaluate_postflop_hand(self, hole_cards, community_cards):
        all_cards = hole_cards.split() + community_cards
        ranks = []
        suits = []
        for card in all_cards:
            rank = card[0]
            suit = card[1]
            if rank == 'A':
                rank = 14
            elif rank == 'K':
                rank = 13
            elif rank == 'Q':
                rank = 12
            elif rank == 'J':
                rank = 11
            elif rank == 'T':
                rank = 10
            else:
                rank = int(rank)
            ranks.append(rank)
            suits.append(suit)
        rank_count = Counter(ranks)
        suit_count = Counter(suits)
        # Check for flush
        flush_suit = None
        for suit, count in suit_count.items():
            if count >= 5:
                flush_suit = suit
                break
        if flush_suit:
            flush_ranks = [r for r, s in zip(ranks, suits) if s == flush_suit]
            flush_ranks.sort(reverse=True)
            # Straight flush
            if self.is_straight(flush_ranks):
                return 900 + flush_ranks[0]
            # Flush
            return 600 + flush_ranks[0]
        # Check for straight
        if self.is_straight(ranks):
            return 500 + max(ranks)
        # Check for pairs, etc.
        pairs = []
        three = []
        four = []
        for rank, count in rank_count.items():
            if count == 4:
                four.append(rank)
            elif count == 3:
                three.append(rank)
            elif count == 2:
                pairs.append(rank)
        pairs.sort(reverse=True)
        three.sort(reverse=True)
        four.sort(reverse=True)
        if four:
            # Four of a kind
            kicker = max(r for r in ranks if r != four[0])
            return 800 + four[0] * 10 + kicker
        if three and pairs:
            # Full house
            return 700 + three[0] * 10 + pairs[0]
        if three:
            # Three of a kind
            kickers = [r for r in ranks if r != three[0]]
            kickers.sort(reverse=True)
            return 400 + three[0] * 10 + kickers[0]
        if len(pairs) >= 2:
            # Two pair
            return 300 + pairs[0] * 10 + pairs[1]
        if pairs:
            # One pair
            kickers = [r for r in ranks if r != pairs[0]]
            kickers.sort(reverse=True)
            return 200 + pairs[0] * 10 + kickers[0]
        # High card
        ranks.sort(reverse=True)
        return 100 + ranks[0]

    def has_draw(self, hole_cards, community_cards):
        all_cards = hole_cards.split() + community_cards
        ranks = []
        suits = []
        for card in all_cards:
            rank = card[0]
            suit = card[1]
            if rank == 'A':
                rank = 14
            elif rank == 'K':
                rank = 13
            elif rank == 'Q':
                rank = 12
            elif rank == 'J':
                rank = 11
            elif rank == 'T':
                rank = 10
            else:
                rank = int(rank)
            ranks.append(rank)
            suits.append(suit)
        suit_count = Counter(suits)
        flush_draw = any(count == 4 for count in suit_count.values())
        unique_ranks = list(set(ranks))
        unique_ranks.sort(reverse=True)
        straight_draw = False
        for i in range(len(unique_ranks)-3):
            if unique_ranks[i] - unique_ranks[i+3] == 3:
                straight_draw = True
                break
        return flush_draw or straight_draw

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        """ Returns the action for the player. """
        print("Player called get action")
        for pid, action in round_state.player_actions.items():
            if pid != self.id:
                self.opponent_stats[pid]["actions"] += 1
                if action == "Raise":
                    self.opponent_stats[pid]["raises"] += 1

        raised = False
        for player_action in round_state.player_actions.values():
            if player_action == "Raise":
                raised = True
        self.opponent_raises += 1 if raised else 0

        if round_state.round == "preflop":
            strength = self.evaluate_preflop_hand()
            tightness = 1 + self.get_max_vpip() * 5
            if remaining_chips < 1000:
                tightness += 1
            tightness = min(tightness, 3)
            if strength > 150:  # high pairs
                self.preflop_raised = True
                return PokerAction.RAISE, min(remaining_chips, round_state.max_raise)
            elif strength > 100 + tightness * 10:  # medium
                if not raised:
                    self.preflop_raised = True
                    return PokerAction.RAISE, min(remaining_chips, 3 * self.blind)
                else:
                    return PokerAction.CALL, 0
            else:
                if self.preflop_raised and round_state.current_bet == 0:
                    return PokerAction.RAISE, min(remaining_chips, 2 * self.blind)
                if raised:
                    return PokerAction.FOLD, 0
                else:
                    return PokerAction.CALL, 0
        else:
            strength = self.evaluate_postflop_hand(self.hand, round_state.community_cards)
            if strength > 600:
                return PokerAction.RAISE, min(remaining_chips, round_state.max_raise)
            elif strength > 300:
                if self.position >= len(self.all_players) - 2 and round_state.current_bet == 0:
                    return PokerAction.RAISE, min(remaining_chips, 3 * self.blind)
                else:
                    return PokerAction.CALL, 0
            else:
                if self.preflop_raised and round_state.current_bet == 0:
                    return PokerAction.RAISE, min(remaining_chips, 2 * self.blind)
                if self.has_draw(self.hand, round_state.community_cards) and random.random() < (0.3 + (1 - self.get_max_vpip()) * 0.4):
                    return PokerAction.RAISE, min(remaining_chips, self.blind)
                else:
                    if round_state.current_bet == 0:
                        return PokerAction.CHECK, 0
                    else:
                        if self.should_call_on_pot_odds(round_state.current_bet, round_state.pot, strength):
                            return PokerAction.CALL, 0
                        else:
                            return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")

    def on_end_game(self, round_state: RoundStateClient, player_score: float, all_scores: dict, active_players_hands: dict):
        print("Player called on end game, with player score: ", player_score)
        print("All final scores: ", all_scores)
        print("Active players hands: ", active_players_hands)