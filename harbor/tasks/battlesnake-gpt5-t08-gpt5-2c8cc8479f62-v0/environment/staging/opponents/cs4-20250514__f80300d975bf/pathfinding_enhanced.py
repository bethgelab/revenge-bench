import typing
import heapq
from collections import deque

def a_star_distance(start: typing.Dict, goal: typing.Dict, game_state: typing.Dict) -> int:
    """
    Calculate actual shortest path distance using A* algorithm.
    Returns the path length, or float('inf') if no path exists.
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Get all occupied positions (snake bodies, excluding tails which will move)
    occupied = set()
    for snake in game_state['board']['snakes']:
        for segment in snake['body'][:-1]:  # Exclude tail
            occupied.add((segment['x'], segment['y']))
    
    # A* algorithm
    start_pos = (start['x'], start['y'])
    goal_pos = (goal['x'], goal['y'])
    
    if start_pos == goal_pos:
        return 0
    
    # Priority queue: (f_score, g_score, position)
    open_set = [(0, 0, start_pos)]
    came_from = {}
    g_score = {start_pos: 0}
    f_score = {start_pos: manhattan_distance_tuple(start_pos, goal_pos)}
    
    while open_set:
        current_f, current_g, current = heapq.heappop(open_set)
        
        if current == goal_pos:
            return current_g
        
        # Check all neighbors
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            neighbor = (current[0] + dx, current[1] + dy)
            
            # Skip if out of bounds
            if (neighbor[0] < 0 or neighbor[0] >= board_width or 
                neighbor[1] < 0 or neighbor[1] >= board_height):
                continue
            
            # Skip if occupied by snake body
            if neighbor in occupied:
                continue
            
            tentative_g = current_g + 1
            
            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + manhattan_distance_tuple(neighbor, goal_pos)
                heapq.heappush(open_set, (f_score[neighbor], tentative_g, neighbor))
    
    return float('inf')  # No path found

def manhattan_distance_tuple(pos1: tuple, pos2: tuple) -> int:
    """Calculate Manhattan distance between two positions (tuples)"""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def manhattan_distance(pos1: typing.Dict, pos2: typing.Dict) -> int:
    """Calculate Manhattan distance between two positions"""
    return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])

def find_best_food_with_competition_logic(head: typing.Dict, food: typing.List[typing.Dict], game_state: typing.Dict) -> typing.Dict:
    """
    Enhanced food selection with competition logic.
    Avoids foods where opponents have significant advantage.
    """
    if not food:
        return None
    
    my_snake = game_state['you']
    opponents = [snake for snake in game_state['board']['snakes'] if snake['id'] != my_snake['id']]
    
    board_center_x = game_state['board']['width'] // 2
    board_center_y = game_state['board']['height'] // 2
    
    food_options = []
    
    for food_item in food:
        my_distance = a_star_distance(head, food_item, game_state)
        if my_distance == float('inf'):
            continue  # Skip unreachable food
        
        # Check opponent distances to this food
        min_opponent_distance = float('inf')
        for opponent in opponents:
            opp_distance = manhattan_distance(opponent['head'], food_item)  # Use Manhattan for speed
            min_opponent_distance = min(min_opponent_distance, opp_distance)
        
        # Calculate competition factor
        if min_opponent_distance == float('inf'):
            competition_penalty = 0  # No competition
        else:
            # Penalty if opponent is closer or tied
            distance_diff = my_distance - min_opponent_distance
            if distance_diff > 0:
                # We're farther - apply penalty based on how much farther
                competition_penalty = distance_diff * 2  # Penalty for being behind
            else:
                # We're closer or tied - small bonus
                competition_penalty = distance_diff * 0.5  # Small bonus for being ahead
        
        # Calculate distance to center as tiebreaker
        center_distance = abs(food_item['x'] - board_center_x) + abs(food_item['y'] - board_center_y)
        
        # Combined score: actual distance + competition penalty
        total_score = my_distance + competition_penalty
        
        food_options.append((total_score, center_distance, food_item, my_distance, min_opponent_distance))
    
    if not food_options:
        return None
    
    # Sort by total score (distance + competition), then by center distance
    food_options.sort(key=lambda x: (x[0], x[1]))
    
    best_option = food_options[0]
    print(f"Food competition analysis: target at {best_option[2]}, our distance: {best_option[3]}, opponent min: {best_option[4]}")
    
    return best_option[2]

def find_best_food_with_pathfinding(head: typing.Dict, food: typing.List[typing.Dict], game_state: typing.Dict) -> typing.Dict:
    """
    Find the food with the shortest actual path, considering competition.
    Falls back to original logic if competition logic fails.
    """
    # Try enhanced competition logic first
    try:
        result = find_best_food_with_competition_logic(head, food, game_state)
        if result:
            return result
    except Exception as e:
        print(f"Competition logic failed, falling back to original: {e}")
    
    # Fallback to original logic
    if not food:
        return None
    
    best_food = None
    best_distance = float('inf')
    board_center_x = game_state['board']['width'] // 2
    board_center_y = game_state['board']['height'] // 2
    
    food_options = []
    
    for food_item in food:
        distance = a_star_distance(head, food_item, game_state)
        if distance < float('inf'):  # Only consider reachable food
            # Calculate distance to center as tiebreaker
            center_distance = abs(food_item['x'] - board_center_x) + abs(food_item['y'] - board_center_y)
            food_options.append((distance, center_distance, food_item))
    
    if not food_options:
        return None
    
    # Sort by path distance first, then by center distance (prefer center)
    food_options.sort(key=lambda x: (x[0], x[1]))
    
    return food_options[0][2]