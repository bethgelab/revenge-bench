def _track_opponent_preflop_stats(self, round_state: RoundStateClient):
        """Tracks opponent's VPIP and PFR actions for the current hand."""
        # Ensure this runs only once per hand, pre-flop, and if the action sequence exists
        if round_state.round_num != 1 or not hasattr(round_state, 'action_sequence'):
            return

        opponent_stats = self.opponent_model[str(self.opponent_id)]
        
        # --- PFR Opportunity Tracking ---
        if not self.hand_pfr_opportunity_tracked:
            pre_opponent_actions = []
            for action in round_state.action_sequence:
                if action.get('round') == 1:
                    if action.get('player') == self.opponent_id:
                        break # Stop when we reach the opponent's first action
                    pre_opponent_actions.append(action)
            
            # A PFR opportunity exists if no one raised before the opponent
            is_pfr_opportunity = not any(a.get('action') == 'RAISE' for a in pre_opponent_actions)
            
            if is_pfr_opportunity:
                opponent_stats['pfr_opportunities'] += 1
            
            self.hand_pfr_opportunity_tracked = True

        # --- VPIP and PFR Action Tracking ---
        if not self.hand_vpip_tracked:
            is_opponent_bb = (round_state.big_blind_player_id == self.opponent_id)
            
            for action in round_state.action_sequence:
                if action.get('player') == self.opponent_id and action.get('round') == 1:
                    action_type = action.get('action')
                    
                    # VPIP action is any voluntary money put in the pot.
                    # A BB checking their option is not voluntary.
                    is_bb_check = is_opponent_bb and action_type == 'CHECK'
                    
                    if action_type in ['CALL', 'RAISE', 'BET'] and not is_bb_check:
                        opponent_stats['vpip_actions'] += 1
                        # PFR action is a raise or bet on their first voluntary action
                        if action_type in ['RAISE', 'BET']:
                            opponent_stats['pfr_actions'] += 1
                        self.hand_vpip_tracked = True
                        break 
                    elif action_type == 'FOLD':
                        # Folding is a voluntary action that ends tracking for the hand
                        self.hand_vpip_tracked = True
                        break