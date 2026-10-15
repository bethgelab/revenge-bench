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


def get_next_position(head: typing.Dict, move: str) -> typing.Dict:
    """Get the next position given a head position and move direction."""
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


def is_position_safe(pos: typing.Dict, game_state: typing.Dict, ignore_tails: bool = True) -> bool:
    """Check if a position is safe to move to."""
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Check walls
    if pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height:
        return False
    
    # Check all snakes (including ourselves)
    for snake in game_state['board']['snakes']:
        for i, body_part in enumerate(snake['body']):
            # Skip tail if ignore_tails (tail will move next turn)
            if ignore_tails and i == len(snake['body']) - 1:
                continue
            if pos["x"] == body_part["x"] and pos["y"] == body_part["y"]:
                return False
    
    return True


def flood_fill(start: typing.Dict, game_state: typing.Dict, max_depth: int = 100) -> int:
    """Count reachable spaces from a starting position using flood fill."""
    visited = set()
    queue = deque([start])
    visited.add((start["x"], start["y"]))
    count = 0
    
    while queue and count < max_depth:
        pos = queue.popleft()
        count += 1
        
        for move in ["up", "down", "left", "right"]:
            next_pos = get_next_position(pos, move)
            pos_tuple = (next_pos["x"], next_pos["y"])
            
            if pos_tuple not in visited and is_position_safe(next_pos, game_state):
                visited.add(pos_tuple)
                queue.append(next_pos)
    
    return count


def get_distance(pos1: typing.Dict, pos2: typing.Dict) -> int:
    """Calculate Manhattan distance between two positions."""
    return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])


def distance_to_edge(pos: typing.Dict, board_width: int, board_height: int) -> int:
    """Calculate minimum distance to any edge."""
    return min(pos["x"], pos["y"], board_width - 1 - pos["x"], board_height - 1 - pos["y"])


def count_immediate_escape_routes(pos: typing.Dict, game_state: typing.Dict) -> int:
    """Count how many safe moves are available from a position."""
    count = 0
    for move in ["up", "down", "left", "right"]:
        next_pos = get_next_position(pos, move)
        if is_position_safe(next_pos, game_state):
            count += 1
    return count


def get_possible_opponent_moves(snake: typing.Dict, game_state: typing.Dict) -> typing.List[typing.Dict]:
    """Get all possible positions an opponent snake could move to."""
    head = snake['body'][0]
    possible_positions = []
    
    for move in ["up", "down", "left", "right"]:
        next_pos = get_next_position(head, move)
        if is_position_safe(next_pos, game_state):
            possible_positions.append(next_pos)
    
    return possible_positions


