else: # No made hand, no draw -> Bluffing opportunity
                # C-Bet logic: If we were the pre-flop aggressor, consider a bluff.
                preflop_aggressor = None
                if hasattr(round_state, 'action_sequence'):
                    preflop_actions = [a for a in round_state.action_sequence if a.get('round') == 1]
                    for action in reversed(preflop_actions):
                        if action.get('action') in ['RAISE', 'BET']:
                            preflop_aggressor = action.get('player')
                            break
                if preflop_aggressor is None: preflop_aggressor = round_state.big_blind_player_id

                if preflop_aggressor == self.player_id and round_state.current_bet == 0 and round_state.round_num == 2:
                    fold_freq = self._get_opponent_fold_to_cbet_frequency()
                    bluff_chance = 0
                    if fold_freq > 0.6:
                        bluff_chance = 0.8 # Bluff frequently against players who fold a lot
                    elif fold_freq > 0.4:
                        bluff_chance = 0.5 # Mix it up against average players
                    
                    if random.random() < bluff_chance:
                        return (PokerAction.BET, int(pot_size * 0.5))

                # Default action: give up if opponent shows aggression, otherwise check.
                return (PokerAction.FOLD, 0) if round_state.current_bet > 0 else (PokerAction.CHECK, 0)