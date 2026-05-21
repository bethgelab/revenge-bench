outs = self.get_outs(round_state)

                if outs > 0:
                    # We have a draw
                    num_community_cards = len(round_state.community_cards)
                    # Equity approximation: (outs * 4) / 100 on flop, (outs * 2) / 100 on turn
                    equity = 0
                    if num_community_cards == 3: # Flop
                        equity = (outs * 4) / 100.0
                    elif num_community_cards == 4: # Turn
                        equity = (outs * 2) / 100.0

                    if round_state.current_bet == 0:
                        # Semi-bluff bet
                        bet_amount = 0
                        if outs >= 12: # Combo draw
                            bet_amount = int(round_state.pot * 0.75)
                        elif outs >= 8: # Strong draw
                            bet_amount = int(round_state.pot * 0.60)
                        else: # Weak draw
                            bet_amount = int(round_state.pot * 0.40)
                        return PokerAction.RAISE, max(self.blind_amount, bet_amount)
                    else:
                        # Facing a bet
                        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)

                        if equity > pot_odds:
                            # It's profitable to call based on odds
                            # Let's consider re-raising as a semi-bluff
                            raise_chance = 0
                            if outs >= 12: # Combo draw
                                raise_chance = 0.40
                            elif outs >= 8: # Strong draw
                                raise_chance = 0.25
                            
                            if random.random() < raise_chance:
                                raise_amount = round_state.current_bet * 3
                                return PokerAction.RAISE, raise_amount
                            
                            return PokerAction.CALL, 0
                        else:
                            # Not profitable to call, but maybe we can bluff
                            # For now, just fold
                            return PokerAction.FOLD, 0