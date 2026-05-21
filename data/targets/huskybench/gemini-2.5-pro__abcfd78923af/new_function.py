def _track_opponent_fold_to_cbet(self, round_state: RoundStateClient):
        if not hasattr(round_state, 'action_sequence') or not round_state.action_sequence:
            return

        opponent_stats = self.opponent_model[str(self.opponent_id)]

        # 1. Identify the pre-flop aggressor
        preflop_aggressor = None
        preflop_actions = [a for a in round_state.action_sequence if a.get('round') == 1]
        for action in reversed(preflop_actions):
            if action.get('action') in ['RAISE', 'BET']:
                preflop_aggressor = action.get('player')
                break
        if preflop_aggressor is None:
            preflop_aggressor = round_state.big_blind_player_id

        # 2. Check if WE were the pre-flop aggressor
        if preflop_aggressor != self.player_id:
            return

        # 3. Check if WE made a C-Bet on the flop
        flop_actions = [a for a in round_state.action_sequence if a.get('round') == 2]
        my_cbet = any(a.get('player') == self.player_id and a.get('action') == 'BET' for a in flop_actions)

        if not my_cbet:
            return

        # 4. If we C-Bet, this is an opportunity for the opponent to fold
        opponent_stats['fold_to_cbet_opportunities'] += 1

        # 5. Check if the opponent folded on the flop
        opponent_folded = any(a.get('player') == self.opponent_id and a.get('action') == 'FOLD' for a in flop_actions)

        if opponent_folded:
            opponent_stats['fold_to_cbet_actions'] += 1