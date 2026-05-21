# Greedy Food Chaser - Simple Deterministic Strategy
#
# Rules (in order of priority):
# 1. Avoid death: don't move into walls, own body, or other snakes
# 2. Chase nearest food by Manhattan distance
# 3. Tie-breaker: prefer right > down > left > up
#
# This is a simple, fully deterministic strategy for testing
# that the inverse strategy pipeline can recover known rules.

import typing


def info() -> typing.Dict:
    return {
        "apiversion": "1",
        "author": "greedy_food",
        "color": "#00FF00",
        "head": "default",
        "tail": "default",
    }


def start(game_state: typing.Dict):
    pass


def end(game_state: typing.Dict):
    pass


def _get_next_pos(head: dict, move: str) -> dict:
    """Get the position after making a move."""
    if move == "up":
        return {"x": head["x"], "y": head["y"] + 1}
    elif move == "down":
        return {"x": head["x"], "y": head["y"] - 1}
    elif move == "left":
        return {"x": head["x"] - 1, "y": head["y"]}
    elif move == "right":
        return {"x": head["x"] + 1, "y": head["y"]}
    return head


def _is_safe(pos: dict, game_state: dict) -> bool:
    """Check if a position is safe (not wall, not snake body)."""
    board = game_state["board"]
    width = board["width"]
    height = board["height"]
    
    # Check bounds
    if pos["x"] < 0 or pos["x"] >= width:
        return False
    if pos["y"] < 0 or pos["y"] >= height:
        return False
    
    # Check collision with any snake body (including self)
    for snake in board["snakes"]:
        # Don't check the tail tip - it will move
        body = snake["body"][:-1]
        for segment in body:
            if pos["x"] == segment["x"] and pos["y"] == segment["y"]:
                return False
    
    return True


def _manhattan_distance(p1: dict, p2: dict) -> int:
    """Calculate Manhattan distance between two points."""
    return abs(p1["x"] - p2["x"]) + abs(p1["y"] - p2["y"])


def move(game_state: typing.Dict) -> typing.Dict:
    """
    Greedy food chaser with deterministic tie-breaking.
    
    Priority:
    1. Only consider safe moves
    2. Among safe moves, pick the one that minimizes distance to nearest food
    3. Tie-breaker order: right > down > left > up
    """
    my_head = game_state["you"]["body"][0]
    
    # Deterministic move order for tie-breaking: right > down > left > up
    move_priority = ["right", "down", "left", "up"]
    
    # Find safe moves
    safe_moves = []
    for m in move_priority:
        next_pos = _get_next_pos(my_head, m)
        if _is_safe(next_pos, game_state):
            safe_moves.append(m)
    
    # If no safe moves, just go down (will die anyway)
    if not safe_moves:
        return {"move": "down"}
    
    # Find nearest food
    foods = game_state["board"].get("food", [])
    
    if not foods:
        # No food - just pick first safe move (follows priority order)
        return {"move": safe_moves[0]}
    
    # Find the nearest food
    nearest_food = None
    nearest_dist = float("inf")
    for food in foods:
        dist = _manhattan_distance(my_head, food)
        if dist < nearest_dist:
            nearest_dist = dist
            nearest_food = food
    
    # Among safe moves, pick the one that gets closest to nearest food
    best_move = safe_moves[0]
    best_dist = float("inf")
    
    for m in safe_moves:
        next_pos = _get_next_pos(my_head, m)
        dist = _manhattan_distance(next_pos, nearest_food)
        if dist < best_dist:
            best_dist = dist
            best_move = m
        # Note: tie-breaking is automatic since we iterate in priority order
        # and only update on strictly less than
    
    return {"move": best_move}


# Server entry point
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})
