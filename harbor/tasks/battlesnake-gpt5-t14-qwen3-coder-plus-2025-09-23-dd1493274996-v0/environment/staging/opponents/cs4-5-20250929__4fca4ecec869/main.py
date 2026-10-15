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


# info is called when you create your Battlesnake on play.battlesnake.com
# and controls your Battlesnake's appearance
# TIP: If you open your Battlesnake URL in a browser you should see this data
def info() -> typing.Dict:
    print("INFO")

    return {
        "apiversion": "1",
        "author": "claude-sonnet-4-5",
        "color": "#4169E1",  # Royal Blue
        "head": "default",
        "tail": "default",
    }


# start is called when your Battlesnake begins a game
def start(game_state: typing.Dict):
    print("GAME START")


# end is called when your Battlesnake finishes a game
def end(game_state: typing.Dict):
    print("GAME OVER\n")


def get_next_position(head: typing.Dict, move: str) -> typing.Dict:
    """Calculate the next position given a head position and move direction."""
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
    """Check if a position is out of bounds."""
    return pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height


def is_collision_with_snake(pos: typing.Dict, snake_body: typing.List[typing.Dict], exclude_tail: bool = False) -> bool:
    """Check if a position collides with a snake body."""
    body_to_check = snake_body[:-1] if exclude_tail else snake_body
    return any(pos["x"] == segment["x"] and pos["y"] == segment["y"] for segment in body_to_check)


def manhattan_distance(pos1: typing.Dict, pos2: typing.Dict) -> int:
    """Calculate Manhattan distance between two positions."""
    return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])


def flood_fill(start_pos: typing.Dict, board_width: int, board_height: int, 
               obstacles: typing.Set[typing.Tuple[int, int]], max_depth: int = 100) -> int:
    """
    Count the number of reachable squares from start_pos using BFS.
    Returns the count of accessible squares.
    """
    visited = set()
    queue = deque([start_pos])
    visited.add((start_pos["x"], start_pos["y"]))
    count = 0
    
    while queue and count < max_depth:
        pos = queue.popleft()
        count += 1
        
        # Check all four directions
        for move in ["up", "down", "left", "right"]:
            next_pos = get_next_position(pos, move)
            next_tuple = (next_pos["x"], next_pos["y"])
            
            # Skip if out of bounds, already visited, or is an obstacle
            if (is_out_of_bounds(next_pos, board_width, board_height) or
                next_tuple in visited or
                next_tuple in obstacles):
                continue
            
            visited.add(next_tuple)
            queue.append(next_pos)
    
    return count


def get_obstacles(game_state: typing.Dict, exclude_tails: bool = False) -> typing.Set[typing.Tuple[int, int]]:
    """
    Get all obstacle positions (snake bodies) on the board.
    If exclude_tails is True, don't include snake tails (they'll move next turn).
    """
    obstacles = set()
    
    for snake in game_state['board']['snakes']:
        body = snake['body']
        # Exclude tail if requested (it will move away next turn unless snake just ate)
        body_to_add = body[:-1] if exclude_tails else body
        for segment in body_to_add:
            obstacles.add((segment["x"], segment["y"]))
    
    return obstacles


