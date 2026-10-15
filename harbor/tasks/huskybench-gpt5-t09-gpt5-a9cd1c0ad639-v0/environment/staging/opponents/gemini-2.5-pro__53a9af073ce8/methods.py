def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        print("Player called get action")

        # Pre-flop logic
        if not round_state.community_cards:
            pair_rank = self.get_pair_rank()
            suited = self.is_suited()
            connector = self.is_connector()

            if pair_rank:
                raise_amount = self.blind_amount * 3 if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount
            
            if suited and connector:
                raise_amount = self.blind_amount * 4 if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount
            
            if suited:
                raise_amount = self.blind_amount * 3 if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount

            if connector:
                raise_amount = int(self.blind_amount * 2.5) if round_state.current_bet == 0 else round_state.current_bet * 3
                return PokerAction.RAISE, raise_amount

            if round_state.current_bet == 0:
                return PokerAction.CHECK, 0
            
            if round_state.current_bet > self.blind_amount:
                return PokerAction.FOLD, 0

            return PokerAction.CALL, 0
        
        # Post-flop logic
        else:
            evaluator = Evaluator()
            score = self.evaluate_hand(round_state)
            rank_class = evaluator.get_rank_class(score)

            # Three of a kind or better
            if rank_class <= self.THREE_OF_A_KIND:
                return PokerAction.RAISE, int(round_state.pot * 0.75)
            
            # Two pair
            elif rank_class == self.TWO_PAIR:
                return PokerAction.RAISE, int(round_state.pot * 0.5)

            # One pair
            elif rank_class == self.PAIR:
                if round_state.current_bet > (round_state.pot / 2):
                    return PokerAction.FOLD, 0
                
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                
                return PokerAction.CALL, 0
            
            # High card
            else:
                if round_state.current_bet == 0:
                    # 15% chance to bluff
                    if random.random() < 0.15:
                        return PokerAction.RAISE, int(round_state.pot * 0.5)
                    return PokerAction.CHECK, 0
                return PokerAction.FOLD, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """ Called at the end of the round. """
        print("Player called on end round")