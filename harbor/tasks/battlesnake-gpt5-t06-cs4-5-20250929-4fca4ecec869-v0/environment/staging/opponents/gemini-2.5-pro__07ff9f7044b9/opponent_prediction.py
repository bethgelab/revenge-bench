import typing as t

def get_possible_opponent_moves(game_state: t.Dict, opponent: t.Dict) -> t.Set[t.Dict[str, int]]:
    """
    Given an opponent, returns a set of possible safe moves they can make.
    "Safe" means not moving into a wall, their own body, or another snake's body.
    """
    possible_moves = set()
    head = opponent["head"]
    body = opponent["body"]
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]
    all_snakes = game_state["board"]["snakes"]

    moves = {
        "up": {"x": head["x"], "y": head["y"] + 1},
        "down": {"x": head["x"], "y": head["y"] - 1},
        "left": {"x": head["x"] - 1, "y": head["y"]},
        "right": {"x": head["x"] + 1, "y": head["y"]},
    }

    for move_name, next_head in moves.items():
        # Avoid walls
        if not (0 <= next_head["x"] < board_width and 0 <= next_head["y"] < board_height):
            continue

        is_safe = True
        # Avoid collision with any snake's body (including its own)
        for snake in all_snakes:
            # Don't need to check tail, it will move
            for segment in snake["body"][:-1]:
                if segment["x"] == next_head["x"] and segment["y"] == next_head["y"]:
                    is_safe = False
                    break
            if not is_safe:
                break
        
        if is_safe:
            # Using tuples of items to make the dict hashable for the set
            possible_moves.add(tuple(sorted(next_head.items())))

    # Convert set of tuples back to set of dicts
    return {dict(t) for t in possible_moves}

def get_threat_map(game_state: t.Dict) -> t.Dict[t.Tuple[int, int], int]:
    """
    Calculates all possible next head positions for all opponents.
    Returns a dictionary mapping (x, y) tuples to the length of the snake
    that can move there. If multiple snakes can move to the same square,
    it records the length of the LONGEST snake as the primary threat.
    """
    threat_map = {}
    opponents = game_state["board"]["snakes"]
    our_id = game_state["you"]["id"]

    for snake in opponents:
        if snake["id"] == our_id:
            continue
        
        opponent_length = snake["length"]
        possible_moves = get_possible_opponent_moves(game_state, snake)
        for move in possible_moves:
            coord = (move["x"], move["y"])
            
            # If coord is already a threat, only update if the new snake is longer
            if coord not in threat_map or opponent_length > threat_map[coord]:
                threat_map[coord] = opponent_length
            
    return threat_map