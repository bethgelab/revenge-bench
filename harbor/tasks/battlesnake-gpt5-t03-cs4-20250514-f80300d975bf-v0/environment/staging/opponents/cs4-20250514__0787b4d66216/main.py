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
import heapq


# info is called when you create your Battlesnake on play.battlesnake.com
# and controls your Battlesnake's appearance
# TIP: If you open your Battlesnake URL in a browser you should see this data
def info() -> typing.Dict:
    print("INFO")

    return {
        "apiversion": "1",
        "author": "claude-sonnet-4-20250514",  # Updated author
        "color": "#00FF00",  # Changed to green for better visibility
        "head": "default",
        "tail": "default",
    }


# start is called when your Battlesnake begins a game
def start(game_state: typing.Dict):
    print("GAME START")


# end is called when your Battlesnake finishes a game
def end(game_state: typing.Dict):
    print("GAME OVER\n")


def get_next_position(head: typing.Dict, direction: str) -> typing.Dict:
    """Calculate the next position given current head position and direction"""
    next_pos = {"x": head["x"], "y": head["y"]}
    
    if direction == "up":
        next_pos["y"] += 1
    elif direction == "down":
        next_pos["y"] -= 1
    elif direction == "left":
        next_pos["x"] -= 1
    elif direction == "right":
        next_pos["x"] += 1
    
    return next_pos


def is_position_safe(pos: typing.Dict, game_state: typing.Dict) -> bool:
    """Check if a position is safe (no collisions, within bounds)"""
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Check bounds
    if pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height:
        return False
    
    # Check collision with our own body (excluding tail which will move)
    my_body = game_state['you']['body']
    for body_part in my_body:
        if pos["x"] == body_part["x"] and pos["y"] == body_part["y"]:
            return False
    
    # Check collision with other snakes
    for snake in game_state['board']['snakes']:
        if snake['id'] == game_state['you']['id']:
            continue  # Skip our own snake
        
        # Check collision with other snake's body
        for body_part in snake['body']:
            if pos["x"] == body_part["x"] and pos["y"] == body_part["y"]:
                return False
        
        # Check head-to-head collision (avoid if we're not longer)
        snake_head = snake['head']
        if pos["x"] == snake_head["x"] and pos["y"] == snake_head["y"]:
            if len(game_state['you']['body']) <= len(snake['body']):
                return False
    
    return True


def count_reachable_spaces(pos: typing.Dict, game_state: typing.Dict, max_depth: int = 3) -> int:
    """Count how many spaces are reachable from a position using flood fill"""
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    visited = set()
    queue = [(pos["x"], pos["y"], 0)]
    count = 0
    
    # Get all occupied positions
    occupied = set()
    for snake in game_state['board']['snakes']:
        for body_part in snake['body']:
            occupied.add((body_part["x"], body_part["y"]))
    
    while queue:
        x, y, depth = queue.pop(0)
        
        if (x, y) in visited or depth > max_depth:
            continue
            
        if x < 0 or x >= board_width or y < 0 or y >= board_height:
            continue
            
        if (x, y) in occupied:
            continue
            
        visited.add((x, y))
        count += 1
        
        # Add adjacent positions
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            queue.append((x + dx, y + dy, depth + 1))
    
    return count


def manhattan_distance(pos1: typing.Dict, pos2: typing.Dict) -> int:
    """Calculate Manhattan distance between two positions"""
    return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])


def astar_path_to_food(start: typing.Dict, goal: typing.Dict, game_state: typing.Dict) -> typing.List:
    """Use A* algorithm to find the best path to food"""
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Get all occupied positions (excluding tails that will move)
    occupied = set()
    for snake in game_state['board']['snakes']:
        for i, body_part in enumerate(snake['body']):
            # Don't include tail positions as they will move
            if i < len(snake['body']) - 1:
                occupied.add((body_part["x"], body_part["y"]))
    
    # A* implementation
    heap = [(0, 0, start["x"], start["y"], [])]  # (f_score, g_score, x, y, path)
    visited = set()
    
    while heap:
        f_score, g_score, x, y, path = heapq.heappop(heap)
        
        if (x, y) in visited:
            continue
        visited.add((x, y))
        
        # Check if we reached the goal
        if x == goal["x"] and y == goal["y"]:
            return path
        
        # Explore neighbors
        for direction in ["up", "down", "left", "right"]:
            next_pos = get_next_position({"x": x, "y": y}, direction)
            nx, ny = next_pos["x"], next_pos["y"]
            
            # Check bounds
            if nx < 0 or nx >= board_width or ny < 0 or ny >= board_height:
                continue
            
            # Check if position is occupied
            if (nx, ny) in occupied:
                continue
            
            # Check if already visited
            if (nx, ny) in visited:
                continue
            
            new_g_score = g_score + 1
            h_score = manhattan_distance({"x": nx, "y": ny}, goal)
            new_f_score = new_g_score + h_score
            
            new_path = path + [direction]
            heapq.heappush(heap, (new_f_score, new_g_score, nx, ny, new_path))
    
    return []  # No path found


