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
    
    # No path found - use consistent float('inf')
    return float('inf')

def manhattan_distance_tuple(pos1: tuple, pos2: tuple) -> int:
    """Calculate Manhattan distance between two tuple positions"""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def find_best_food_with_pathfinding(head: typing.Dict, food: typing.List[typing.Dict], game_state: typing.Dict) -> typing.Dict:
    """
    Find the food with the shortest actual path (not just Manhattan distance).
    If multiple foods have the same distance, prefer the one closer to center.
    """
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