def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        print("Player called get action")
        print(f"Round state for analysis: {round_state}") # Added for opponent modeling
        self.update_opponent_stats(round_state)

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

            # Very Strong Hands (Full House or better)
            if rank_class <= self.FULL_HOUSE:
                raise_amount = round_state.pot
                return PokerAction.RAISE, raise_amount

            # Strong Hands (Flush or Straight)
            elif rank_class <= self.STRAIGHT:
                raise_amount = max(self.blind_amount, int(round_state.pot * 0.75))
                return PokerAction.RAISE, raise_amount

            # Three of a kind
            elif rank_class == self.THREE_OF_A_KIND:
                raise_amount = max(self.blind_amount, int(round_state.pot * 0.60))
                return PokerAction.RAISE, raise_amount
            
            # Two pair
            elif rank_class == self.TWO_PAIR:
                raise_amount = max(self.blind_amount, int(round_state.pot * 0.5))
                return PokerAction.RAISE, raise_amount

            # One pair
            elif rank_class == self.PAIR:
                if round_state.current_bet > (round_state.pot / 2):
                    return PokerAction.FOLD, 0
                
                if round_state.current_bet == 0:
                    return PokerAction.CHECK, 0
                
                return PokerAction.CALL, 0
            
            # High card
            else:
                has_flush_draw = self.has_flush_draw(round_state)
                has_straight_draw = self.has_straight_draw(round_state)

                if has_flush_draw or has_straight_draw:
                    # Semi-bluff if no bet
                    if round_state.current_bet == 0:
                        raise_amount = max(self.blind_amount, int(round_state.pot * 0.5))
                        return PokerAction.RAISE, raise_amount
                    # Facing a bet, calculate pot odds or re-raise
                    else:
                        # Don't call if the bet is too large (e.g., all-in)
                        if round_state.current_bet >= remaining_chips:
                            return PokerAction.FOLD, 0

                        # Semi-bluff re-raise with a 30% chance
                        if random.random() < 0.3:
                            raise_amount = round_state.current_bet * 3
                            return PokerAction.RAISE, raise_amount

                        pot_odds = round_state.current_bet / (round_state.pot + round_state.current_bet)
                        
                        outs = 0
                        if has_flush_draw:
                            outs = 9
                        elif has_straight_draw:
                            outs = 8
                        
                        num_community_cards = len(round_state.community_cards)
                        equity = 0
                        # We are only guaranteed to see the next card
                        if num_community_cards == 3: # Flop
                            equity = outs / 47 
                        elif num_community_cards == 4: # Turn
                            equity = outs / 46

                        if equity > pot_odds:
                            return PokerAction.CALL, 0
                        else:
                            return PokerAction.FOLD, 0
                
                # No draw, high card logic
                if round_state.current_bet == 0:
                    # Bluff heads-up with a 15% chance
                    if sum(1 for action in round_state.player_actions.values() if action != 'fold') == 2 and random.random() < 0.15:
                        raise_amount = max(.blind_amount, int(round_state.pot * 0.5))
                        return PokerAction.RAISE, raise_amount
                    return PokerAction.CHECK, 0
                return PokerAction.FOLD, 0