def find_best_food(head: typing.Dict, food_list: typing.List, game_state: typing.Dict) -> typing.Dict:
    """Find the best food considering distance, safety, and path efficiency"""
    if not food_list:
        return None
    
    best_food = None
    best_score = float('-inf')
    
    for food in food_list:
        # Use A* to find actual path distance
        path = astar_path_to_food(head, food, game_state)
        if not path:  # No path to this food
            continue
        
        path_length = len(path)
        
        # Base score favors closer food
        score = 100 - path_length
        
        # Bonus for food that doesn't lead us into tight spaces
        food_pos = {"x": food["x"], "y": food["y"]}
        reachable_spaces = count_reachable_spaces(food_pos, game_state)
        score += reachable_spaces * 3  # Increased bonus for open areas
        
        # Bonus for food that's not contested by other snakes
        contested = False
        for snake in game_state['board']['snakes']:
            if snake['id'] != game_state['you']['id']:
                snake_distance = manhattan_distance(snake['head'], food)
                if snake_distance <= path_length:  # Other snake is closer or equal
                    contested = True
                    break
        
        if not contested:
            score += 20  # Bonus for uncontested food
        
        if score > best_score:
            best_score = score
            best_food = food
    
    return best_food


def get_direction_to_target(head: typing.Dict, target: typing.Dict, game_state: typing.Dict) -> str:
    """Get the best direction to move towards a target using A* pathfinding"""
    path = astar_path_to_food(head, target, game_state)
    if path:
        return path[0]  # Return first move in the path
    
    # Fallback to simple direction if A* fails
    dx = target["x"] - head["x"]
    dy = target["y"] - head["y"]
    
    # Prioritize the axis with larger distance
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    else:
        return "up" if dy > 0 else "down"


def should_seek_food(game_state: typing.Dict) -> bool:
    """Determine if we should actively seek food based on health and game state"""
    my_health = game_state['you']['health']
    my_length = len(game_state['you']['body'])
    
    # Always seek food if health is critically low
    if my_health < 25:
        return True
    
    # Seek food if we're shorter than opponents
    for snake in game_state['board']['snakes']:
        if snake['id'] != game_state['you']['id']:
            if len(snake['body']) > my_length:
                return True
    
    # Seek food if health is getting low and we're not significantly longer
    if my_health < 60:
        max_opponent_length = 0
        for snake in game_state['board']['snakes']:
            if snake['id'] != game_state['you']['id']:
                max_opponent_length = max(max_opponent_length, len(snake['body']))
        
        # If we're not at least 2 segments longer, keep growing
        if my_length <= max_opponent_length + 1:
            return True
    
    return False


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

    # Check all moves for safety (bounds, collisions)
    for direction in ["up", "down", "left", "right"]:
        if is_move_safe[direction]:
            next_pos = get_next_position(my_head, direction)
            if not is_position_safe(next_pos, game_state):
                is_move_safe[direction] = False

    # Are there any safe moves left?
    safe_moves = []
    for move_dir, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move_dir)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Enhanced food-seeking logic with A* pathfinding
    food = game_state['board']['food']
    if food and should_seek_food(game_state):
        best_food = find_best_food(my_head, food, game_state)
        if best_food:
            preferred_direction = get_direction_to_target(my_head, best_food, game_state)
            if preferred_direction in safe_moves:
                print(f"MOVE {game_state['turn']}: Moving {preferred_direction} towards food at {best_food} (health: {game_state['you']['health']}, length: {len(game_state['you']['body'])})")
                return {"move": preferred_direction}

    # If we can't go towards food, choose the move that gives us the most space
    best_move = None
    best_space_count = -1
    
    for move_dir in safe_moves:
        next_pos = get_next_position(my_head, move_dir)
        space_count = count_reachable_spaces(next_pos, game_state)
        if space_count > best_space_count:
            best_space_count = space_count
            best_move = move_dir

    if best_move:
        print(f"MOVE {game_state['turn']}: Moving {best_move} for space (reachable: {best_space_count})")
        return {"move": best_move}

    # Fallback to random move from safe ones
    next_move = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: Random move {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})