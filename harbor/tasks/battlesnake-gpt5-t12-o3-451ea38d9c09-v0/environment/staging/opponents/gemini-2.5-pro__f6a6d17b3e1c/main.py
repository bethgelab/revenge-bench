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
from logic import find_safe_moves, bfs, find_largest_safe_area


# info is called when you create your Battlesnake on play.battlesnake.com
# and controls your Battlesnake's appearance
# TIP: If you open your Battlesnake URL in a browser you should see this data
def info() -> typing.Dict:
    print("INFO")

    return {
        "apiversion": "1",
        "author": "gemini-2.5-pro",
        "color": "#00FF00",
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
    # Step 0: Acknowledge variables from game_state
    my_head = game_state["you"]["body"][0]
    my_body = game_state['you']['body']
    board_width = game_state['board']['width']

    # Step 1: Get all safe moves from the current position
    safe_moves = find_safe_moves(game_state)
    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Step 2: Strategic BFS Pathfinding
    # If hungry, find a path to the closest reachable food.
    if game_state['you']['health'] < 50: # Lowered hunger threshold
        food_items = sorted(game_state['board']['food'], key=lambda f: abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y']))
        for food in food_items:
            path = bfs(game_state, my_head, food)
            if path and len(path) > 1:
                next_step = path[1]
                move_to_target = ''
                if next_step['x'] > my_head['x']: move_to_target = 'right'
                elif next_step['x'] < my_head['x']: move_to_target = 'left'
                elif next_step['y'] > my_head['y']: move_to_target = 'up'
                else: move_to_target = 'down'
                
                if move_to_target in safe_moves:
                    print(f"MOVE {game_state['turn']}: Found safe path to food! Moving {move_to_target}")
                    return {"move": move_to_target}

    # If not hungry and we are very long, chase our tail to conserve space.
    if game_state['you']['length'] > (board_width / 2):
        my_tail = my_body[-1]
        path = bfs(game_state, my_head, my_tail)
        if path and len(path) > 1:
            next_step = path[1]
            move_to_target = ''
            if next_step['x'] > my_head['x']: move_to_target = 'right'
            elif next_step['x'] < my_head['x']: move_to_target = 'left'
            elif next_step['y'] > my_head['y']: move_to_target = 'up'
            else: move_to_target = 'down'
            
            if move_to_target in safe_moves:
                print(f"MOVE {game_state['turn']}: Healthy and long, chasing tail. Moving {move_to_target}")
                return {"move": move_to_target}

    # Step 3: Default Move - Flood Fill to find largest safe area
    # If no strategic move is made, find the move that leads to the most open space.
    move_area_sizes = {}
    for move in safe_moves:
        move_area_sizes[move] = find_largest_safe_area(game_state, move)
    
    # Choose the move that leads to the largest area.
    # If multiple moves have the same max area, pick one randomly.
    if move_area_sizes:
        max_area = -1
        best_moves = []
        # Sort moves to make random choice deterministic for testing if needed
        for move in sorted(move_area_sizes.keys()):
            area = move_area_sizes[move]
            if area > max_area:
                max_area = area
                best_moves = [move]
            elif area == max_area:
                best_moves.append(move)
        
        next_move = random.choice(best_moves)
        print(f"MOVE {game_state['turn']}: Defaulting to largest area ({max_area}). Moving {next_move}")
        return {"move": next_move}

    # Step 4: Fallback (should be rare)
    next_move = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: No ideal move, making random safe move: {next_move}")
    return {"move": next_move}

# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})