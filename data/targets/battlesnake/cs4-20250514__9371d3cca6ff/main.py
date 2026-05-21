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
        "author": "claude-sonnet-4-20250514",
        "color": "#FF6B35",
        "head": "default",
        "tail": "default",
    }


# start is called when your Battlesnake begins a game
def start(game_state: typing.Dict):
    print("GAME START")


# end is called when your Battlesnake finishes a game
def end(game_state: typing.Dict):
    print("GAME OVER\n")


def quick_space_check(game_state: typing.Dict, pos: typing.Dict, depth: int = 3) -> int:
    """
    Quick space check using limited depth flood fill for performance.
    """
    if depth <= 0:
        return 0
        
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Create set of occupied positions
    occupied = set()
    for snake in game_state['board']['snakes']:
        for i, body_part in enumerate(snake['body'][:-1]):  # Skip tail
            occupied.add((body_part['x'], body_part['y']))
    
    # Quick BFS with limited depth
    visited = set()
    queue = [(pos['x'], pos['y'], 0)]
    reachable = 0
    
    while queue:
        x, y, d = queue.pop(0)
        
        if (x, y) in visited or d > depth:
            continue
            
        if (x < 0 or x >= board_width or y < 0 or y >= board_height):
            continue
            
        if (x, y) in occupied:
            continue
            
        visited.add((x, y))
        reachable += 1
        
        # Add adjacent positions
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            queue.append((x + dx, y + dy, d + 1))
    
    return reachable


def get_safe_moves(game_state: typing.Dict) -> typing.Dict[str, bool]:
    """
    Determine which moves are safe by checking boundaries, self-collision, and other snakes.
    """
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}
    
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1] if len(game_state["you"]["body"]) > 1 else None
    my_body = game_state["you"]["body"]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Prevent moving backwards (into neck)
    if my_neck:
        if my_neck["x"] < my_head["x"]:  # Neck is left of head, don't move left
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:  # Neck is right of head, don't move right
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:  # Neck is below head, don't move down
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:  # Neck is above head, don't move up
            is_move_safe["up"] = False

    # Check each possible move
    possible_moves = {
        "up": {"x": my_head["x"], "y": my_head["y"] + 1},
        "down": {"x": my_head["x"], "y": my_head["y"] - 1},
        "left": {"x": my_head["x"] - 1, "y": my_head["y"]},
        "right": {"x": my_head["x"] + 1, "y": my_head["y"]}
    }
    
    for move, new_pos in possible_moves.items():
        # Check boundaries
        if (new_pos["x"] < 0 or new_pos["x"] >= board_width or 
            new_pos["y"] < 0 or new_pos["y"] >= board_height):
            is_move_safe[move] = False
            continue
            
        # Check self-collision (skip tail since it will move)
        for i, body_part in enumerate(my_body[:-1]):  # Skip tail
            if new_pos["x"] == body_part["x"] and new_pos["y"] == body_part["y"]:
                is_move_safe[move] = False
                break
                
        # Check collision with other snakes
        for snake in game_state['board']['snakes']:
            if snake['id'] == game_state['you']['id']:
                continue  # Skip ourselves
                
            # Check collision with other snake bodies (skip their tail too)
            for i, body_part in enumerate(snake['body'][:-1]):
                if new_pos["x"] == body_part["x"] and new_pos["y"] == body_part["y"]:
                    is_move_safe[move] = False
                    break
                    
            # Check head-to-head collisions - be more aggressive if we're longer
            other_head = snake['body'][0]
            other_possible_moves = [
                {"x": other_head["x"], "y": other_head["y"] + 1},
                {"x": other_head["x"], "y": other_head["y"] - 1},
                {"x": other_head["x"] - 1, "y": other_head["y"]},
                {"x": other_head["x"] + 1, "y": other_head["y"]}
            ]
            
            for other_move in other_possible_moves:
                if (new_pos["x"] == other_move["x"] and new_pos["y"] == other_move["y"]):
                    # Head-to-head collision possible - be more aggressive
                    if len(game_state['you']['body']) < len(snake['body']):
                        is_move_safe[move] = False
                        break
    
    return is_move_safe


