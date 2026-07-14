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
from collections import deque


def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "claude-team",
        "color": "#4B0082",
        "head": "default",
        "tail": "default",
    }


def start(game_state: typing.Dict):
    print("GAME START")


def end(game_state: typing.Dict):
    print("GAME OVER\n")


def get_next_position(head: typing.Dict, move: str) -> typing.Dict:
    x, y = head["x"], head["y"]
    if move == "up":
        y += 1
    elif move == "down":
        y -= 1
    elif move == "left":
        x -= 1
    elif move == "right":
        x += 1
    return {"x": x, "y": y}


def is_out_of_bounds(pos: typing.Dict, board_width: int, board_height: int) -> bool:
    return pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height


def is_collision_with_snake(pos: typing.Dict, snake_body: typing.List[typing.Dict], exclude_tail: bool = True) -> bool:
    body_to_check = snake_body[:-1] if exclude_tail else snake_body
    return any(pos["x"] == segment["x"] and pos["y"] == segment["y"] for segment in body_to_check)


def manhattan_distance(pos1: typing.Dict, pos2: typing.Dict) -> int:
    return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])


def get_wall_penalty(pos: typing.Dict, board_width: int, board_height: int) -> float:
    x, y = pos["x"], pos["y"]
    dist_left = x
    dist_right = board_width - 1 - x
    dist_bottom = y
    dist_top = board_height - 1 - y
    min_wall_dist = min(dist_left, dist_right, dist_bottom, dist_top)
    is_near_corner = (
        (dist_left <= 1 and dist_bottom <= 1) or
        (dist_left <= 1 and dist_top <= 1) or
        (dist_right <= 1 and dist_bottom <= 1) or
        (dist_right <= 1 and dist_top <= 1)
    )
    is_on_edge = min_wall_dist == 0
    if is_near_corner:
        return -150.0
    elif is_on_edge:
        return -80.0
    elif min_wall_dist == 1:
        return -30.0
    else:
        return 0.0


def get_food_safety_score(food_pos: typing.Dict, board_width: int, board_height: int) -> float:
    x, y = food_pos["x"], food_pos["y"]
    dist_left = x
    dist_right = board_width - 1 - x
    dist_bottom = y
    dist_top = board_height - 1 - y
    min_wall_dist = min(dist_left, dist_right, dist_bottom, dist_top)
    is_in_corner = (
        (dist_left <= 0 and dist_bottom <= 0) or
        (dist_left <= 0 and dist_top <= 0) or
        (dist_right <= 0 and dist_bottom <= 0) or
        (dist_right <= 0 and dist_top <= 0)
    )
    is_near_corner = (
        (dist_left <= 1 and dist_bottom <= 1) or
        (dist_left <= 1 and dist_top <= 1) or
        (dist_right <= 1 and dist_bottom <= 1) or
        (dist_right <= 1 and dist_top <= 1)
    )
    is_on_edge = min_wall_dist == 0
    if is_in_corner:
        return 0.0
    elif is_near_corner:
        return 0.3
    elif is_on_edge:
        return 0.5
    elif min_wall_dist == 1:
        return 0.7
    else:
        return 1.0


def flood_fill(start_pos: typing.Dict, game_state: typing.Dict, max_depth: int = 50) -> int:
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    visited = set()
    queue = deque([start_pos])
    visited.add((start_pos['x'], start_pos['y']))
    occupied = set()
    for snake in game_state['board']['snakes']:
        for i, segment in enumerate(snake['body']):
            if i < len(snake['body']) - 1:
                occupied.add((segment['x'], segment['y']))
    count = 0
    while queue and count < max_depth:
        pos = queue.popleft()
        count += 1
        for move in ['up', 'down', 'left', 'right']:
            next_pos = get_next_position(pos, move)
            next_tuple = (next_pos['x'], next_pos['y'])
            if (is_out_of_bounds(next_pos, board_width, board_height) or
                next_tuple in visited or
                next_tuple in occupied):
                continue
            visited.add(next_tuple)
            queue.append(next_pos)
    return count


