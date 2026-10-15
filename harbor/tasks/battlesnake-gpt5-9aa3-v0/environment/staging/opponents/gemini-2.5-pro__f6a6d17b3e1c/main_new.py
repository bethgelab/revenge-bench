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
        "author": "gemini-2.5-pro",
        "color": "#00FF00",  # A nice green
        "head": "default",
        "tail": "default",
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

    # Step 0: Acknowledge variables from game_state
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]
    my_body = game_state['you']['body']
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    opponents = game_state['board']['snakes']
    food = game_state['board']['food']

    # Step 1: Prevent your Battlesnake from moving backwards
    if my_neck["x"] < my_head["x"]:  # Neck is left of head, don't move left
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:  # Neck is right of head, don't move right
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:  # Neck is below head, don't move down
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:  # Neck is above head, don't move up
        is_move_safe["up"] = False

    # Step 2: Prevent your Battlesnake from moving out of bounds
    if my_head['x'] == 0:
        is_move_safe['left'] = False
    if my_head['x'] == board_width - 1:
        is_move_safe['right'] = False
    if my_head['y'] == 0:
        is_move_safe['down'] = False
    if my_head['y'] == board_height - 1:
        is_move_safe['up'] = False

    # Step 3: Prevent your Battlesnake from colliding with itself
    body_parts = set()
    for part in my_body:
        body_parts.add((part['x'], part['y']))
    if (my_head['x'] - 1, my_head['y']) in body_parts:
        is_move_safe['left'] = False
    if (my_head['x'] + 1, my_head['y']) in body_parts:
        is_move_safe['right'] = False
    if (my_head['x'], my_head['y'] - 1) in body_parts:
        is_move_safe['down'] = False
    if (my_head['x'], my_head['y'] + 1) in body_parts:
        is_move_safe['up'] = False

    # Step 4: Prevent your Battlesnake from colliding with other Battlesnakes

    # Step 4.1: Prevent head-to-head collisions with larger/equal snakes
    my_length = game_state['you']['length']
    for snake in opponents:
        if snake['id'] != game_state['you']['id']:
            if len(snake['body']) >= my_length:
                opponent_head = snake['body'][0]
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] + 1) - opponent_head['y']) < 2:
                    is_move_safe['up'] = False
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] - 1) - opponent_head['y']) < 2:
                    is_move_safe['down'] = False
                if abs((my_head['x'] - 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) < 2:
                    is_move_safe['left'] = False
                if abs((my_head['x'] + 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) < 2:
                    is_move_safe['right'] = False
    opponent_bodies = set()
    for snake in opponents:
        if snake['id'] != game_state['you']['id']:
            for part in snake['body']:
                opponent_bodies.add((part['x'], part['y']))
    if (my_head['x'] - 1, my_head['y']) in opponent_bodies:
        is_move_safe['left'] = False
    if (my_head['x'] + 1, my_head['y']) in opponent_bodies:
        is_move_safe['right'] = False
    if (my_head['x'], my_head['y'] - 1) in opponent_bodies:
        is_move_safe['down'] = False
    if (my_head['x'], my_head['y'] + 1) in opponent_bodies:
        is_move_safe['up'] = False

    # Step 5: Are there any safe moves left?
    safe_moves = []
    for move, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Step 6: Choose a random move from the safe ones as a default
    next_move = random.choice(safe_moves)

    # Step 7: Overwrite default move with a better one if possible
    # If hungry, seek food.
    if game_state['you']['health'] < 50:
        if len(food) > 0:
            closest_food = None
            min_dist = float('inf')
            for f in food:
                dist = abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y'])
                if dist < min_dist:
                    min_dist = dist
                    closest_food = f
    
            if closest_food:
                food_moves = []
                dx = closest_food['x'] - my_head['x']
                dy = closest_food['y'] - my_head['y']

                preferred_moves = []
                alt_moves = []

                if abs(dx) > abs(dy):
                    if dx < 0:
                        preferred_moves.append('left')
                    else:
                        preferred_moves.append('right')
                    if dy < 0:
                        alt_moves.append('down')
                    else:
                        alt_moves.append('up')
                else:
                    if dy < 0:
                        preferred_moves.append('down')
                    else:
                        preferred_moves.append('up')
                    if dx < 0:
                        alt_moves.append('left')
                    else:
                        alt_moves.append('right')

                for move in preferred_moves:
                    if move in safe_moves:
                        food_moves.append(move)
                if len(food_moves) == 0:
                    for move in alt_moves:
                        if move in safe_moves:
                            food_moves.append(move)

                if len(food_moves) > 0:
                    next_move = food_moves[0]
    # If not hungry and long enough, follow tail.
    elif my_length > 3:
        my_tail = my_body[-1]
        tail_moves = []
        dx = my_tail['x'] - my_head['x']
        dy = my_tail['y'] - my_head['y']

        preferred_moves = []
        alt_moves = []

        if abs(dx) > abs(dy):
            if dx < 0:
                preferred_moves.append('left')
            else:
                preferred_moves.append('right')
            if dy < 0:
                alt_moves.append('down')
            else:
                alt_moves.append('up')
        else:
            if dy < 0:
                preferred_moves.append('down')
            else:
                preferred_moves.append('up')
            if dx < 0:
                alt_moves.append('left')
            else:
                alt_moves.append('right')

        for move in preferred_moves:
            if move in safe_moves:
                tail_moves.append(move)
        if len(tail_moves) == 0:
            for move in alt_moves:
                if move in safe_moves:
                    tail_moves.append(move)

        if len(tail_moves) > 0:
            next_move = tail_moves[0]
    # If not hungry and short, seek the center.
    else:
        center_x = board_width // 2
        center_y = board_height // 2
        center_moves = []
        dx = center_x - my_head['x']
        dy = center_y - my_head['y']

        preferred_moves = []
        alt_moves = []

        if abs(dx) > abs(dy):
            if dx < 0:
                preferred_moves.append('left')
            else:
                preferred_moves.append('right')
            if dy < 0:
                alt_moves.append('down')
            else:
                alt_moves.append('up')
        else:
            if dy < 0:
                preferred_moves.append('down')
            else:
                preferred_moves.append('up')
            if dx < 0:
                alt_moves.append('left')
            else:
                alt_moves.append('right')

        for move in preferred_moves:
            if move in safe_moves:
                center_moves.append(move)
        if len(center_moves) == 0:
            for move in alt_moves:
                if move in safe_moves:
                    center_moves.append(move)

        if len(center_moves) > 0:
            next_move = center_moves[0]

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})