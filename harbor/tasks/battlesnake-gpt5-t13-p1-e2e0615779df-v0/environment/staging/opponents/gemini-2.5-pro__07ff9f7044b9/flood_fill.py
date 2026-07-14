import collections

def count_accessible_area(game_state: dict, start_pos: dict, threat_map: dict = None, my_length: int = 0) -> float:
    """
    Calculates a weighted score for the accessible area from a starting position.
    The score is based on the safety of the tiles:
    - Safe tile: 1.0
    - Tile threatened by a smaller snake: 1.5 (potential kill zone)
    - Tile threatened by a larger/equal snake: 0.05 (danger zone)
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Obstacles are absolute barriers (our body, other snake bodies)
    obstacles = set()
    for snake in game_state['board']['snakes']:
        # Our own tail is not an obstacle for the next move
        if snake['id'] == game_state['you']['id']:
            for segment in snake['body'][:-1]:
                obstacles.add((segment['x'], segment['y']))
        else:
            # For other snakes, their entire body is a potential obstacle.
            for segment in snake['body']:
                obstacles.add((segment['x'], segment['y']))

    start_coord = (start_pos['x'], start_pos['y'])
    
    # The starting position cannot be an obstacle
    if start_coord in obstacles:
        return 0

    queue = collections.deque([start_coord])
    visited = {start_coord}
    area_score = 0.0

    while queue:
        x, y = queue.popleft()
        
        current_coord = (x, y)
        opponent_length = threat_map.get(current_coord) if threat_map else None

        if opponent_length is not None:
            if my_length > opponent_length:
                area_score += 1.5  # Opportunity tile
            else:
                area_score += 0.05 # Danger tile
        else:
            area_score += 1.0  # Safe tile

        # Explore neighbors
        for move_x, move_y in [(0, 1), (0, -1), (1, 0), (-1, 0)]: # Up, Down, Right, Left
            next_x, next_y = x + move_x, y + move_y
            next_coord = (next_x, next_y)
            
            # Check if the next move is valid and not visited
            if (0 <= next_x < board_width and
                0 <= next_y < board_height and
                next_coord not in obstacles and
                next_coord not in visited):
                
                visited.add(next_coord)
                queue.append(next_coord)
    
    return area_score