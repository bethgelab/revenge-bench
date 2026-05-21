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