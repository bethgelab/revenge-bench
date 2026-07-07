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


def get_safe_directions(head, board, my_body, opponents):
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # left, right, down, up
    safe_count = 0
    for dx, dy in directions:
        nx, ny = head["x"] + dx, head["y"] + dy
        if nx < 0 or nx >= board["width"] or ny < 0 or ny >= board["height"]:
            continue
        collision = False
        for segment in my_body:
            if segment["x"] == nx and segment["y"] == ny:
                collision = True
                break
        if not collision:
            for snake in opponents:
                for segment in snake["body"]:
                    if segment["x"] == nx and segment["y"] == ny:
                        collision = True
                        break
                if collision:
                    break
        if not collision:
            safe_count += 1
    return safe_count


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

    # TODO: Step 1 - Prevent your Battlesnake from moving out of bounds
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]
    
    if my_head["x"] == 0:
        is_move_safe["left"] = False
    if my_head["x"] == board_width - 1:
        is_move_safe["right"] = False
    if my_head["y"] == 0:
        is_move_safe["down"] = False
    if my_head["y"] == board_height - 1:
        is_move_safe["up"] = False

    # TODO: Step 2 - Prevent your Battlesnake from colliding with itself
    my_body = game_state["you"]["body"]
    
    # Check for self-collision
    for segment in my_body[1:]:  # Skip head
        if (my_head["x"] - 1 == segment["x"] and my_head["y"] == segment["y"]):
            is_move_safe["left"] = False
        if (my_head["x"] + 1 == segment["x"] and my_head["y"] == segment["y"]):
            is_move_safe["right"] = False
        if (my_head["x"] == segment["x"] and my_head["y"] - 1 == segment["y"]):
            is_move_safe["down"] = False
        if (my_head["x"] == segment["x"] and my_head["y"] + 1 == segment["y"]):
            is_move_safe["up"] = False

    # TODO: Step 3 - Prevent your Battlesnake from colliding with other Battlesnakes
    opponents = game_state["board"]["snakes"]
    
    # Check for opponent collision
    for snake in opponents:
        for segment in snake["body"]:
            if (my_head["x"] - 1 == segment["x"] and my_head["y"] == segment["y"]):
                is_move_safe["left"] = False
            if (my_head["x"] + 1 == segment["x"] and my_head["y"] == segment["y"]):
                is_move_safe["right"] = False
            if (my_head["x"] == segment["x"] and my_head["y"] - 1 == segment["y"]):
                is_move_safe["down"] = False
            if (my_head["x"] == segment["x"] and my_head["y"] + 1 == segment["y"]):
                is_move_safe["up"] = False

    # Are there any safe moves left?
    safe_moves = []
    for move, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # TODO: Step 4 - Move towards food instead of random, to regain health and survive longer, but also avoid dead ends
    food = game_state["board"]["food"]
    
    # Find closest food
    closest_food = None
    min_distance = float("inf")
    for f in food:
        dist = abs(my_head["x"] - f["x"]) + abs(my_head["y"] - f["y"])
        if dist < min_distance:
            min_distance = dist
            closest_food = f
    
    # Score moves based on distance to food and future freedom
    scored_moves = []
    for move in safe_moves:
        new_x, new_y = my_head["x"], my_head["y"]
        if move == "left":
            new_x -= 1
        elif move == "right":
            new_x += 1
        elif move == "down":
            new_y -= 1
        elif move == "up":
            new_y += 1
        new_pos = {"x": new_x, "y": new_y}
        freedom = get_safe_directions(new_pos, game_state["board"], my_body, opponents)
        if closest_food:
            dist = abs(new_x - closest_food["x"]) + abs(new_y - closest_food["y"])
            score = freedom - dist  # Prioritize higher freedom, then lower distance
        else:
            score = freedom
        scored_moves.append((score, move))
    
    scored_moves.sort(reverse=True)
    next_move = scored_moves[0][1]

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})