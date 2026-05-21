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
    
    if my_head["x"] == 0:  # Head is at left edge, don't move left
        is_move_safe["left"] = False
        
    if my_head["x"] == board_width - 1:  # Head is at right edge, don't move right
        is_move_safe["right"] = False
        
    if my_head["y"] == 0:  # Head is at bottom edge, don't move down
        is_move_safe["down"] = False
        
    if my_head["y"] == board_height - 1:  # Head is at top edge, don't move up
        is_move_safe["up"] = False

    # Step 2 - Prevent your Battlesnake from colliding with itself
    my_body = game_state['you']['body']
    
    # Calculate potential next head positions for each move
    my_next_head = {
        "up": {"x": my_head["x"], "y": my_head["y"] + 1},
        "down": {"x": my_head["x"], "y": my_head["y"] - 1},
        "left": {"x": my_head["x"] - 1, "y": my_head["y"]},
        "right": {"x": my_head["x"] + 1, "y": my_head["y"]}
    }
    
    for move in ["up", "down", "left", "right"]:
        if is_move_safe[move]:
            # Check if the next head position would collide with any part of the body
            for body_part in my_body[:-1]:  # Exclude tail since it will move
                if my_next_head[move]["x"] == body_part["x"] and my_next_head[move]["y"] == body_part["y"]:
                    is_move_safe[move] = False
                    break

    # Step 3 - Prevent your Battlesnake from colliding with other Battlesnakes
    opponents = game_state['board']['snakes']
    
    for move in ["up", "down", "left", "right"]:
        if is_move_safe[move]:
            # Check if the next head position would collide with any opponent snake
            for snake in opponents:
                if snake["id"] == game_state["you"]["id"]:  # Skip our own snake
                    continue
                    
                # Check collision with opponent body (excluding their tail since it will move)
                for body_part in snake["body"][:-1]:
                    if my_next_head[move]["x"] == body_part["x"] and my_next_head[move]["y"] == body_part["y"]:
                        is_move_safe[move] = False
                        break
                        
                if not is_move_safe[move]:
                    break
                    
                # Check potential head-to-head collision
                opponent_head = snake["body"][0]
                if (my_next_head[move]["x"] == opponent_head["x"] and 
                    my_next_head[move]["y"] == opponent_head["y"]):
                    # Only allow head-to-head if we're longer than the opponent
                    if len(my_body) <= len(snake["body"]):
                        is_move_safe[move] = False
                        break

    # Are there any safe moves left?
    safe_moves = []
    for move, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Step 4 - Move towards food instead of random, to regain health and survive longer
    food = game_state['board']['food']
    
    if len(food) > 0:
        # Find the closest food
        my_head = game_state["you"]["body"][0]
        closest_food = food[0]
        min_distance = abs(my_head["x"] - food[0]["x"]) + abs(my_head["y"] - food[0]["y"])
        
        for f in food:
            distance = abs(my_head["x"] - f["x"]) + abs(my_head["y"] - f["y"])
            if distance < min_distance:
                min_distance = distance
                closest_food = f
        
        # Calculate potential moves that get closer to food
        preferred_moves = []
        current_distance = abs(my_head["x"] - closest_food["x"]) + abs(my_head["y"] - closest_food["y"])
        
        for move in safe_moves:
            new_distance = abs(my_next_head[move]["x"] - closest_food["x"]) + abs(my_next_head[move]["y"] - closest_food["y"])
            if new_distance < current_distance:
                preferred_moves.append(move)
        
        # If there are preferred moves toward food, choose from those
        if len(preferred_moves) > 0:
            next_move = random.choice(preferred_moves)
        else:
            # Otherwise, choose a random safe move
            next_move = random.choice(safe_moves)
    else:
        # If no food is available, choose a random safe move
        next_move = random.choice(safe_moves)

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})