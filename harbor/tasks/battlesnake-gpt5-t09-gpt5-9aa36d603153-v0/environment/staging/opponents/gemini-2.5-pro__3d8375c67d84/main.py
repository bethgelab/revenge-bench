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
import logic

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

    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    # Prevent moving backwards
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]

    if my_neck["x"] < my_head["x"]:
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:
        is_move_safe["up"] = False

    # Prevent moving out of bounds
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    if my_head['x'] == 0:
        is_move_safe['left'] = False
    if my_head['x'] == board_width - 1:
        is_move_safe['right'] = False
    if my_head['y'] == 0:
        is_move_safe['up'] = False
    if my_head['y'] == board_height - 1:
        is_move_safe['down'] = False

    # Prevent colliding with myself
    my_body = game_state['you']['body']
    for move, is_safe in is_move_safe.items():
        if is_safe:
            next_pos = get_next_position(my_head, move)
            if next_pos in my_body:
                is_move_safe[move] = False

    # Prevent colliding with other snakes
    opponents = game_state['board']['snakes']
    for snake in opponents:
        if snake['id'] == game_state['you']['id']:
            continue
        for move, is_safe in is_move_safe.items():
            if is_safe:
                next_pos = get_next_position(my_head, move)
                # Head-on collision
                if len(snake['body']) >= len(my_body) and next_pos == snake['body'][0]:
                    is_move_safe[move] = False
                # Body collision
                if next_pos in snake['body'][1:]:
                    is_move_safe[move] = False

    safe_moves = [move for move, is_safe in is_move_safe.items() if is_safe]

    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves! Moving down")
        return {"move": "down"}

    # Score moves based on flood fill, food proximity, and wall hugging
    move_scores = {}
    food = game_state['board']['food']

    for move in safe_moves:
        next_pos = get_next_position(my_head, move)
        
        # Check if the next move is on food
        ate_food = next_pos in food

        # 1. Base score on available space (flood fill)
        space_score = logic.flood_fill(next_pos['x'], next_pos['y'], game_state, game_state['you'], ate_food)
        
        # 2. Add food bonus
        food_bonus = 0
        health_threshold = 50 

        if game_state['you']['health'] < health_threshold:
            max_food_score = 0
            if food:
                for f in food:
                    dist_to_food = abs(next_pos['x'] - f['x']) + abs(next_pos['y'] - f['y'])
                    if dist_to_food == 0:
                        dist_to_food = 0.5 # Prefer eating food over just moving next to it
                    
                    urgency = (health_threshold - game_state['you']['health'])
                    food_score = (1 / dist_to_food) * urgency * 2
                    if food_score > max_food_score:
                        max_food_score = food_score
                food_bonus = max_food_score
        else:
            # Gentle nudge towards all food on the board
            if food:
                for f in food:
                    dist = abs(next_pos['x'] - f['x']) + abs(next_pos['y'] - f['y'])
                    if dist > 0:
                        food_bonus += 1 / (dist * 2)
        
        move_scores[move] = space_score + food_bonus
        
        # 3. Add penalty for moving next to a larger snake's head
        opponent_head_penalty = 0
        for opponent in opponents:
            if opponent['id'] != game_state['you']['id'] and len(opponent['body']) >= len(my_body):
                opponent_head = opponent['body'][0]
                dist_to_opponent_head = abs(next_pos['x'] - opponent_head['x']) + abs(next_pos['y'] - opponent_head['y'])
                if dist_to_opponent_head == 1:
                    opponent_head_penalty = (board_width * board_height)
                    break
        move_scores[move] -= opponent_head_penalty

    # 4. Add wall-hugging bonus if we are the largest snake
    if logic.is_largest_snake(game_state):
        for move in safe_moves:
            next_pos = get_next_position(my_head, move)
            is_at_wall = (
                next_pos["x"] == 0 or
                next_pos["x"] == board_width - 1 or
                next_pos["y"] == 0 or
                next_pos["y"] == board_height - 1
            )
            if is_at_wall:
                wall_bonus = (board_width * board_height) / 4
                if move in move_scores:
                    move_scores[move] += wall_bonus

    if not move_scores:
        best_move = random.choice(safe_moves) if safe_moves else "down"
    else:
        best_move = max(move_scores, key=move_scores.get)
    
    print(f"MOVE {game_state['turn']}: {best_move} (Scores: {move_scores})")
    return {"move": best_move}

def get_next_position(current_pos, move):
    if move == 'up':
        return {'x': current_pos['x'], 'y': current_pos['y'] - 1}
    if move == 'down':
        return {'x': current_pos['x'], 'y': current_pos['y'] + 1}
    if move == 'left':
        return {'x': current_pos['x'] - 1, 'y': current_pos['y']}
    if move == 'right':
        return {'x': current_pos['x'] + 1, 'y': current_pos['y']}
    return current_pos

# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})