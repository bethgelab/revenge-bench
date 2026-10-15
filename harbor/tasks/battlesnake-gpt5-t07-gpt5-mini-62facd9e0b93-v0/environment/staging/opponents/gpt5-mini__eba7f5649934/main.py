#!/usr/bin/env python3
import random
import typing

# info is called when you create your Battlesnake on play.battlesnake.com
# and controls your Battlesnake's appearance
def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "",  # TODO: Your Battlesnake Username
        "color": "#888888",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

def _get_next_coord(head: typing.Dict, move: str) -> typing.Dict:
    if move == "up":
        return {"x": head["x"], "y": head["y"] + 1}
    if move == "down":
        return {"x": head["x"], "y": head["y"] - 1}
    if move == "left":
        return {"x": head["x"] - 1, "y": head["y"]}
    if move == "right":
        return {"x": head["x"] + 1, "y": head["y"]}
    return head

def _manhattan(a: typing.Dict, b: typing.Dict) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    my_body = game_state["you"]["body"]
    my_head = my_body[0]
    my_neck = my_body[1] if len(my_body) > 1 else None
    my_length = len(my_body)

    width = board["width"]
    height = board["height"]

    # Start with all moves allowed, then rule out unsafe ones
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    # Prevent moving backwards into neck
    if my_neck:
        if my_neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    # Helper: check out of bounds
    def _out_of_bounds(coord: typing.Dict) -> bool:
        return coord["x"] < 0 or coord["x"] >= width or coord["y"] < 0 or coord["y"] >= height

    # Build a set of occupied coordinates by snakes (excluding the tail of snakes could be allowed
    # because tails may move, but for safety we treat all body parts as obstacles)
    occupied = set()
    for snake in board.get("snakes", []):
        for segment in snake.get("body", []):
            occupied.add((segment["x"], segment["y"]))

    # Consider opponent heads for head-to-head collisions
    opponent_heads = []
    for snake in board.get("snakes", []):
        if snake.get("id") != game_state["you"].get("id"):
            opponent_heads.append({"head": snake["body"][0], "length": len(snake.get("body", []))})

    # Evaluate each potential move
    for mv in list(is_move_safe.keys()):
        if not is_move_safe[mv]:
            continue
        next_coord = _get_next_coord(my_head, mv)

        # Out of bounds
        if _out_of_bounds(next_coord):
            is_move_safe[mv] = False
            continue

        # Collision with any body
        if (next_coord["x"], next_coord["y"]) in occupied:
            is_move_safe[mv] = False
            continue

        # Don't move into positions that are adjacent to an opponent head if they are
        # equal or longer (risk of head-to-head collision). If opponent is shorter,
        # moving there could be advantageous.
        for opp in opponent_heads:
            opp_head = opp["head"]
            opp_len = opp["length"]
            if _manhattan(next_coord, opp_head) == 0:
                # If the opponent's head would be on the same square, then head-to-head
                # resolve by length: if opponent length >= ours it's unsafe.
                if opp_len >= my_length:
                    is_move_safe[mv] = False
                    break

    # Collect safe moves
    safe_moves = [m for m, ok in is_move_safe.items() if ok]

    if not safe_moves:
        # No safe moves detected - choose a move to minimize immediate danger (prefer not backwards)
        fallback = random.choice(list(is_move_safe.keys()))
        print(f"MOVE {game_state['turn']}: No safe moves detected! Falling back to {fallback}")
        return {"move": fallback}

    # Prefer moves that get us closer to the nearest food
    foods = board.get("food", [])
    if foods:
        # Find nearest food by Manhattan distance
        nearest = min(foods, key=lambda f: _manhattan(f, my_head))
        # Score safe moves by resulting distance to the nearest food
        best_moves = []
        best_dist = None
        for mv in safe_moves:
            coord = _get_next_coord(my_head, mv)
            dist = _manhattan(coord, nearest)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_moves = [mv]
            elif dist == best_dist:
                best_moves.append(mv)
        next_move = random.choice(best_moves)
        print(f"MOVE {game_state['turn']}: Moving toward food at {nearest} via {next_move}")
        return {"move": next_move}

    # Otherwise choose a random safe move
    next_move = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: No food found - choosing safe move {next_move}")
    return {"move": next_move}

# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})