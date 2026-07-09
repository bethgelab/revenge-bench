def _get_opponent_fold_to_cbet_frequency(self) -> float:
        stats = self.opponent_model.get(str(self.opponent_id))
        if not stats or stats['fold_to_cbet_opportunities'] < 5:
            # Default assumption: opponents fold to cbets a reasonable amount of time.
            return 0.5
        return (stats['fold_to_cbet_actions'] / stats['fold_to_cbet_opportunities']) if stats['fold_to_cbet_opportunities'] > 0 else 0