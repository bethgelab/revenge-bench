# Continuation Bet Logic
            opponent_id = [p_id for p_id in self.player_order if p_id != self.id][0]
            stats = self.opponent_stats[opponent_id]
            fold_to_cbet_rate = 0
            # Use stat only with a minimum sample size
            if stats['cbet_opportunities'] > 2:
                fold_to_cbet_rate = stats['cbet_fold_count'] / stats['cbet_opportunities']

            if self.was_preflop_aggressor and strength < 1 and round_state.current_bet == 0 and round_state.round == 'flop':
                # C-bet bluff against players who fold often, or if we have no info yet
                if fold_to_cbet_rate > 0.5 or stats['cbet_opportunities'] <= 2:
                    raise_amount = self._get_clamped_raise_amount(int(round_state.pot * 0.4), round_state, remaining_chips)
                    return PokerAction.RAISE, raise_amount