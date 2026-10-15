# Improved Battlesnake for round 1
# - avoids walls, self-collisions, and other snakes' bodies
# - moves toward nearest food (Manhattan distance) when safe
# - falls back to a random safe move

import random
import typing

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

def _move_coords(head: typing.Dict, move: str) -> typing.Dict:
    x, y = head["x"], head["y"]
    if move == "up":
        return {"x": x, "y": y + 1}
    if move == "down":
        return {"x": x, "y": y - 1}
    if move == "left":
        return {"x": x - 1, "y": y}
    if move == "right":
        return {"x": x + 1, "y": y}
    return {"x": x, "y": y}

def _manhattan(a: typing.Dict, b: typing.Dict) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def move(game_state: typing.Dict) -> typing.Dict:
    # Possible moves
    moves = ["up", "down", "left", "right"]
    is_move_safe = {m: True for m in moves}

    board = game_state.get("board", {})
    width = board.get("width", 0)
    height = board.get("height", 0)

    you = game_state.get("you", {})
    my_body = you.get("body", [])
    if not my_body:
        # Fallback: choose a random move
        next_move = random.choice(moves)
        print(f"MOVE {game_state.get('turn')}: No body info, moving {next_move}")
        return {"move": next_move}

    my_head = my_body[0]
    # Prevent moving backwards: if we have a neck (len > 1)
    if len(my_body) > 1:
        my_neck = my_body[1]
        if my_neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    # Build a set of occupied coordinates (other snakes and our body)
    occupied = set()
    snakes = board.get("snakes", [])
    for s in snakes:
        for segment in s.get("body", []):
            occupied.add((segment["x"], segment["y"]))

    # Optionally, we could allow moving into our own tail (last segment)
    # because the tail will move, but to keep behavior safe across all opponents
    # we'll avoid all currently occupied squares.

    # Check each move for wall collisions and body collisions
    for m in list(is_move_safe.keys()):
        if not is_move_safe[m]:
            continue
        new_head = _move_coords(my_head, m)
        nx, ny = new_head["x"], new_head["y"]
        # Out of bounds
        if nx < 0 or nx >= width or ny < 0 or ny >= height:
            is_move_safe[m] = False
            continue
        # Collides with any occupied cell
        if (nx, ny) in occupied:
            is_move_safe[m] = False
            continue

    safe_moves = [m for m, ok in is_move_safe.items() if ok]

    if not safe_moves:
        # No safe moves detected; choose "down" as a last resort (as in example)
        print(f"MOVE {game_state.get('turn')}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Move towards the nearest food if possible
    food = board.get("food", [])
    if food:
        # For each potential safe move, compute the distance to the closest food
        best_moves = []
        best_dist = None
        for m in safe_moves:
            new_head = _move_coords(my_head, m)
            # distance to nearest food
            dist = min(_manhattan(new_head, f) for f in food)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_moves = [m]
            elif dist == best_dist:
                best_moves.append(m)
        next_move = random.choice(best_moves)
    else:
        # No food on board; pick a random safe move
        next_move = random.choice(safe_moves)

    print(f"MOVE {game_state.get('turn')}: {next_move}")
    return {"move": next_move}

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})