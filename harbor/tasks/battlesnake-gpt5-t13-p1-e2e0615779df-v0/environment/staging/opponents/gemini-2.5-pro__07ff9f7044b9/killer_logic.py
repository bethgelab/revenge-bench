import typing
import pathfinding
import collections

def _calculate_opponent_area(game_state: dict, target_snake: dict) -> int:
    """
    Calculates the number of accessible tiles for a specific opponent snake,
    considering our potential moves as threats.
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    my_head = game_state['you']['body'][0]
    start_pos = target_snake['body'][0]
    
    # Define our potential next moves as threats to the opponent
    my_potential_moves = {
        (my_head['x'], my_head['y'] + 1),
        (my_head['x'], my_head['y'] - 1),
        (my_head['x'] + 1, my_head['y']),
        (my_head['x'] - 1, my_head['y']),
    }

    # Obstacles are all snake bodies, except for the target's own tail
    obstacles = set()
    for snake in game_state['board']['snakes']:
        if snake['id'] == target_snake['id']:
            for segment in snake['body'][:-1]:
                obstacles.add((segment['x'], segment['y']))
        else:
            for segment in snake['body']:
                obstacles.add((segment['x'], segment['y']))

    start_coord = (start_pos['x'], start_pos['y'])

    # The starting position must not be an obstacle
    if start_coord in obstacles:
        return 0

    queue = collections.deque([start_coord])
    visited = {start_coord}
    count = 0

    while queue:
        x, y = queue.popleft()
        # Do not count squares we are threatening
        if (x,y) in my_potential_moves:
            continue
        count += 1

        # Explore neighbors
        for move_x, move_y in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            next_x, next_y = x + move_x, y + move_y
            next_coord = (next_x, next_y)
            
            # Check if the next move is valid and not visited
            if (0 <= next_x < board_width and
                0 <= next_y < board_height and
                next_coord not in obstacles and
                next_coord not in visited):
                
                visited.add(next_coord)
                queue.append(next_coord)
    
    return count


def get_killer_move(game_state: typing.Dict, safe_moves: typing.List[str], potential_moves: typing.Dict, unsafe_coords: set) -> typing.Union[str, None]:
    """
    Identifies the most vulnerable smaller snake and returns a move to chase its head.
    Vulnerability is determined by the amount of space the opponent has, considering our threat.
    """
    my_head = game_state["you"]["body"][0]
    my_length = game_state["you"]["length"]
    opponents = [s for s in game_state['board']['snakes'] if s['id'] != game_state['you']['id']]
    
    smaller_opponents = [opp for opp in opponents if opp['length'] < my_length]

    if not smaller_opponents:
        return None

    target_data = []
    for target in smaller_opponents:
        target_head = target['body'][0]
        # Pathfinding now uses the new Dijkstra's and is risk-aware
        path = pathfinding.find_path(game_state, my_head, target_head, unsafe_coords)
        if path:
            # Calculate the area available to the target snake, considering our threat
            available_area = _calculate_opponent_area(game_state, target)
            target_data.append({
                'path': path,
                'target': target,
                'area': available_area
            })

    if not target_data:
        return None

    # Sort targets by available area (ascending), then path length (ascending)
    target_data.sort(key=lambda x: (x['area'], len(x['path'])))
    
    best_target_info = target_data[0]
    shortest_path = best_target_info['path']
    
    if shortest_path and len(shortest_path) > 1:
        next_step = shortest_path[1]
        move = ""
        
        if next_step[0] > my_head['x']:
            move = "right"
        elif next_step[0] < my_head['x']:
            move = "left"
        elif next_step[1] > my_head['y']:
            move = "up"
        elif next_step[1] < my_head['y']:
            move = "down"

        if move in safe_moves:
            print(f"KILLER MODE: Chasing trapped snake {best_target_info['target']['name']} with move {move} (Opponent Area: {best_target_info['area']}, Dist: {len(shortest_path)-1})")
            return move
            
    return None