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
from pathfinding import a_star_pathfind, get_neighbors, heuristic


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


# Helper function to calculate accessible area from a position
def calculate_accessible_area(start_pos, game_state, my_body):
    """
    Calculate the accessible area from a given position, avoiding obstacles.
    Uses flood fill algorithm to determine the accessible area size.
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Create a set of positions to avoid (walls, bodies, hazards)
    obstacles = set()
    
    # Add my body (excluding head)
    for part in my_body[:-1]:
        obstacles.add((part['x'], part['y']))
    
    # Add opponent bodies
    for snake in game_state['board']['snakes']:
        if snake['id'] != game_state['you']['id']:
            for part in snake['body'][:-1]:  # Exclude opponent heads
                obstacles.add((part['x'], part['y']))
            # Include opponent heads as well since we don't want to collide with them
            obstacles.add((snake['body'][0]['x'], snake['body'][0]['y']))
    
    # Add hazards if they exist
    if 'hazards' in game_state['board'] and game_state['board']['hazards']:
        for hazard in game_state['board']['hazards']:
            obstacles.add((hazard['x'], hazard['y']))
    
    # Flood fill to calculate accessible area
    visited = set()
    queue = [start_pos]
    area_size = 0
    
    # Directions: up, down, left, right
    directions = [
        {'x': 0, 'y': 1},
        {'x': 0, 'y': -1},
        {'x': -1, 'y': 0},
        {'x': 1, 'y': 0}
    ]
    
    while queue:
        current = queue.pop(0)
        pos_key = (current['x'], current['y'])
        
        # Skip if already visited or is an obstacle
        if pos_key in visited or pos_key in obstacles:
            continue
        
        # Skip if out of bounds
        if (current['x'] < 0 or current['x'] >= board_width or 
            current['y'] < 0 or current['y'] >= board_height):
            continue
        
        visited.add(pos_key)
        area_size += 1
        
        # Add neighbors to queue
        for direction in directions:
            neighbor = {
                'x': current['x'] + direction['x'],
                'y': current['y'] + direction['y']
            }
            queue.append(neighbor)
    
    return area_size


# Helper function to check if a position is safe
def is_position_safe(pos, game_state, my_body):
    # Check bounds
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    if pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height:
        return False
    
    # Check self collision
    for part in my_body[:-1]:  # Exclude head
        if pos == part:
            return False
    
    # Check opponent collision
    opponents = game_state['board']['snakes']
    for snake in opponents:
        if snake["id"] == game_state["you"]["id"]:  # Skip our own snake
            continue
            
        for part in snake["body"][:-1]:  # Exclude opponent's head
            if pos == part:
                return False
    
    # Check hazard collision
    if "hazards" in game_state["board"] and game_state["board"]["hazards"]:
        for hazard in game_state["board"]["hazards"]:
            if pos == hazard:
                return False
    
    return True


# Helper function to count safe moves from a position
def count_safe_moves_from_position(pos, game_state, my_body):
    possible_moves = [
        {"x": pos["x"] + 1, "y": pos["y"]},  # Right
        {"x": pos["x"] - 1, "y": pos["y"]},  # Left
        {"x": pos["x"], "y": pos["y"] + 1},  # Up
        {"x": pos["x"], "y": pos["y"] - 1}   # Down
    ]
    
    safe_count = 0
    for move_pos in possible_moves:
        if is_position_safe(move_pos, game_state, my_body):
            safe_count += 1
    
    return safe_count


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

    # Step 1 - Prevent your Battlesnake from moving out of bounds
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    if my_head["x"] == 0:  # At left edge, can't move left
        is_move_safe["left"] = False
    if my_head["x"] == board_width - 1:  # At right edge, can't move right
        is_move_safe["right"] = False
    if my_head["y"] == 0:  # At bottom edge, can't move down
        is_move_safe["down"] = False
    if my_head["y"] == board_height - 1:  # At top edge, can't move up
        is_move_safe["up"] = False

    # Step 2 - Prevent your Battlesnake from colliding with itself
    my_body = game_state['you']['body']
    
    for part in my_body[:-1]:  # Exclude the head itself
        # Check if moving in any direction would cause collision with body
        if {"x": my_head["x"] + 1, "y": my_head["y"]} == part:  # Right
            is_move_safe["right"] = False
        if {"x": my_head["x"] - 1, "y": my_head["y"]} == part:  # Left
            is_move_safe["left"] = False
        if {"x": my_head["x"], "y": my_head["y"] + 1} == part:  # Up
            is_move_safe["up"] = False
        if {"x": my_head["x"], "y": my_head["y"] - 1} == part:  # Down
            is_move_safe["down"] = False

    # Step 3 - Prevent your Battlesnake from colliding with other Battlesnakes
    opponents = game_state['board']['snakes']
    
    for snake in opponents:
        if snake["id"] == game_state["you"]["id"]:  # Skip our own snake
            continue
            
        for part in snake["body"][:-1]:  # Exclude opponent's head, as head-to-head collisions are handled differently
            # Check if moving in any direction would cause collision with opponent's body
            if {"x": my_head["x"] + 1, "y": my_head["y"]} == part:  # Right
                is_move_safe["right"] = False
            if {"x": my_head["x"] - 1, "y": my_head["y"]} == part:  # Left
                is_move_safe["left"] = False
            if {"x": my_head["x"], "y": my_head["y"] + 1} == part:  # Up
                is_move_safe["up"] = False
            if {"x": my_head["x"], "y": my_head["y"] - 1} == part:  # Down
                is_move_safe["down"] = False
    
    # Step 4 - Prevent your Battlesnake from moving into hazard squares
    if "hazards" in game_state["board"] and game_state["board"]["hazards"]:
        hazards = game_state["board"]["hazards"]
        for hazard in hazards:
            # Check if moving in any direction would cause collision with hazard
            if {"x": my_head["x"] + 1, "y": my_head["y"]} == hazard and is_move_safe["right"]:  # Right
                is_move_safe["right"] = False
            if {"x": my_head["x"] - 1, "y": my_head["y"]} == hazard and is_move_safe["left"]:  # Left
                is_move_safe["left"] = False
            if {"x": my_head["x"], "y": my_head["y"] + 1} == hazard and is_move_safe["up"]:  # Up
                is_move_safe["up"] = False
            if {"x": my_head["x"], "y": my_head["y"] - 1} == hazard and is_move_safe["down"]:  # Down
                is_move_safe["down"] = False
    
    # Additional safety: avoid head-to-head collisions if we would lose
    for snake in opponents:
        if snake["id"] == game_state["you"]["id"]:  # Skip our own snake
            continue
            
        # Check if opponent's head is adjacent to our head
        opponent_head = snake["body"][0]
        my_x, my_y = my_head["x"], my_head["y"]
        op_x, op_y = opponent_head["x"], opponent_head["y"]
        
        # Check if the opponent's head is one space away in any direction
        if abs(my_x - op_x) + abs(my_y - op_y) == 1:  # Adjacent
            # Check which direction the opponent's head is in relation to ours
            if my_x + 1 == op_x and is_move_safe["right"]:  # Opponent head to the right
                # Check if we'd lose in head-to-head
                if len(snake["body"]) >= len(my_body):
                    is_move_safe["right"] = False
            elif my_x - 1 == op_x and is_move_safe["left"]:  # Opponent head to the left
                if len(snake["body"]) >= len(my_body):
                    is_move_safe["left"] = False
            elif my_y + 1 == op_y and is_move_safe["up"]:  # Opponent head above
                if len(snake["body"]) >= len(my_body):
                    is_move_safe["up"] = False
            elif my_y - 1 == op_y and is_move_safe["down"]:  # Opponent head below
                if len(snake["body"]) >= len(my_body):
                    is_move_safe["down"] = False

    # Are there any safe moves left?
    safe_moves = []
    for move, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Evaluate safe moves based on future safety and area size
    future_safe_counts = {}
    accessible_areas = {}
    
    for move in safe_moves:
        # Calculate the position after this move
        if move == "up":
            next_pos = {"x": my_head["x"], "y": my_head["y"] + 1}
        elif move == "down":
            next_pos = {"x": my_head["x"], "y": my_head["y"] - 1}
        elif move == "left":
            next_pos = {"x": my_head["x"] - 1, "y": my_head["y"]}
        elif move == "right":
            next_pos = {"x": my_head["x"] + 1, "y": my_head["y"]}
        
        # Count how many safe moves would be available from this new position
        future_safe_counts[move] = count_safe_moves_from_position(next_pos, game_state, my_body)
        
        # Calculate accessible area from this new position
        accessible_areas[move] = calculate_accessible_area(next_pos, game_state, my_body)

    # Step 5 - Move towards food instead of random, to regain health and survive longer
    my_health = game_state["you"]["health"]
    food = game_state['board']['food']
    
    if len(food) > 0 and my_health < 50:  # Only seek food when health is low
        # Find the closest food
        head_x, head_y = my_head["x"], my_head["y"]
        closest_food = min(food, key=lambda f: abs(f["x"] - head_x) + abs(f["y"] - head_y))
        
        # Try to find a path to the food using A*
        path_to_food = a_star_pathfind(my_head, closest_food, game_state, my_body)
        
        if path_to_food and len(path_to_food) > 1:
            # Get the next step in the path
            next_step = path_to_food[1]  # First element is current position
            
            # Determine which move gets us to the next step
            preferred_move = None
            if next_step["x"] > my_head["x"]:
                preferred_move = "right"
            elif next_step["x"] < my_head["x"]:
                preferred_move = "left"
            elif next_step["y"] > my_head["y"]:
                preferred_move = "up"
            elif next_step["y"] < my_head["y"]:
                preferred_move = "down"
            
            # If the preferred move is safe, use it
            if preferred_move and preferred_move in safe_moves:
                # When health is critically low, be more aggressive about following the path
                if my_health < 30:
                    next_move = preferred_move
                else:
                    # Otherwise, still consider the path but also evaluate safety and area
                    best_move = preferred_move
                    for move in safe_moves:
                        # Prioritize moves with larger accessible areas first, then future safety
                        if (accessible_areas[move] > accessible_areas[best_move] or 
                            (accessible_areas[move] == accessible_areas[best_move] and 
                             future_safe_counts[move] > future_safe_counts[best_move])):
                            best_move = move
                    next_move = best_move
            else:
                # If path direction isn't safe, choose the safe move with the best future options and area
                next_move = safe_moves[0]
                for move in safe_moves:
                    # Prioritize moves with larger accessible areas first, then future safety
                    if (accessible_areas[move] > accessible_areas[next_move] or 
                        (accessible_areas[move] == accessible_areas[next_move] and 
                         future_safe_counts[move] > future_safe_counts[next_move])):
                        next_move = move
        else:
            # If no path exists to food, use the same logic as before
            # Create a list of moves that get closer to food
            preferred_moves = []
            
            # Horizontal moves
            food_x, food_y = closest_food["x"], closest_food["y"]
            if food_x < head_x and "left" in safe_moves:
                preferred_moves.append("left")
            elif food_x > head_x and "right" in safe_moves:
                preferred_moves.append("right")
                
            # Vertical moves
            if food_y < head_y and "down" in safe_moves:
                preferred_moves.append("down")
            elif food_y > head_y and "up" in safe_moves:
                preferred_moves.append("up")
            
            # If we have preferred moves, choose the one with the best future safety and area
            if preferred_moves:
                # If health is low, be more aggressive about getting food
                if my_health < 30:  # More aggressive when health is low
                    # Choose the move that gets us closer to food and has good future safety and area
                    best_move = preferred_moves[0]
                    for move in preferred_moves:
                        # Prioritize moves with larger accessible areas first, then future safety
                        if (accessible_areas[move] > accessible_areas[best_move] or 
                            (accessible_areas[move] == accessible_areas[best_move] and 
                             future_safe_counts[move] > future_safe_counts[best_move])):
                            best_move = move
                    next_move = best_move
                else:
                    # Choose a preferred move with good future safety and area
                    best_move = preferred_moves[0]
                    for move in preferred_moves:
                        # Prioritize moves with larger accessible areas first, then future safety
                        if (accessible_areas[move] > accessible_areas[best_move] or 
                            (accessible_areas[move] == accessible_areas[best_move] and 
                             future_safe_counts[move] > future_safe_counts[best_move])):
                            best_move = move
                    next_move = best_move
            else:
                # If no direct path to food is safe, choose the safe move with the most future options and area
                next_move = safe_moves[0]
                for move in safe_moves:
                    # Prioritize moves with larger accessible areas first, then future safety
                    if (accessible_areas[move] > accessible_areas[next_move] or 
                        (accessible_areas[move] == accessible_areas[next_move] and 
                         future_safe_counts[move] > future_safe_counts[next_move])):
                        next_move = move
    else:
        # If no food is available or health is sufficient, choose the safe move with the most future options and area
        next_move = safe_moves[0]
        for move in safe_moves:
            # Prioritize moves with larger accessible areas first, then future safety
            if (accessible_areas[move] > accessible_areas[next_move] or 
                (accessible_areas[move] == accessible_areas[next_move] and 
                 future_safe_counts[move] > future_safe_counts[next_move])):
                next_move = move

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})