def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        hand_strength = self.get_hand_strength(round_state.community_cards)
        to_call = round_state.get_tocall_amount(self.id)
        min_raise = round_state.get_min_raise(self.id)
        pot_size = round_state.pot

        # Introduce randomness to bet sizing
        raise_multiplier = 1.0 + random.uniform(-0.1, 0.1) # +/- 10%

        raise_amount = 0
        if hand_strength == 8: raise_amount = remaining_chips
        elif hand_strength == 7: raise_amount = int(remaining_chips * 0.8 * raise_multiplier)
        elif hand_strength == 6: raise_amount = int(remaining_chips * 0.6 * raise_multiplier)
        elif hand_strength == 5: raise_amount = int(remaining_chips * 0.5 * raise_multiplier)
        elif hand_strength == 4: raise_amount = int(remaining_chips * 0.4 * raise_multiplier)
        elif hand_strength == 3: raise_amount = int(remaining_chips * 0.3 * raise_multiplier)
        elif hand_strength == 2: raise_amount = int(remaining_chips * 0.2 * raise_multiplier)
        elif hand_strength == 1: raise_amount = int(remaining_chips * 0.1 * raise_multiplier)
        
        # Probabilistic bluffing with weak hands
        if hand_strength <= 1 and random.random() < 0.20: # 20% chance to bluff
            # Bluff amount is a fraction of the pot, e.g., 50% to 75%
            bluff_raise = int(pot_size * random.uniform(0.5, 0.75))
            if bluff_raise >= min_raise and bluff_raise <= remaining_chips:
                return PokerAction.RAISE, bluff_raise

        if raise_amount > 0:
            final_bet = min(remaining_chips, max(min_raise, raise_amount))
            if final_bet > to_call:
                return PokerAction.RAISE, final_bet
        
        if to_call > 0:
            # Be more likely to fold with a weak hand if the call amount is high
            if hand_strength < 2 and to_call > pot_size * 0.3: # If call is > 30% of pot
                 if random.random() < 0.5: # 50% chance to fold
                    return PokerAction.FOLD, 0

            if remaining_chips >= to_call:
                return PokerAction.CALL, to_call
            else:
                return PokerAction.CALL, remaining_chips
        else:
            return PokerAction.CHECK, 0