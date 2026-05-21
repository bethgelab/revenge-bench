def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        self._update_opponent_stats(round_state)

        is_raised = any(action.action == 'Raise' for p_id, action in round_state.player_actions.items() if str(p_id) != str(self.id))

        if round_state.round == 'preflop':
            strength = self._get_preflop_strength()

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
        else: # Post-flop
            strength = self._get_postflop_strength(round_state.community_cards)

            if self.was_preflop_aggressor and strength < 1 and round_state.current_bet == 0 and round_state.round == 'flop':
                raise_amount = self._get_clamped_raise_amount(int(round_state.pot * 0.4), round_state, remaining_chips)
                return PokerAction.RAISE, raise_amount

            if strength >= 4: # Straight or better
                raise_amount = self._get_clamped_raise_amount(int(round_state.pot * random.uniform(0.7, 1.0)), round_state, remaining_chips)
                return PokerAction.RAISE, raise_amount
            elif strength >= 2: # Two pair or three of a kind
                if round_state.current_bet > 0:
                    raise_amount = self._get_clamped_raise_amount(int(round_state.current_bet * random.uniform(1.8, 2.5)), round_state, remaining_chips)
                else:
                    raise_amount = self._get_clamped_raise_amount(int(round_state.pot * random.uniform(0.4, 0.6)), round_state, remaining_chips)
                return PokerAction.RAISE, raise_amount
            elif strength >= 1.5: # Top pair
                if round_state.current_bet > 0:
                    raise_amount = self._get_clamped_raise_amount(int(round_state.current_bet * random.uniform(2.0, 3.0)), round_state, remaining_chips)
                else:
                    raise_amount = self._get_clamped_raise_amount(int(round_state.pot * random.uniform(0.5, 0.8)), round_state, remaining_chips)
                return PokerAction.RAISE, raise_amount
            elif strength >= 1.2: # Pocket pair below top card
                if round_state.current_bet > remaining_chips * 0.3:
                    return PokerAction.FOLD, 0
                return (PokerAction.CALL, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)
            elif strength >= 1: # Middle/bottom pair
                if round_state.current_bet > remaining_chips * 0.2 and round_state.pot < round_state.current_bet * 3:
                    return PokerAction.FOLD, 0
                return (PokerAction.CALL, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)
            elif strength > 0: # Draws
                # Determine odds to improve
                outs = 0
                if strength == 0.8: outs = 15 # Flush + OESD
                elif strength == 0.7: outs = 9 # Flush
                elif strength == 0.6: outs = 8 # OESD/Gutshot
                
                num_unseen_cards = 52 - (len(self.hand) + len(round_state.community_cards))
                hit_prob = outs / num_unseen_cards if num_unseen_cards > 0 else 0

                pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet) if (round_state.pot + round_state.current_bet) > 0 else 0

                if round_state.current_bet == 0:
                    # Semi-bluff by betting
                    raise_amount = self._get_clamped_raise_amount(int(round_state.pot * 0.5), round_state, remaining_chips)
                    return PokerAction.RAISE, raise_amount
                elif hit_prob > pot_odds:
                    # Call if the pot odds are in our favor
                    return PokerAction.CALL, 0
                else:
                    return PokerAction.FOLD, 0
            else:
                return (PokerAction.CHECK, 0) if round_state.current_bet == 0 else (PokerAction.FOLD, 0)