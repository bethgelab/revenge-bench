# ===== RIVER LOGIC =====
        elif round_state.round_num == 4:
            # Track opponent stats from the turn before making a river decision
            self._track_opponent_fold_to_turn_bet(round_state)
            self._track_opponent_river_bet(round_state)
            self._track_opponent_fold_to_river_bet(round_state)

            # Value Betting with Strong Hands
            if hand_strength >= 3: # Two Pair or better
                bet_amount = int(pot_size * 0.7)
                return (PokerAction.RAISE, bet_amount) if round_state.current_bet > 0 else (PokerAction.BET, bet_amount)

            # Bluff Catching with Medium Hands
            elif hand_strength == 2: # One Pair
                if round_state.current_bet > 0:
                    river_aggro_freq = self._get_opponent_river_aggression_frequency()
                    pot_odds = self._calculate_pot_odds(pot_size, round_state.current_bet)
                    required_equity = 1 / (pot_odds + 1) if pot_odds is not None else 1

                    # If opponent is aggressive, we can call more lightly
                    if river_aggro_freq > 0.5:
                        # Call with bets up to 2/3 of the pot
                        if round_state.current_bet < pot_size * 0.67:
                            return (PokerAction.CALL, 0)
                        else:
                            return (PokerAction.FOLD, 0)
                    # If opponent is passive, only call small bets
                    else:
                        if round_state.current_bet < pot_size * 0.33:
                             return (PokerAction.CALL, 0)
                        else:
                            return (PokerAction.FOLD, 0)
                else:
                    # Check if we have a medium strength hand and no one has bet
                    return (PokerAction.CHECK, 0)

            # Bluffing with Weak Hands
            else: # High card / missed draws
                if round_state.current_bet == 0:
                    fold_freq = self._get_opponent_fold_to_river_bet_frequency()
                    # Bluff if opponent folds often, don't bluff if they call a lot
                    bluff_chance = 0.0
                    if fold_freq > 0.6:
                        bluff_chance = 0.75 # High chance to bluff
                    elif fold_freq > 0.4:
                        bluff_chance = 0.40 # Medium chance
                    
                    if random.random() < bluff_chance:
                        return (PokerAction.BET, int(pot_size * 0.6))
                
                # Default action for weak hands is to check or fold
                return (PokerAction.FOLD, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)