def can_reach_food_first(my_head: typing.Dict, food_pos: typing.Dict, 
                         opponents: typing.List, my_length: int) -> bool:
    """
    Check if we can reach food before any opponent.
    Returns True if we're closer or equal distance and longer/equal length.
    """
    my_dist = manhattan_distance(my_head, food_pos)
    
    for opponent in opponents:
        opp_head = opponent['body'][0]
        opp_dist = manhattan_distance(opp_head, food_pos)
        opp_length = len(opponent['body'])
        
        # If opponent is closer, we can't guarantee reaching first
        if opp_dist < my_dist:
            return False
        
        # If same distance, we need to be longer or equal to win head-to-head
        if opp_dist == my_dist and opp_length > my_length:
            return False
    
    return True


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:

    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]
    my_body = game_state["you"]["body"]
    my_tail = my_body[-1]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    opponents = [s for s in game_state['board']['snakes'] if s['id'] != game_state['you']['id']]
    food = game_state['board']['food']
    my_health = game_state['you']['health']
    my_length = len(my_body)

    # Prevent moving backwards
    if my_neck["x"] < my_head["x"]:
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:
        is_move_safe["up"] = False

    # Check all possible moves
    for move_direction in ["up", "down", "left", "right"]:
        if not is_move_safe[move_direction]:
            continue
            
        next_pos = get_next_position(my_head, move_direction)
        
        # Check boundaries
        if is_out_of_bounds(next_pos, board_width, board_height):
            is_move_safe[move_direction] = False
            continue
        
        # Check collision with own body (exclude tail since it will move)
        if is_collision_with_snake(next_pos, my_body, exclude_tail=True):
            is_move_safe[move_direction] = False
            continue
        
        # Check collision with opponent snakes
        for opponent in opponents:
            # Exclude tail for opponents too (unless they might eat food)
            if is_collision_with_snake(next_pos, opponent['body'], exclude_tail=True):
                is_move_safe[move_direction] = False
                break
            
            # Avoid head-to-head collisions with longer or equal snakes
            opponent_head = opponent['body'][0]
            opponent_length = len(opponent['body'])
            
            # Check if opponent could move to the same square
            if manhattan_distance(next_pos, opponent_head) == 1:
                # If opponent is longer or equal, avoid this square
                if opponent_length >= my_length:
                    is_move_safe[move_direction] = False
                    break

    # Get safe moves
    safe_moves = [move for move, is_safe in is_move_safe.items() if is_safe]

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Use flood fill to evaluate space available for each move
    move_space = {}
    obstacles = get_obstacles(game_state, exclude_tails=True)
    
    for move_direction in safe_moves:
        next_pos = get_next_position(my_head, move_direction)
        # Calculate available space from this position
        space = flood_fill(next_pos, board_width, board_height, obstacles)
        move_space[move_direction] = space
    
    # Get opponent info for strategic decisions
    max_opponent_length = 0
    for opponent in opponents:
        max_opponent_length = max(max_opponent_length, len(opponent['body']))
    
    # Determine food seeking priority
    should_seek_food = False
    food_priority = "none"
    
    if my_health < 30:
        should_seek_food = True
        food_priority = "critical"
    elif my_health < 50:
        should_seek_food = True
        food_priority = "high"
    elif my_length < max_opponent_length:
        should_seek_food = True
        food_priority = "growth"
    elif my_health < 80:
        should_seek_food = True
        food_priority = "medium"
    elif my_length < 20:
        should_seek_food = True
        food_priority = "low"
    
    # Food seeking logic with improved race prediction
    if should_seek_food and food:
        # Find food we can reach first
        winnable_food = []
        for f in food:
            if can_reach_food_first(my_head, f, opponents, my_length):
                winnable_food.append(f)
        
        # If no winnable food, consider all food (be aggressive)
        food_to_consider = winnable_food if winnable_food else food
        
        closest_food = min(food_to_consider, key=lambda f: manhattan_distance(my_head, f))
        closest_food_dist = manhattan_distance(my_head, closest_food)
        
        # Determine if we should go for this food
        max_food_distance = 15
        if food_priority == "critical":
            max_food_distance = 999
        elif food_priority == "high":
            max_food_distance = 20
        elif food_priority == "growth":
            max_food_distance = 15
        
        if closest_food_dist <= max_food_distance:
            # Determine space requirement based on food priority
            # Be more aggressive (require less space) when seeking food
            if food_priority in ["critical", "high"]:
                min_space_for_food = my_length  # Only require 1x space when desperate
            elif food_priority == "growth":
                min_space_for_food = int(my_length * 1.2)  # 1.2x space when growing
            else:
                min_space_for_food = int(my_length * 1.5)  # 1.5x space otherwise
            
            # Filter moves that have enough space for food seeking
            food_seeking_moves = [m for m in safe_moves if move_space[m] >= min_space_for_food]
            
            # If no moves meet the space requirement, use all safe moves
            if not food_seeking_moves:
                food_seeking_moves = safe_moves
            
            # Score moves based on distance to food and space
            move_scores = {}
            for move_direction in food_seeking_moves:
                next_pos = get_next_position(my_head, move_direction)
                distance = manhattan_distance(next_pos, closest_food)
                space = move_space[move_direction]
                
                # Adjust weights based on priority
                if food_priority == "critical":
                    distance_weight = 100
                    space_weight = 0.1
                elif food_priority == "high":
                    distance_weight = 50
                    space_weight = 0.5
                elif food_priority == "growth":
                    distance_weight = 30
                    space_weight = 1
                elif food_priority == "medium":
                    distance_weight = 20
                    space_weight = 1.5
                else:
                    distance_weight = 15
                    space_weight = 2
                
                move_scores[move_direction] = -distance * distance_weight + space * space_weight
            
            best_move = max(move_scores, key=move_scores.get)
            print(f"MOVE {game_state['turn']}: {best_move} (food [{food_priority}], h={my_health}, l={my_length}, s={move_space[best_move]}, winnable={len(winnable_food)})")
            return {"move": best_move}

    # No food seeking - choose move with most space, but require 1.5x space
    min_required_space = int(my_length * 1.5)
    spacious_moves = [move for move in safe_moves if move_space[move] >= min_required_space]
    
    # If no moves meet 1.5x requirement, try 1x
    if not spacious_moves:
        min_required_space = my_length
        spacious_moves = [move for move in safe_moves if move_space[move] >= min_required_space]
    
    # If still no spacious moves, use all safe moves
    if not spacious_moves:
        spacious_moves = safe_moves
    
    best_move = max(spacious_moves, key=lambda m: move_space[m])
    print(f"MOVE {game_state['turn']}: {best_move} (max space={move_space[best_move]})")
    return {"move": best_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})