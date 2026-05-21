# Welcome to
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  | |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#
# This file can be a nice home for your Battlesnake logic and helper functions.
#
# To get you started we've included code to prevent your Battlesnake from moving backwards.
# For more info see docs.battlesnake.com

import random
import typing
import pathfinding
import flood_fill


# and controls your Battlesnake's appearance
# TIP: If you open your Battlesnake URL in a browser you should see this data
def info() -> typing.Dict:
    print("INFO")

    return {
        "apiversion": "1",
        "author": "",  # TODO: Your Battlesnake Username
        "color": "#888888",  # TODO: Choose color
        "head": "default",  # TODO: Choose head
        "tail": "default",  # TODO: Choose tail
    }


# start is called when your Battlesnake begins a game
def start(game_state: typing.Dict):
    print("GAME START")


# end is called when your Battlesnake finishes a game
def end(game_state: typing.Dict):
    print("GAME OVER\n")


def maximize_space(game_state: typing.Dict, potential_moves: typing.Dict, safe_moves: typing.List[str]) -> typing.Dict:
    """
    Uses flood fill to find the safe move that leads to the largest accessible area.
    """
    best_move = ""
    max_area = -1

    for move in safe_moves:
        next_pos = potential_moves[move]
        area = flood_fill.count_accessible_area(game_state, next_pos)
        if area > max_area:
            max_area = area
            best_move = move
    
    # If all safe moves lead to zero area (a trap), just pick one randomly to survive one more turn.
    if not best_move and safe_moves:
        best_move = random.choice(safe_moves)

    print(f"MOVE {game_state['turn']}: Chosen move {best_move} to maximize space with area: {max_area}")
    return {"move": best_move}


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:

    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    # We've included code to prevent your Battlesnake from moving backwards
    my_head = game_state["you"]["body"][0]  # Coordinates of your head
    my_neck = game_state["you"]["body"][1]  # Coordinates of your "neck"

    if my_neck["x"] < my_head["x"]:  # Neck is left of head, don't move left
        is_move_safe["left"] = False

    elif my_neck["x"] > my_head["x"]:  # Neck is right of head, don't move right
        is_move_safe["right"] = False

    elif my_neck["y"] < my_head["y"]:  # Neck is below head, don't move down
        is_move_safe["down"] = False

    elif my_neck["y"] > my_head["y"]:  # Neck is above head, don't move up
        is_move_safe["up"] = False

    # Step 1 - Prevent your Battlesnake from moving out of bounds
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    if my_head['x'] == board_width - 1:
        is_move_safe['right'] = False
    if my_head['x'] == 0:
        is_move_safe['left'] = False
    if my_head['y'] == board_height - 1:
        is_move_safe['up'] = False
    if my_head['y'] == 0:
        is_move_safe['down'] = False

    # Step 2 - Prevent your Battlesnake from colliding with itself
    my_body = game_state['you']['body']

    # Define potential next head positions
    potential_moves = {
        "up": {"x": my_head["x"], "y": my_head["y"] + 1},
        "down": {"x": my_head["x"], "y": my_head["y"] - 1},
        "left": {"x": my_head["x"] - 1, "y": my_head["y"]},
        "right": {"x": my_head["x"] + 1, "y": my_head["y"]},
    }

    # Check for self-collision
    for move, pos in potential_moves.items():
        if pos in my_body:
            is_move_safe[move] = False

    # Step 3 - Prevent your Battlesnake from colliding with other Battlesnakes
    opponents = game_state['board']['snakes']
    for opponent in opponents:
        for pos in opponent['body']:
            if pos in potential_moves.values():
                for move, move_pos in potential_moves.items():
                    if move_pos == pos:
                        is_move_safe[move] = False

    # Are there any safe moves left?
    safe_moves = []
    for move, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Step 4: Health-based Strategy
    my_health = game_state['you']['health']
    health_threshold = 75 # TUNE THIS VALUE

    # If health is high, prioritize controlling space
    if my_health > health_threshold:
        print(f"MOVE {game_state['turn']}: Health ({my_health}) is high, maximizing space.")
        return maximize_space(game_state, potential_moves, safe_moves)

    # If health is lower, prioritize food, then space
    else:
        print(f"MOVE {game_state['turn']}: Health ({my_health}) is low, seeking food.")
        # Move towards food using BFS
        food = game_state['board']['food']
        shortest_path = None

        # Find the shortest safe path to any food
        for a_food in food:
            path = pathfinding.find_path(game_state, my_head, a_food)
            if path:
                if shortest_path is None or len(path) < len(shortest_path):
                    shortest_path = path

        # If a path is found, move along it
        if shortest_path and len(shortest_path) > 1:
            next_step = shortest_path[1]  # The first element is the head itself
            move = ""
            
            # Determine the move direction from the next step in the path
            if next_step[0] > my_head['x']:
                move = "right"
            elif next_step[0] < my_head['x']:
                move = "left"
            elif next_step[1] > my_head['y']:
                move = "up"
            elif next_step[1] < my_head['y']:
                move = "down"

            if move in safe_moves:
                print(f"MOVE {game_state['turn']}: {move} (towards food via BFS)")
                return {"move": move}

        # Fallback to space control if no food path
        print(f"MOVE {game_state['turn']}: No path to food, falling back to maximizing space.")
        return maximize_space(game_state, potential_moves, safe_moves)


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})