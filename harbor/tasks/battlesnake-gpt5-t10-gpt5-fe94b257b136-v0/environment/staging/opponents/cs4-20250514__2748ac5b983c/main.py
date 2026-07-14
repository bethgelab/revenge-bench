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


# info is called when you create your Battlesnake on play.battlesnake.com
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


def is_safe_move(head, move, board_width, board_height, my_body, opponents):
    """Check if a move is safe (no collisions, within bounds)"""
    # Calculate new head position
    new_head = {"x": head["x"], "y": head["y"]}
    
    if move == "up":
        new_head["y"] += 1
    elif move == "down":
        new_head["y"] -= 1
    elif move == "left":
        new_head["x"] -= 1
    elif move == "right":
        new_head["x"] += 1
    
    # Check boundaries
    if (new_head["x"] < 0 or new_head["x"] >= board_width or 
        new_head["y"] < 0 or new_head["y"] >= board_height):
        return False
    
    # Check self collision (avoid own body except tail which will move)
    for i, body_part in enumerate(my_body):
        if i == len(my_body) - 1:  # Skip tail as it will move
            continue
        if new_head["x"] == body_part["x"] and new_head["y"] == body_part["y"]:
            return False
    
    # Check opponent collisions
    for opponent in opponents:
        for body_part in opponent["body"]:
            if new_head["x"] == body_part["x"] and new_head["y"] == body_part["y"]:
                return False
    
    return True


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:
    """
    ROUND 15 STRATEGY: PURE CHAOS
    
    The opponent has adapted to ALL our strategies including the original Round 2 winner.
    Round 2: 614 points (original winner)
    Round 14: 250 points (pure Round 2 revert FAILED)
    
    Theory: Opponent has over-optimized against food-seeking behaviors.
    Solution: Complete chaos - ignore food entirely, move randomly among safe moves.
    This might work because it's the opposite of everything we've tried.
    """

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

    # Get board dimensions and game objects
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    my_body = game_state['you']['body']
    opponents = game_state['board']['snakes']

    # Check safety for each move
    for move_direction in is_move_safe:
        if is_move_safe[move_direction]:  # Only check moves that aren't backwards
            is_move_safe[move_direction] = is_safe_move(
                my_head, move_direction, board_width, board_height, my_body, opponents
            )

    # Are there any safe moves left?
    safe_moves = []
    for move_direction, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move_direction)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # PURE CHAOS STRATEGY: Completely ignore food, move randomly
    # This is the opposite of all our previous food-seeking strategies
    next_move = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: CHAOS MODE - Random move: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})