def find_food_direction(game_state: typing.Dict, safe_moves: typing.List[str]) -> str:
    """
    Find direction towards closest food, but with some strategic considerations.
    """
    if not safe_moves:
        return None
        
    my_head = game_state["you"]["body"][0]
    food_list = game_state['board']['food']
    
    if not food_list:
        return None
    
    # Find closest food
    closest_food = min(food_list, key=lambda food: 
                      abs(my_head["x"] - food["x"]) + abs(my_head["y"] - food["y"]))
    
    # Calculate direction to closest food
    dx = closest_food["x"] - my_head["x"]
    dy = closest_food["y"] - my_head["y"]
    
    preferred_moves = []
    
    # Prioritize the axis with larger distance
    if abs(dx) > abs(dy):
        if dx > 0 and "right" in safe_moves:
            preferred_moves.append("right")
        elif dx < 0 and "left" in safe_moves:
            preferred_moves.append("left")
        if dy > 0 and "up" in safe_moves:
            preferred_moves.append("up")
        elif dy < 0 and "down" in safe_moves:
            preferred_moves.append("down")
    else:
        if dy > 0 and "up" in safe_moves:
            preferred_moves.append("up")
        elif dy < 0 and "down" in safe_moves:
            preferred_moves.append("down")
        if dx > 0 and "right" in safe_moves:
            preferred_moves.append("right")
        elif dx < 0 and "left" in safe_moves:
            preferred_moves.append("left")
    
    if preferred_moves:
        return random.choice(preferred_moves)
    
    return None


def choose_aggressive_move(game_state: typing.Dict, safe_moves: typing.List[str]) -> str:
    """
    Choose move with mix of space awareness and aggression.
    """
    if not safe_moves:
        return "down"
    
    if len(safe_moves) == 1:
        return safe_moves[0]
    
    # Quick space evaluation for each move
    possible_moves = {
        "up": {"x": game_state["you"]["body"][0]["x"], "y": game_state["you"]["body"][0]["y"] + 1},
        "down": {"x": game_state["you"]["body"][0]["x"], "y": game_state["you"]["body"][0]["y"] - 1},
        "left": {"x": game_state["you"]["body"][0]["x"] - 1, "y": game_state["you"]["body"][0]["y"]},
        "right": {"x": game_state["you"]["body"][0]["x"] + 1, "y": game_state["you"]["body"][0]["y"]}
    }
    
    move_scores = {}
    for move in safe_moves:
        new_pos = possible_moves[move]
        space = quick_space_check(game_state, new_pos, depth=2)  # Shallow check for speed
        move_scores[move] = space
    
    # Filter out moves with very little space (less than 3)
    good_moves = [m for m in safe_moves if move_scores[m] >= 3]
    
    if not good_moves:
        good_moves = safe_moves  # Fallback to any safe move
    
    # Add some randomness - don't always pick the "best" move
    if len(good_moves) > 1 and random.random() < 0.3:  # 30% chance of random choice
        return random.choice(good_moves)
    
    # Otherwise pick move with most space
    return max(good_moves, key=lambda m: move_scores[m])


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:
    
    # Get safe moves
    is_move_safe = get_safe_moves(game_state)
    
    # Get list of safe moves
    safe_moves = []
    for move, is_safe in is_move_safe.items():
        if is_safe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    my_health = game_state['you']['health']
    my_length = len(game_state['you']['body'])
    turn = game_state['turn']
    
    # More aggressive food seeking strategy
    food_move = find_food_direction(game_state, safe_moves)
    
    # Seek food when:
    # - Health is low (< 60, more aggressive than before)
    # - We're small (< 8, increased from 6)
    # - Early game (first 20 turns) and health < 80
    # - We have multiple safe options and health < 90
    should_seek_food = (
        my_health < 60 or
        my_length < 8 or
        (turn < 20 and my_health < 80) or
        (len(safe_moves) > 2 and my_health < 90)
    )
    
    if food_move and should_seek_food:
        next_move = food_move
        print(f"MOVE {turn}: Food seeking: {next_move} (health: {my_health}, length: {my_length})")
    else:
        # Use aggressive move selection with some randomness
        next_move = choose_aggressive_move(game_state, safe_moves)
        print(f"MOVE {turn}: Aggressive move: {next_move} (health: {my_health}, length: {my_length})")

    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})