def move(game_state: typing.Dict) -> typing.Dict:
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]
    my_body = game_state["you"]["body"]
    my_health = game_state["you"]["health"]
    my_length = game_state["you"]["length"]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    if my_neck["x"] < my_head["x"]:
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:
        is_move_safe["up"] = False

    for move_direction in ["up", "down", "left", "right"]:
        if not is_move_safe[move_direction]:
            continue
        next_pos = get_next_position(my_head, move_direction)
        if is_out_of_bounds(next_pos, board_width, board_height):
            is_move_safe[move_direction] = False
            continue
        if is_collision_with_snake(next_pos, my_body, exclude_tail=True):
            is_move_safe[move_direction] = False
            continue
        for snake in game_state['board']['snakes']:
            if snake['id'] == game_state['you']['id']:
                continue
            if is_collision_with_snake(next_pos, snake['body'], exclude_tail=True):
                is_move_safe[move_direction] = False
                break
            snake_head = snake['body'][0]
            if manhattan_distance(next_pos, snake_head) == 1:
                if snake['length'] >= my_length:
                    is_move_safe[move_direction] = False
                    break

    safe_moves = [move for move, is_safe in is_move_safe.items() if is_safe]
    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    move_space = {}
    for move_direction in safe_moves:
        next_pos = get_next_position(my_head, move_direction)
        space = flood_fill(next_pos, game_state)
        move_space[move_direction] = space
    
    # NEW: Detect if we're trapped in a small space
    max_space = max(move_space.values())
    board_area = board_width * board_height
    is_trapped = max_space < board_area * 0.25  # Less than 25% of board accessible
    
    max_opponent_length = 0
    for snake in game_state['board']['snakes']:
        if snake['id'] != game_state['you']['id']:
            max_opponent_length = max(max_opponent_length, snake['length'])
    
    food = game_state['board']['food']
    length_difference = my_length - max_opponent_length
    is_critical = my_health < 30
    
    # NEW: More aggressive food seeking when behind in length
    should_seek_food = (
        is_critical or
        my_health < 50 or
        (length_difference <= 0 and my_health < 70) or
        (length_difference < -3 and my_health < 80)  # NEW: More aggressive when significantly behind
    )
    
    # NEW: If trapped, prioritize escape (space) over food unless critical
    if is_trapped and not is_critical:
        print(f"MOVE {game_state['turn']}: TRAPPED! Prioritizing escape (max_space={max_space})")
        move_scores = {}
        for move_direction in safe_moves:
            next_pos = get_next_position(my_head, move_direction)
            space_score = move_space[move_direction]
            wall_penalty = get_wall_penalty(next_pos, board_width, board_height)
            # Heavy emphasis on space when trapped
            move_scores[move_direction] = space_score * 2.0 + 0.15 * wall_penalty
        next_move = max(move_scores, key=move_scores.get)
    elif should_seek_food and food:
        if is_critical:
            target_food = min(food, key=lambda f: manhattan_distance(my_head, f))
        else:
            food_scores = {}
            for f in food:
                distance = manhattan_distance(my_head, f)
                safety = get_food_safety_score(f, board_width, board_height)
                # NEW: Reduce safety weight when behind in length
                safety_weight = 0.2 if length_difference < -3 else 0.3
                food_scores[tuple(f.items())] = -distance * (1.0 - safety_weight) + safety * 10 * safety_weight
            best_food_tuple = max(food_scores, key=food_scores.get)
            target_food = dict(best_food_tuple)
        
        if is_critical:
            food_weight = 0.70
            space_weight = 0.15
            wall_weight = 0.15
        else:
            food_weight = 0.55
            space_weight = 0.30
            wall_weight = 0.15
        
        move_scores = {}
        for move_direction in safe_moves:
            next_pos = get_next_position(my_head, move_direction)
            distance_score = -manhattan_distance(next_pos, target_food)
            space_score = move_space[move_direction] / 10.0
            wall_penalty = get_wall_penalty(next_pos, board_width, board_height)
            move_scores[move_direction] = (food_weight * distance_score + 
                                          space_weight * space_score + 
                                          wall_weight * wall_penalty)
        next_move = max(move_scores, key=move_scores.get)
    else:
        move_scores = {}
        for move_direction in safe_moves:
            next_pos = get_next_position(my_head, move_direction)
            space_score = move_space[move_direction]
            wall_penalty = get_wall_penalty(next_pos, board_width, board_height)
            move_scores[move_direction] = space_score + 0.15 * wall_penalty
        next_move = max(move_scores, key=move_scores.get)

    print(f"MOVE {game_state['turn']}: {next_move} (space: {move_space[next_move]}, health: {my_health}, len_diff: {length_difference})")
    return {"move": next_move}


if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})