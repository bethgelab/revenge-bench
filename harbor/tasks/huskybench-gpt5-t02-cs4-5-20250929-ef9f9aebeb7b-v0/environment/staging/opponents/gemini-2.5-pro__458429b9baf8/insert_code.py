def _get_dynamic_bet_size(self, strength: float, pot: int, is_bluff: bool = False) -> int:
        """
        Determines a dynamic bet size based on hand strength and situation.
        """
        if is_bluff:
            # Smaller bets for bluffs, typically 33-50% of the pot
            return int(pot * random.uniform(0.33, 0.5))

        # Value betting
        if strength >= 6: # Full house or better (the nuts)
            # Bet larger to extract maximum value. Can even overbet.
            return int(pot * random.uniform(0.75, 1.2))
        elif strength >= 4: # Straight or flush
            return int(pot * random.uniform(0.6, 0.9))
        elif strength >= 2: # Two pair or three of a kind
            return int(pot * random.uniform(0.5, 0.75))
        elif strength >= 1.5: # Top pair
            return int(pot * random.uniform(0.4, 0.6))
        else: # Weaker hands, should not be value betting, but as a fallback
            return int(pot * 0.5)