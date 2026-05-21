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
        "author": "claude-sonnet-4-20250514",  # Updated author
        "color": "#FF6B35",  # Updated to a more distinctive color
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


def flood_fill_space(start_pos: typing.Dict, game_state: typing.Dict, max_depth: int = 15) -> int:
    """Count accessible spaces using flood fill algorithm"""
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    visited = set()
    queue = [(start_pos["x"], start_pos["y"], 0)]
    visited.add((start_pos["x"], start_pos["y"]))
    
    accessible_count = 0
    
    while queue and accessible_count < max_depth:
        x, y, depth = queue.pop(0)
        accessible_count += 1
        
        if depth >= max_depth:
            continue
            
        # Check all 4 directions
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            
            if (nx, ny) in visited:
                continue
                
            if nx < 0 or nx >= board_width or ny < 0 or ny >= board_height:
                continue
                
            # Check if position is blocked by snake bodies
            blocked = False
            
            # Check our body (excluding tail which will move)
            for body_part in game_state['you']['body'][:-1]:
                if nx == body_part["x"] and ny == body_part["y"]:
                    blocked = True
                    break
            
            if not blocked:
                # Check opponent bodies
                for snake in game_state['board']['snakes']:
                    if snake['id'] == game_state['you']['id']:
                        continue
                    for body_part in snake['body'][:-1]:
                        if nx == body_part["x"] and ny == body_part["y"]:
                            blocked = True
                            break
                    if blocked:
                        break
            
            if not blocked:
                visited.add((nx, ny))
                queue.append((nx, ny, depth + 1))
    
    return accessible_count


def is_position_safe(pos: typing.Dict, game_state: typing.Dict) -> bool:
    """Check if a position is safe (no walls, bodies, or opponents)"""
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Check boundaries
    if pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height:
        return False
    
    # Check self collision
    my_body = game_state['you']['body'][:-1]  # Exclude tail as it will move
    for body_part in my_body:
        if pos["x"] == body_part["x"] and pos["y"] == body_part["y"]:
            return False
    
    # Check opponent collisions
    opponents = game_state['board']['snakes']
    for opponent in opponents:
        if opponent['id'] == game_state['you']['id']:
            continue  # Skip ourselves
        
        # Check collision with opponent body (excluding tail which will move)
        for body_part in opponent['body'][:-1]:
            if pos["x"] == body_part["x"] and pos["y"] == body_part["y"]:
                return False
        
        # Check head-to-head collision risk
        opponent_head = opponent['body'][0]
        if pos["x"] == opponent_head["x"] and pos["y"] == opponent_head["y"]:
            # Only avoid if opponent is same length or longer
            if opponent['length'] >= game_state['you']['length']:
                return False
    
    return True


def find_food_direction(game_state: typing.Dict) -> str:
    """Find the best direction to move towards food"""
    my_head = game_state["you"]["body"][0]
    food_list = game_state['board']['food']
    
    if not food_list:
        return None
    
    # Find closest food
    closest_food = None
    min_distance = float('inf')
    
    for food in food_list:
        distance = abs(food["x"] - my_head["x"]) + abs(food["y"] - my_head["y"])
        if distance < min_distance:
            min_distance = distance
            closest_food = food
    
    if not closest_food:
        return None
    
    # Determine best direction towards food
    dx = closest_food["x"] - my_head["x"]
    dy = closest_food["y"] - my_head["y"]
    
    # Prioritize the direction with larger distance
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    else:
        return "up" if dy > 0 else "down"


def should_prioritize_food(game_state: typing.Dict) -> bool:
    """Determine if we should prioritize food over space control"""
    my_health = game_state['you']['health']
    my_length = game_state['you']['length']
    
    # Always prioritize food if health is critically low
    if my_health <= 15:
        return True
    
    # Prioritize food if health is low and we're not much longer than opponents
    if my_health <= 30:
        for opponent in game_state['board']['snakes']:
            if opponent['id'] != game_state['you']['id']:
                if opponent['length'] >= my_length - 2:  # Opponent is close in length
                    return True
    
    # Early game: prioritize growth
    if my_length <= 6:
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

    # Check safety for each possible move
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

    # Health-based decision making
    prioritize_food = should_prioritize_food(game_state)
    
    if prioritize_food:
        # When prioritizing food, try food direction first if it's safe
        food_direction = find_food_direction(game_state)
        if food_direction and food_direction in safe_moves:
            print(f"MOVE {game_state['turn']}: Prioritizing food due to health/length: {food_direction}")
            return {"move": food_direction}

    # If we have multiple safe moves, prefer ones with more space
    if len(safe_moves) > 1:
        move_scores = {}
        for move_dir in safe_moves:
            next_pos = get_next_position(my_head, move_dir)
            space_count = flood_fill_space(next_pos, game_state)
            move_scores[move_dir] = space_count
        
        # Sort moves by space available
        safe_moves.sort(key=lambda x: move_scores[x], reverse=True)
        
        # More conservative space advantage threshold when we're winning
        my_length = game_state['you']['length']
        max_opponent_length = max([snake['length'] for snake in game_state['board']['snakes'] 
                                  if snake['id'] != game_state['you']['id']], default=0)
        
        # If we're significantly longer, be more conservative
        space_threshold = 3 if my_length > max_opponent_length + 5 else 2
        
        # If there's a clear winner in terms of space, choose it
        best_space = move_scores[safe_moves[0]]
        if len(safe_moves) > 1 and best_space > move_scores[safe_moves[1]] + space_threshold:
            print(f"MOVE {game_state['turn']}: Choosing {safe_moves[0]} for space ({best_space} accessible)")
            return {"move": safe_moves[0]}

    # Try to move towards food if we have safe moves and not already prioritizing
    if not prioritize_food:
        food_direction = find_food_direction(game_state)
        if food_direction and food_direction in safe_moves:
            print(f"MOVE {game_state['turn']}: Moving towards food: {food_direction}")
            return {"move": food_direction}

    # Choose the move with most space available
    next_move = safe_moves[0]
    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})