def is_head_to_head_risky(pos: typing.Dict, game_state: typing.Dict, my_length: int) -> bool:
    """Check if a position could result in a risky head-to-head collision.
    Only avoid if we would definitely lose (opponent is larger)."""
    for snake in game_state['board']['snakes']:
        if snake['id'] == game_state['you']['id']:
            continue
        
        snake_head = snake['body'][0]
        snake_length = len(snake['body'])
        
        opponent_moves = get_possible_opponent_moves(snake, game_state)
        
        for opp_pos in opponent_moves:
            # Direct head-to-head collision - only avoid if opponent is strictly larger
            if pos["x"] == opp_pos["x"] and pos["y"] == opp_pos["y"]:
                if snake_length > my_length:
                    return True
    
    return False


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:

    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]
    my_health = game_state["you"]["health"]
    my_length = len(game_state["you"]["body"])
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    current_turn = game_state['turn']

    # Prevent moving backwards
    if my_neck["x"] < my_head["x"]:
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:
        is_move_safe["up"] = False

    # Check each move for safety
    for move_dir in ["up", "down", "left", "right"]:
        if not is_move_safe[move_dir]:
            continue
        
        next_pos = get_next_position(my_head, move_dir)
        
        # Check if position is safe (walls, bodies)
        if not is_position_safe(next_pos, game_state):
            is_move_safe[move_dir] = False
            continue
        
        # Check for head-to-head collisions with larger snakes only
        if is_head_to_head_risky(next_pos, game_state, my_length):
            is_move_safe[move_dir] = False

    # Get safe moves
    safe_moves = [move for move, isSafe in is_move_safe.items() if isSafe]

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # If we have multiple safe moves, choose the best one
    if len(safe_moves) > 1:
        # Evaluate moves based on space available and food proximity
        move_scores = {}
        
        # Get opponent info
        max_opponent_length = max([len(s['body']) for s in game_state['board']['snakes'] 
                                  if s['id'] != game_state['you']['id']], default=0)
        
        for move_dir in safe_moves:
            next_pos = get_next_position(my_head, move_dir)
            score = 0
            
            # Space control - ADAPTIVE based on situation
            space = flood_fill(next_pos, game_state, max_depth=100)
            
            # If space is very limited (< 15), prioritize it heavily to avoid traps
            if space < 15:
                score += space * 20  # Increased from 15
            elif space < 30:
                score += space * 12  # Increased from 10
            else:
                score += space * 7   # Increased from 6
            
            # Escape route quality - penalize positions with few escape routes
            escape_routes = count_immediate_escape_routes(next_pos, game_state)
            if escape_routes <= 1:
                score -= 100  # Very dangerous - only one way out
            elif escape_routes == 2:
                score -= 30   # Risky - limited options
            
            # Edge avoidance - SIGNIFICANTLY increased from Round 14
            edge_dist = distance_to_edge(next_pos, board_width, board_height)
            if edge_dist == 0:
                score -= 100  # Increased from 60 - edges are death traps
            elif edge_dist == 1:
                score -= 40   # Increased from 15 - near edges is risky
            elif edge_dist == 2:
                score -= 10   # Small penalty for being close to edges
            
            # ULTRA AGGRESSIVE FOOD SEEKING STRATEGY (kept from Round 13)
            # BUT reduced when space is very limited
            if game_state['board']['food']:
                closest_food = min(game_state['board']['food'], 
                                 key=lambda f: get_distance(next_pos, f))
                food_dist = get_distance(next_pos, closest_food)
                
                # Calculate size disadvantage
                size_disadvantage = max_opponent_length - my_length
                
                # Reduce food aggression when space is very limited
                space_multiplier = 1.0
                if space < 15:
                    space_multiplier = 0.5  # Half food priority when trapped
                elif space < 25:
                    space_multiplier = 0.75  # Reduced food priority when space is tight
                
                # MASSIVELY increased food seeking weights (but modulated by space)
                if my_health < 20:
                    # Critical - must get food NOW
                    score += int((600 - food_dist * 50) * space_multiplier)
                elif my_health < 35:
                    # Very low health - prioritize heavily
                    score += int((500 - food_dist * 45) * space_multiplier)
                elif my_health < 50:
                    # Low health - strong priority
                    score += int((400 - food_dist * 40) * space_multiplier)
                elif size_disadvantage > 5:
                    # Way behind in size - need to catch up AGGRESSIVELY
                    score += int((350 - food_dist * 35) * space_multiplier)
                elif size_disadvantage > 3:
                    # Behind in size - prioritize growth heavily
                    score += int((300 - food_dist * 30) * space_multiplier)
                elif size_disadvantage > 0:
                    # Any size disadvantage - seek food aggressively
                    score += int((250 - food_dist * 25) * space_multiplier)
                elif my_health < 70:
                    # Moderate health - still prioritize food
                    score += int((200 - food_dist * 20) * space_multiplier)
                elif current_turn < 150:
                    # Mid game - keep growing
                    score += int((180 - food_dist * 18) * space_multiplier)
                else:
                    # Late game with good health - still seek food
                    score += int((150 - food_dist * 15) * space_multiplier)
            
            # Minimal opponent proximity penalties - don't let this stop us from getting food
            for snake in game_state['board']['snakes']:
                if snake['id'] == game_state['you']['id']:
                    continue
                
                snake_head = snake['body'][0]
                dist_to_opponent = get_distance(next_pos, snake_head)
                
                # Only penalize if opponent is significantly larger AND very close
                if len(snake['body']) > my_length + 3:
                    if dist_to_opponent <= 1:
                        score -= 30
                # If we're larger, be aggressive
                elif len(snake['body']) < my_length:
                    if dist_to_opponent <= 2:
                        score += 40
            
            move_scores[move_dir] = score
        
        # Choose move with highest score
        next_move = max(move_scores, key=move_scores.get)
        print(f"MOVE {game_state['turn']}: {next_move} (scores: {move_scores})")
    else:
        next_move = safe_moves[0]
        print(f"MOVE {game_state['turn']}: {next_move} (only safe move)")

    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})