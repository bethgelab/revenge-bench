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


def get_next_head(head, move):
    x, y = head['x'], head['y']
    if move == "up":
        y += 1
    elif move == "down":
        y -= 1
    elif move == "left":
        x -= 1
    elif move == "right":
        x += 1
    return {"x": x, "y": y}


def is_safe(next_head, width, height, my_body, opponents):
    # Check bounds
    if next_head['x'] < 0 or next_head['x'] >= width or next_head['y'] < 0 or next_head['y'] >= height:
        return False
    # Check self-collision
    for segment in my_body:
        if next_head == segment:
            return False
    # Check collision with other snakes
    for snake in opponents:
        for segment in snake['body']:
            if next_head == segment:
                return False
    return True


def get_direction(head, target):
    dx = target['x'] - head['x']
    dy = target['y'] - head['y']
    if abs(dx) > abs(dy):
        if dx > 0:
            return "right"
        else:
            return "left"
    else:
        if dy > 0:
            return "up"
        else:
            return "down"


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:
    my_head = game_state["you"]["body"][0]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    my_body = game_state['you']['body']
    opponents = game_state['board']['snakes']
    food = game_state['board']['food']

    possible_moves = ["up", "down", "left", "right"]
    safe_moves = []
    for move in possible_moves:
        next_head = get_next_head(my_head, move)
        if is_safe(next_head, board_width, board_height, my_body, opponents):
            safe_moves.append(move)

    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Move towards food if possible
    next_move = random.choice(safe_moves)
    if food:
        closest_food = min(food, key=lambda f: abs(f['x'] - my_head['x']) + abs(f['y'] - my_head['y']))
        target_dir = get_direction(my_head, closest_food)
        if target_dir in safe_moves:
            next_move = target_dir

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})