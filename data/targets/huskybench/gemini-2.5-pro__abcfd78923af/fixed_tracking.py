def _get_opponent_river_aggression_frequency(self) -> float:
        stats = self.opponent_model.get(str(self.opponent_id))
        if not stats or stats['river_bet_opportunities'] < 2: # Lowered sample size for final round
            return 0.3 # Default assumption: people are more cautious on the river
        return (stats['river_bet_actions'] / stats['river_bet_opportunities']) if stats['river_bet_opportunities'] > 0 else 0

    def _get_opponent_fold_to_river_bet_frequency(self) -> float:
        stats = self.opponent_model.get(str(self.opponent_id))
        if not stats or stats['fold_to_river_bet_opportunities'] < 2: # Lowered sample size
            return 0.4 # Default assumption
        return (stats['fold_to_river_bet_actions'] / stats['fold_to_river_bet_opportunities']) if stats['fold_to_river_bet_opportunities'] > 0 else 0

    def _track_opponent_river_bet(self, round_state: RoundStateClient):
        if self.hand_river_bet_tracked or not hasattr(round_state, 'action_sequence'):
            return
        
        opponent_stats = self.opponent_model[str(self.opponent_id)]
        
        # Find the index of our last action on the river
        my_last_river_action_index = -1
        for i in range(len(round_state.action_sequence) - 1, -1, -1):
            action = round_state.action_sequence[i]
            if action.get('round') == 4 and action.get('player') == self.player_id:
                my_last_river_action_index = i
                break
        
        # If we checked, it's an opportunity for the opponent to bet
        if my_last_river_action_index != -1 and round_state.action_sequence[my_last_river_action_index].get('action') == 'CHECK':
            # Look for the opponent's action immediately after ours
            for i in range(my_last_river_action_index + 1, len(round_state.action_sequence)):
                action = round_state.action_sequence[i]
                if action.get('player') == self.opponent_id:
                    opponent_stats['river_bet_opportunities'] += 1
                    if action.get('action') in ['BET', 'RAISE']:
                        opponent_stats['river_bet_actions'] += 1
                    self.hand_river_bet_tracked = True
                    return # Stop after finding their action

    def _track_opponent_fold_to_river_bet(self, round_state: RoundStateClient):
        if self.hand_fold_to_river_bet_tracked or not hasattr(round_state, 'action_sequence'):
            return

        opponent_stats = self.opponent_model[str(self.opponent_id)]
        
        # Find the index of our last bet/raise on the river
        my_last_bet_index = -1
        for i in range(len(round_state.action_sequence) - 1, -1, -1):
            action = round_state.action_sequence[i]
            if action.get('round') == 4 and action.get('player') == self.player_id and action.get('action') in ['BET', 'RAISE']:
                my_last_bet_index = i
                break

        if my_last_bet_index != -1:
            opponent_stats['fold_to_river_bet_opportunities'] += 1
            # Check if opponent folded after our bet
            folded = False
            for i in range(my_last_bet_index + 1, len(round_state.action_sequence)):
                action = round_state.action_sequence[i]
                if action.get('player') == self.opponent_id:
                    if action.get('action') == 'FOLD':
                        folded = True
                    break # Found opponent's reaction
            
            if folded:
                opponent_stats['fold_to_river_bet_actions'] += 1
            self.hand_fold_to_river_bet_tracked = True