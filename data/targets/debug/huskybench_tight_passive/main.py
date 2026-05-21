# Tight-Passive Poker Strategy - Simple Deterministic Strategy
#
# Rules (in order of priority):
# 1. Evaluate hand strength from hole cards + community cards
# 2. Fold weak hands, call medium hands, raise strong hands
# 3. Hand strength thresholds are fixed and deterministic
#
# Actions returned in canonical format:
#   FOLD, CHECK, CALL, or RAISE:<ratio>  (ratio = amount / my_stack, in (0, 1])
#
# This is a simple, fully deterministic strategy for testing
# that the inverse strategy pipeline can recover known rules.


# Card rank values for hand strength estimation
RANK_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}


def _parse_card(card_str):
    """Parse a card string like '7h' into (rank_value, suit)."""
    rank = card_str[:-1]
    suit = card_str[-1]
    return RANK_VALUES.get(rank, 0), suit


def _hand_strength(hole_cards, community_cards):
    """
    Estimate hand strength as a score from 0.0 to 1.0.

    Simple heuristic based on:
    - High cards (A, K, Q, J)
    - Pairs (hole pair, or pair with board)
    - Suited cards
    - Connectedness (close ranks)
    """
    if not hole_cards or len(hole_cards) < 2:
        return 0.0

    r1, s1 = _parse_card(hole_cards[0])
    r2, s2 = _parse_card(hole_cards[1])

    score = 0.0

    # High card bonus (each high card adds value)
    for r in (r1, r2):
        if r >= 14:  # Ace
            score += 0.25
        elif r >= 13:  # King
            score += 0.20
        elif r >= 12:  # Queen
            score += 0.15
        elif r >= 11:  # Jack
            score += 0.10
        elif r >= 10:  # Ten
            score += 0.05

    # Pocket pair bonus
    if r1 == r2:
        score += 0.30
        if r1 >= 11:  # High pocket pair
            score += 0.15

    # Suited bonus
    if s1 == s2:
        score += 0.05

    # Connectedness bonus (close ranks)
    gap = abs(r1 - r2)
    if gap == 1:
        score += 0.05
    elif gap == 0:
        pass  # Already counted as pair
    elif gap == 2:
        score += 0.02

    # Board interaction (if community cards are dealt)
    all_ranks = [r1, r2]
    all_suits = [s1, s2]
    for card in community_cards:
        cr, cs = _parse_card(card)
        all_ranks.append(cr)
        all_suits.append(cs)

    if community_cards:
        # Pair with board
        board_ranks = [_parse_card(c)[0] for c in community_cards]
        for hr in (r1, r2):
            if hr in board_ranks:
                score += 0.20
                if hr >= 11:  # High pair with board
                    score += 0.10

        # Two pair or trips
        from collections import Counter
        rank_counts = Counter(all_ranks)
        pairs = sum(1 for c in rank_counts.values() if c == 2)
        trips = sum(1 for c in rank_counts.values() if c >= 3)
        if trips > 0:
            score += 0.30
        elif pairs >= 2:
            score += 0.15

        # Flush draw or flush
        suit_counts = Counter(all_suits)
        max_suit = max(suit_counts.values())
        if max_suit >= 5:
            score += 0.35  # Flush
        elif max_suit == 4:
            score += 0.10  # Flush draw

    return min(score, 1.0)


def move(game_state):
    """
    Tight-passive strategy with deterministic thresholds.

    Decision logic:
    - hand_strength < 0.15: FOLD (unless free check)
    - hand_strength < 0.30: CHECK if possible, else FOLD
    - hand_strength < 0.50: CALL (or CHECK)
    - hand_strength < 0.70: RAISE ~0.3x pot  (ratio = 0.3 * pot / my_stack)
    - hand_strength < 0.85: RAISE ~1.0x pot  (ratio = pot / my_stack)
    - hand_strength >= 0.85: RAISE ~2.0x pot  (ratio = 2.0 * pot / my_stack)

    Returns canonical action strings:
        "FOLD", "CHECK", "CALL", or "RAISE:<ratio>" where ratio = amount / my_stack.
    """
    hole_cards = game_state.get("hole_cards", [])
    community_cards = game_state.get("community_cards", [])
    current_bet = game_state.get("current_bet", 0)
    my_stack = game_state.get("my_stack", 10000)
    pot = game_state.get("pot", 0)

    strength = _hand_strength(hole_cards, community_cards)

    # Can we check (no bet to call)?
    can_check = current_bet == 0

    if strength < 0.15:
        if can_check:
            return "CHECK"
        return "FOLD"
    elif strength < 0.30:
        if can_check:
            return "CHECK"
        return "FOLD"
    elif strength < 0.50:
        if can_check:
            return "CHECK"
        return "CALL"
    else:
        return _raise_action(strength, pot, my_stack)


def _raise_action(strength, pot, my_stack):
    """Compute a raise in canonical RAISE:<ratio> format.

    Ratio = amount / my_stack, clamped to (0, 1].
    """
    effective_pot = max(pot, 1)
    if strength < 0.70:
        amount = max(int(effective_pot * 0.3), 1)
    elif strength < 0.85:
        amount = max(effective_pot, 1)
    else:
        amount = max(int(effective_pot * 2.0), 1)

    if my_stack > 0:
        ratio = min(amount / my_stack, 1.0)
    else:
        ratio = 1.0  # all-in if no stack left
    return f"RAISE:{ratio:.4f}"
