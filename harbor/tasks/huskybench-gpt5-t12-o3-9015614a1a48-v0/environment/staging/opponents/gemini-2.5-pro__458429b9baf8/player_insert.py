# Modified Donk Bet Logic based on Board Texture
                    if not self.was_preflop_aggressor:
                        donk_bet_condition = False
                        if board_texture == 'dry':
                            if strength >= 2: # Two pair or better
                                donk_bet_condition = True
                        elif board_texture == 'wet' or board_texture == 'paired':
                            if strength >= 4: # Straight or better
                                donk_bet_condition = True
                        
                        if donk_bet_condition:
                            bet_amount = self._get_dynamic_bet_size(strength, round_state.pot, round_state)
                            return PokerAction.RAISE, self._get_clamped_raise_amount(bet_amount, round_state, remaining_chips)