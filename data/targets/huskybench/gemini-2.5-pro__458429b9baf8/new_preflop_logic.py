if strength <= 2: # Tiers 1-2: Premium hands
                self.was_preflop_aggressor = True
                # Always raise, and re-raise if someone else raised
                raise_amount = self._get_clamped_raise_amount(round_state.current_bet * 3 if is_raised else 50, round_state, remaining_chips)
                return PokerAction.RAISE, raise_amount
            elif strength == 3: # Tier 3: Strong hands
                if not is_raised:
                    self.was_preflop_aggressor = True
                    raise_amount = self._get_clamped_raise_amount(40, round_state, remaining_chips)
                    return PokerAction.RAISE, raise_amount
                else:
                    return PokerAction.CALL, 0
            elif strength == 4: # Tier 4: Good hands, play with caution if raised
                if not is_raised:
                    self.was_preflop_aggressor = True
                    raise_amount = self._get_clamped_raise_amount(30, round_state, remaining_chips)
                    return PokerAction.RAISE, raise_amount
                else:
                    # Facing a raise, use opponent stats
                    raiser_id = -1
                    for p_id, action in round_state.player_actions.items():
                        if action.action == 'Raise':
                            raiser_id = int(p_id)
                            break
                    
                    if raiser_id != -1 and raiser_id in self.opponent_stats:
                        stats = self.opponent_stats[raiser_id]
                        if stats['vpip_opportunities'] > 10:
                            vpip = stats['vpip_put_money_in_pot'] / stats['vpip_opportunities']
                            pfr = stats['pfr_raise_count'] / stats['pfr_opportunities'] if stats['pfr_opportunities'] > 0 else 0
                            
                            is_tight = vpip < 0.25
                            is_aggressive = pfr > 0.15

                            if is_tight and is_aggressive: # TAG - likely has a strong hand
                                return PokerAction.FOLD, 0
                            elif not is_tight and is_aggressive: # LAG - could be bluffing
                                return PokerAction.CALL, 0
                            else: # Passive players - raise is more likely to be for value
                                return PokerAction.FOLD, 0

                    # Default to folding if not enough stats
                    return PokerAction.FOLD, 0
            elif strength <= 6: # Tiers 5-6: Speculative hands
                if round_state.current_bet < remaining_chips * 0.05: # Call small bets
                    return (PokerAction.CALL, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)
                else:
                    return PokerAction.FOLD, 0
            else: # Tiers 7-9: Weak hands
                # Only play if we can check (e.g., in big blind)
                return (PokerAction.CHECK, 0) if round_state.current_bet == 0 else (PokerAction.FOLD, 0)