def _get_dynamic_bet_size(self, strength: float, pot: int, round_state: RoundStateClient, is_bluff: bool = False, opponent_profile: str = "standard", board_texture: str = "dry") -> int:
        big_blind = 2 * round_state.big_blind_amount

        # 1. Base bet sizing on hand strength or bluff status
        if is_bluff:
            base_multiplier = random.uniform(0.33, 0.5)
        elif strength >= 6:  # Very strong hand (2pair+)
            base_multiplier = random.uniform(0.75, 1.2)
        elif strength >= 4:  # Strong hand (Top pair good kicker)
            base_multiplier = random.uniform(0.6, 0.9)
        elif strength >= 2:  # Medium hand (Top pair weak kicker, middle pair)
            base_multiplier = random.uniform(0.5, 0.75)
        else:  # Marginal hand
            base_multiplier = random.uniform(0.4, 0.6)

        # 2. Adjust multiplier based on opponent profile
        if opponent_profile == "calling_station":
            if not is_bluff:
                base_multiplier *= 1.25  # Bet bigger for value
            else:
                base_multiplier *= 0.75  # Bluff smaller or not at all
        elif opponent_profile == "tight_passive":
            if is_bluff:
                base_multiplier *= 1.1 # Can bluff them more effectively
        elif opponent_profile == "aggressive":
            if not is_bluff:
                base_multiplier *= 1.1 # Get value from their aggression

        # 3. Adjust multiplier based on board texture
        if board_texture == "wet":
            if not is_bluff:
                base_multiplier *= 1.2 # Charge draws
            else:
                base_multiplier *= 0.8 # Be more cautious with bluffs
        elif board_texture == "dry":
            if is_bluff:
                base_multiplier *= 1.1 # Bluffs are more likely to succeed

        bet = int(pot * base_multiplier)
        return max(bet, big_blind if not is_bluff else int(big_blind * 0.5))