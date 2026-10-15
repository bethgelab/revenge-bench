elif position == 'BB': # Out of Position
                if not is_facing_bet:
                    # Value Betting Logic (stricter OOP)
                    value_bet_threshold = 2.0
                    if opponent_type == 'calling_station':
                        value_bet_threshold = 1.5
                    if strength >= value_bet_threshold:
                        bet_amount = self._get_dynamic_bet_size(strength, pot, round_state)
                        return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # C-Betting Logic (less frequent OOP)
                    elif self.was_preflop_aggressor and round_state.round == 'flop':
                        bluff_chance = 0.25
                        if opponent_type == 'tight_passive' and board_texture == 'dry':
                            bluff_chance = 0.60
                        
                        if random.random() < bluff_chance:
                            bet_amount = self._get_dynamic_bet_size(0, pot, round_state, is_bluff=True)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)

                    # Semi-Bluffing with Draws (more passive OOP)
                    elif 0.6 <= strength <= 0.8:
                        return PokerAction.CHECK, 0 # Check/call with draws OOP
                    
                    # Default Action
                    else:
                        return PokerAction.CHECK, 0
                else: # Facing a bet
                    # Raising Logic (very strong hands only)
                    if strength >= 5:
                        raise_amount = self._get_clamped_raise_amount(int(pot * 2.2), round_state, remaining_chips)
                        return PokerAction.RAISE, raise_amount

                    # Calling Logic
                    call_threshold = 1.5
                    if opponent_type == 'aggressive':
                        call_threshold = 1.2
                    elif opponent_type == 'tight_passive':
                        call_threshold = 2.5
                    if strength >= call_threshold:
                        return PokerAction.CALL, bet_to_match

                    # Calling with Draws
                    elif 0.6 <= strength <= 0.8:
                        pot_odds = bet_to_match / (pot + bet_to_match)
                        draw_odds = (9/47) if strength == 0.7 else (8/47) # simplified odds
                        if pot_odds < draw_odds:
                            return PokerAction.CALL, bet_to_match
                        else:
                            return PokerAction.FOLD, 0
                    
                    # Default Action
                    else:
                        return PokerAction.FOLD, 0