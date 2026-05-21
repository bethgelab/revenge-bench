def _get_preflop_strength(self):
        card1, card2 = self.hand[0], self.hand[1]
        rank1_str, suit1 = card1[0], card1[1]
        rank2_str, suit2 = card2[0], card2[1]
        rank1, rank2 = self.ranks.get(rank1_str, 0), self.ranks.get(rank2_str, 0)
        is_suited = suit1 == suit2
        
        # Create a standardized hand representation (e.g., 'AKs', 'T9o')
        high_rank_str = self.inv_ranks[max(rank1, rank2)]
        low_rank_str = self.inv_ranks[min(rank1, rank2)]
        
        if rank1 == rank2:
            hand_str = high_rank_str + low_rank_str
        else:
            hand_str = high_rank_str + low_rank_str + ('s' if is_suited else 'o')

        # Tier-based hand strength evaluation
        tier1 = {'AA', 'KK', 'QQ', 'JJ', 'AKs'}
        tier2 = {'TT', 'AQs', 'AJs', 'KQs', 'AKo'}
        tier3 = {'99', 'JTs', 'QJs', 'KJs', 'ATs', 'AQo'}
        tier4 = {'88', 'KTs', 'QTs', 'J9s', 'T9s', '98s', 'AJo', 'KQo'}
        tier5 = {'77', '87s', '76s', '65s', 'A9s', 'A8s', 'A7s', 'A6s', 'A5s', 'A4s', 'A3s', 'A2s', 'KJo', 'QJo', 'JTo'}
        tier6 = {'66', '55', 'T8s', '97s', '86s', '75s', '54s', 'ATo', 'KTo', 'QTo'}
        tier7 = {'44', '33', '22', 'J9o', 'T9o', '98o'}
        tier8 = {'K9s', 'K8s', 'K7s', 'K6s', 'K5s', 'K4s', 'K3s', 'K2s', 'Q9s', 'Q8s', 'J8s', '64s'}

        if hand_str in tier1: return 1
        if hand_str in tier2: return 2
        if hand_str in tier3: return 3
        if hand_str in tier4: return 4
        if hand_str in tier5: return 5
        if hand_str in tier6: return 6
        if hand_str in tier7: return 7
        if hand_str in tier8: return 8
        return 9