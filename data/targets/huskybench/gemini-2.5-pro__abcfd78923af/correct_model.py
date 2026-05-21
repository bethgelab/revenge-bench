if str(self.opponent_id) not in self.opponent_model:
            self.opponent_model[str(self.opponent_id)] = {
                'hands_played': 0,
                'vpip_opportunities': 0,
                'vpip_actions': 0,
                'pfr_opportunities': 0,
                'pfr_actions': 0,
                'cbet_opportunities': 0,
                'cbet_actions': 0,
                'fold_to_cbet_opportunities': 0,
                'fold_to_cbet_actions': 0
            }