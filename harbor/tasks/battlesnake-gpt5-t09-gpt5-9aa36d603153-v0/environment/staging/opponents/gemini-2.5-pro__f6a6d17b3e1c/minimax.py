import typing
import copy
from logic import find_largest_safe_area, _get_moves_from_pos

# Constants for evaluation
DEATH_PENALTY = -1000
FOOD_REWARD = 100
SPACE_CONTROL_WEIGHT = 1
HEALTH_WEIGHT = 0.5

def _get_move_from_pos_delta(start_pos, end_pos):
    """Helper to determine move direction string from two positions."""
    if end_pos['x'] > start_pos['x']: return 'right'
    if end_pos['x'] < start_pos['x']: return 'left'
    if end_pos['y'] > start_pos['y']: return 'up'
    return 'down'

def _get_new_head_pos(head, move):
    """Calculates the new head position given a move string."""
    new_head = head.copy()
    if move == 'up': new_head['y'] += 1
    elif move == 'down': new_head['y'] -= 1
    elif move == 'left': new_head['x'] -= 1
    elif move == 'right': new_head['x'] += 1
    return new_head

def _get_next_game_state(game_state: typing.Dict, my_move: str, opponent_moves: typing.Dict) -> typing.Dict:
    """
    Simulates one turn of the game to produce a new game_state.
    :param game_state: The current state of the game.
    :param my_move: The move for our snake.
    :param opponent_moves: A dict of {snake_id: move} for opponents.
    :return: A new game_state dictionary representing the board after one turn.
    """
    next_state = copy.deepcopy(game_state)
    next_state['turn'] += 1
    
    all_snakes = next_state['board']['snakes']
    my_id = next_state['you']['id']
    
    # 1. Move all snakes
    new_head_positions = {}
    for snake in all_snakes:
        snake_id = snake['id']
        move = my_move if snake_id == my_id else opponent_moves.get(snake_id, 'up') # Default 'up' if no move provided
        
        new_head = _get_new_head_pos(snake['body'][0], move)
        new_head_positions[snake_id] = new_head
        
        snake['body'].insert(0, new_head)
        # Tail doesn't pop yet, that happens after food check

    # 2. Handle food consumption
    food_eaten_indices = []
    for snake in all_snakes:
        head = snake['body'][0]
        for i, food in enumerate(next_state['board']['food']):
            if head['x'] == food['x'] and head['y'] == food['y']:
                snake['health'] = 100
                snake['length'] += 1
                if i not in food_eaten_indices:
                    food_eaten_indices.append(i)
                # Snake grows, so we don't pop the tail
                break
        else:
            # No food eaten, pop the tail
            snake['body'].pop()

    # Remove eaten food
    next_state['board']['food'] = [food for i, food in enumerate(next_state['board']['food']) if i not in food_eaten_indices]

    # 3. Handle collisions and starvation
    surviving_snakes = []
    
    # Get all body parts for collision checks
    all_bodies = {}
    for s in all_snakes:
        all_bodies[s['id']] = set((p['x'], p['y']) for p in s['body'])

    for snake in all_snakes:
        snake_id = snake['id']
        head_pos = (snake['body'][0]['x'], snake['body'][0]['y'])
        is_dead = False
        
        # 3a. Starvation
        snake['health'] -= 1
        if snake['health'] <= 0:
            is_dead = True
        
        # 3b. Wall collision
        if not (0 <= head_pos[0] < next_state['board']['width'] and 0 <= head_pos[1] < next_state['board']['height']):
            is_dead = True

        # 3c. Body collisions
        for other_snake in all_snakes:
            # Exclude the head for self-collision check
            body_to_check = other_snake['body'][1:] if other_snake['id'] == snake_id else other_snake['body']
            for part in body_to_check:
                if head_pos[0] == part['x'] and head_pos[1] == part['y']:
                    is_dead = True
                    break
            if is_dead: break
        
        # 3d. Head-to-head collisions
        for other_snake in all_snakes:
            if snake_id != other_snake['id']:
                other_head_pos = (other_snake['body'][0]['x'], other_snake['body'][0]['y'])
                if head_pos == other_head_pos:
                    if snake['length'] <= other_snake['length']:
                        is_dead = True
                        break
        
        if not is_dead:
            surviving_snakes.append(snake)

    next_state['board']['snakes'] = surviving_snakes

    # Update 'you' object separately
    my_snake_alive = False
    for s in surviving_snakes:
        if s['id'] == my_id:
            next_state['you'] = s
            my_snake_alive = True
            break
    if not my_snake_alive:
        # We died, create a dummy 'you' object to avoid key errors
        next_state['you'] = {'id': my_id, 'health': 0, 'body': [], 'length': 0}
        
    return next_state


def _evaluate_board(game_state: typing.Dict, my_id: str) -> float:
    """
    Scores the given game_state from the perspective of our snake.
    Higher score is better.
    """
    my_snake = None
    for snake in game_state['board']['snakes']:
        if snake['id'] == my_id:
            my_snake = snake
            break
    
    # If our snake is not on the board, we have lost.
    if my_snake is None:
        return DEATH_PENALTY
        
    # Heuristic 1: Space Control (Flood Fill)
    # A simple way to measure space is to see how much area is accessible.
    # We can use a simplified version of find_largest_safe_area's logic.
    my_head = my_snake['body'][0]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    obstacles = set()
    for s in game_state['board']['snakes']:
        for part in s['body']:
            obstacles.add((part['x'], part['y']))

    q = deque([my_head])
    visited = set([(my_head['x'], my_head['y'])])
    space_score = 0
    while q:
        pos = q.popleft()
        space_score += 1
        for d in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            next_x, next_y = pos['x'] + d[0], pos['y'] + d[1]
            if (0 <= next_x < board_width and 0 <= next_y < board_height and
                    (next_x, next_y) not in obstacles and
                    (next_x, next_y) not in visited):
                visited.add((next_x, next_y))
                q.append({'x': next_x, 'y': next_y})

    # Heuristic 2: Health
    health_score = my_snake['health']

    # Heuristic 3: Food Proximity (Bonus for being closer to food)
    food_bonus = 0
    if game_state['board']['food']:
        closest_food_dist = min(abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y']) for f in game_state['board']['food'])
        food_bonus = (board_width + board_height - closest_food_dist) # Larger bonus for smaller distance

    # Heuristic 4: Kill potential (being larger than others)
    length_advantage = 0
    for other in game_state['board']['snakes']:
        if other['id'] != my_id:
            if my_snake['length'] > other['length']:
                length_advantage += (my_snake['length'] - other['length'])

    final_score = (space_score * SPACE_CONTROL_WEIGHT) + \
                  (health_score * HEALTH_WEIGHT) + \
                   food_bonus + \
                   length_advantage

    return final_score