def _get_board_wetness(self, community_cards: List[str]) -> int:
        if not community_cards:
            return 0

        wetness_score = 0
        
        # Flush draw check
        suits = [card[1] for card in community_cards]
        suit_counts = {suit: suits.count(suit) for suit in set(suits)}
        if 3 in suit_counts.values():
            wetness_score += 4
        elif 2 in suit_counts.values():
            wetness_score += 2

        # Straight draw check
        rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        numerical_ranks = sorted(list(set([rank_map[card[0]] for card in community_cards])))
        
        if len(numerical_ranks) >= 3:
            rank_span = numerical_ranks[-1] - numerical_ranks[0]
            if rank_span == 2: # e.g., 5,6,7
                wetness_score += 3
            elif rank_span == 3: # e.g., 5,6,8 or 5,7,8
                wetness_score += 2
            elif rank_span == 4: # e.g., 5,6,9 or 5,8,9
                wetness_score += 1
        
        # Paired board check
        ranks = [card[0] for card in community_cards]
        rank_counts = {rank: ranks.count(rank) for rank in set(ranks)}
        if 2 in rank_counts.values() or 3 in rank_counts.values():
            wetness_score -= 1

        return max(0, wetness_score)