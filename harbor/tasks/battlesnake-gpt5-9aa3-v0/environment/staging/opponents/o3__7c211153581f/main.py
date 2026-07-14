# Simple but safer Battlesnake bot

import random
import typing

# Game metadata
def info() -> typing.Dict:
    return {
        "apiversion": "1",
        "author": "o3",          # Update with team/author name
        "color": "#33cccc",
        "head": "default",
        "tail": "default",
    }


def start(game_state: typing.Dict):
    print("GAME START")


def end(game_state: typing.Dict):
    print("GAME OVER\n")


# Direction helpers
DIRECTIONS = {
    "up": (0, 1),
    "down": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}


def add_coord(a, b):
    return {"x": a["x"] + b[0], "y": a["y"] + b[1]}


def manhattan(a, b):
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    you = game_state["you"]
    head = you["body"][0]

    board_width = board["width"]
    board_height = board["height"]

    # Build set of occupied squares (all snake bodies)
    occupied = set()
    for snake in board["snakes"]:
        for part in snake["body"]:
            occupied.add((part["x"], part["y"]))

    # Evaluate safe moves
    safe_moves = []
    for move_dir, delta in DIRECTIONS.items():
        next_head = add_coord(head, delta)
        x, y = next_head["x"], next_head["y"]

        # Wall collision
        if x < 0 or y < 0 or x >= board_width or y >= board_height:
            continue
        # Body collision (self or others)
        if (x, y) in occupied:
            continue
        safe_moves.append(move_dir)

    # If no safe moves, default to down (will likely die but unavoidable)
    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves, defaulting down")
        return {"move": "down"}

    # Choose move: head toward nearest food if possible, else random
    food = board["food"]
    if food:
        # Find closest food
        nearest_food = min(food, key=lambda f: manhattan(head, f))
        # Rank safe moves by resulting distance to food
        safe_moves.sort(key=lambda m: manhattan(add_coord(head, DIRECTIONS[m]), nearest_food))
        chosen = safe_moves[0]
    else:
        chosen = random.choice(safe_moves)

    print(f"MOVE {game_state['turn']}: {chosen}")
    return {"move": chosen}


# Local testing server entrypoint
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})