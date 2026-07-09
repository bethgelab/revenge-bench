import typing
from collections import deque

def _get_moves_from_pos(pos: typing.Dict, game_state: typing.Dict) -> typing.List[str]:
    """
    A helper function that returns a list of safe moves from a given (x,y) position.
    Checks for:
    - Out of bounds
    - Self-collision
    - Opponent collision (including opponent heads, assuming we are smaller)
    Does NOT check for:
    - Backward move (neck)
    - Head-to-head collisions where we are larger (this is an aggressive move)
    """
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}
    my_body = game_state['you']['body']
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    opponents = game_state['board']['snakes']

    # 1. Prevent moving out of bounds
    if pos['x'] == 0: is_move_safe['left'] = False
    if pos['x'] == board_width - 1: is_move_safe['right'] = False
    if pos['y'] == 0: is_move_safe['down'] = False
    if pos['y'] == board_height - 1: is_move_safe['up'] = False

    # 2. Prevent colliding with self
    # We add the snake's head to the body set for the lookahead simulation
    body_parts = set((part['x'], part['y']) for part in my_body)
    if (pos['x'] - 1, pos['y']) in body_parts: is_move_safe['left'] = False
    if (pos['x'] + 1, pos['y']) in body_parts: is_move_safe['right'] = False
    if (pos['x'], pos['y'] - 1) in body_parts: is_move_safe['down'] = False
    if (pos['x'], pos['y'] + 1) in body_parts: is_move_safe['up'] = False

    # 3. Prevent colliding with other snakes
    opponent_bodies = set()
    for snake in opponents:
        if snake['id'] != game_state['you']['id']:
            # Treat the whole body of other snakes as obstacles
            for part in snake['body']:
                opponent_bodies.add((part['x'], part['y']))

    if (pos['x'] - 1, pos['y']) in opponent_bodies: is_move_safe['left'] = False
    if (pos['x'] + 1, pos['y']) in opponent_bodies: is_move_safe['right'] = False
    if (pos['x'], pos['y'] - 1) in opponent_bodies: is_move_safe['down'] = False
    if (pos['x'], pos['y'] + 1) in opponent_bodies: is_move_safe['up'] = False

    safe_moves = [move for move, is_safe in is_move_safe.items() if is_safe]
    return safe_moves

def find_safe_moves(game_state: typing.Dict) -> typing.List[str]:
    """
    Returns a list of safe moves for the snake's CURRENT head position.
    This function handles all primary safety checks.
    """
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]
    my_length = game_state['you']['length']
    opponents = game_state['board']['snakes']

    # Get standard safe moves from the current head position
    is_move_safe = {move: True for move in ["up", "down", "left", "right"]}

    # 1. Get standard safe moves (bounds, self, opponents)
    standard_safe_moves = _get_moves_from_pos(my_head, game_state)
    for move in ["up", "down", "left", "right"]:
        if move not in standard_safe_moves:
            is_move_safe[move] = False

    # 2. Prevent moving backwards
    if my_neck["x"] < my_head["x"]: is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]: is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]: is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]: is_move_safe["up"] = False

    # 3. Prevent head-to-head collisions with larger/equal snakes
    for snake in opponents:
        if snake['id'] != game_state['you']['id']:
            if len(snake['body']) >= my_length:
                opponent_head = snake['body'][0]
                # Check potential moves
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] + 1) - opponent_head['y']) < 2: is_move_safe['up'] = False
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] - 1) - opponent_head['y']) < 2: is_move_safe['down'] = False
                if abs((my_head['x'] - 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) < 2: is_move_safe['left'] = False
                if abs((my_head['x'] + 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) < 2: is_move_safe['right'] = False

    safe_moves = [move for move, is_safe in is_move_safe.items() if is_safe]
    return safe_moves

def bfs(game_state: typing.Dict, start: typing.Dict, end: typing.Dict) -> typing.Optional[typing.List[typing.Dict]]:
    """
    A simple Breadth-First Search to find a path from start to end.
    Returns a list of coordinates representing the path, or None if no path is found.
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Create a set of all obstacles for O(1) lookup.
    obstacles = set()
    for snake in game_state['board']['snakes']:
        for part in snake['body']:
            obstacles.add((part['x'], part['y']))

    # For any snake that is NOT about to eat, its tail will move.
    # So, we can remove it from the set of obstacles for pathfinding purposes.
    for snake in game_state['board']['snakes']:
        head = snake['body'][0]
        tail = snake['body'][-1]
        
        is_about_to_eat = False
        # Heuristic: if a snake's head is adjacent to food, it will eat.
        for food in game_state['board']['food']:
            if abs(head['x'] - food['x']) + abs(head['y'] - food['y']) == 1:
                is_about_to_eat = True
                break
        
        if not is_about_to_eat:
            # If the snake is not eating, its tail will move, freeing up the square.
            # We must ensure the tail is not the same as the head (for length 1 snakes).
            if (tail['x'], tail['y']) in obstacles and (tail['x'], tail['y']) != (head['x'], head['y']):
                 obstacles.remove((tail['x'], tail['y']))

    queue = deque([[start]])
    visited = set((start['x'], start['y']))

    while queue:
        path = queue.popleft()
        node = path[-1]

        if node['x'] == end['x'] and node['y'] == end['y']:
            return path

        # Explore neighbors
        for move in [(0, 1), (0, -1), (1, 0), (-1, 0)]: # Up, Down, Right, Left
            next_x = node['x'] + move[0]
            next_y = node['y'] + move[1]
            
            # Check if the next position is valid
            if (
                0 <= next_x < board_width and
                0 <= next_y < board_height and
                (next_x, next_y) not in obstacles and
                (next_x, next_y) not in visited
            ):
                visited.add((next_x, next_y))
                new_path = list(path)
                new_path.append({'x': next_x, 'y': next_y})
                queue.append(new_path)
    
    return None # No path found

def find_largest_safe_area(game_state: typing.Dict, move: str, future_obstacles: set = None) -> int:
    """
    Calculates the size of the contiguous safe area reachable from a given move.
    """
    my_head = game_state['you']['body'][0]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    start_pos = my_head.copy()
    if move == "up": start_pos["y"] += 1
    elif move == "down": start_pos["y"] -= 1
    elif move == "left": start_pos["x"] -= 1
    elif move == "right": start_pos["x"] += 1

    obstacles = set()
    if future_obstacles:
        obstacles.update(future_obstacles)
    for snake in game_state['board']['snakes']:
        for part in snake['body']:
            obstacles.add((part['x'], part['y']))
    
    # Simulate our snake's next move to correctly block its old tail position
    my_simulated_body = [start_pos] + game_state['you']['body'][:-1]
    for part in my_simulated_body:
        obstacles.add((part['x'], part['y']))

    q = deque([start_pos])
    visited = set([(start_pos['x'], start_pos['y'])])
    area_size = 0

    while q:
        pos = q.popleft()
        area_size += 1

        for d in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            next_x, next_y = pos['x'] + d[0], pos['y'] + d[1]

            if (
                0 <= next_x < board_width and
                0 <= next_y < board_height and
                (next_x, next_y) not in obstacles and
                (next_x, next_y) not in visited
            ):
                visited.add((next_x, next_y))
                q.append({'x': next_x, 'y': next_y})

    return area_size