import typing

def flood_fill(start_x, start_y, game_state, my_snake, ate_food=False):
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Check if starting point is initially invalid
    if start_x < 0 or start_x >= board_width or start_y < 0 or start_y >= board_height:
        return 0
    
    for s in game_state['board']['snakes']:
        for bp in s['body']:
            if start_x == bp['x'] and start_y == bp['y']:
                return 0

    count = 0
    queue = [(start_x, start_y)]
    visited = set()
    visited.add((start_x, start_y))
    
    food = game_state['board']['food']
    all_snakes = game_state['board']['snakes']
    my_id = my_snake['id']
    my_head = my_snake['body'][0]
    my_length = len(my_snake['body'])

    while queue:
        x, y = queue.pop(0)
        count += 1

        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited:
                # Check board boundaries
                if nx < 0 or nx >= board_width or ny < 0 or ny >= board_height:
                    continue

                # Check for any snake body parts
                is_occupied = False
                for s in all_snakes:
                    head = s['body'][0]
                    
                    # Determine if the snake will eat and grow
                    will_eat = False
                    if s['id'] == my_id:
                        will_eat = ate_food
                    else:
                        # A simple prediction for other snakes
                        if len(s['body']) > 1: # Avoid index out of bounds on short snakes
                           neck = s['body'][1]
                           for f in food:
                               if abs(head['x'] - f['x']) + abs(head['y'] - f['y']) == 1:
                                   # Check if food is not in the opponent's neck
                                   if f['x'] != neck['x'] or f['y'] != neck['y']:
                                       # ADDED LOGIC: Check if this move is suicidal for the opponent
                                       is_suicidal = False
                                       if abs(f['x'] - my_head['x']) + abs(f['y'] - my_head['y']) <= 1 and my_length >= len(s['body']):
                                           is_suicidal = True
                                       
                                       if not is_suicidal:
                                           will_eat = True
                                           break
                    
                    # Check body parts, ignoring the tail if the snake will not eat
                    body_to_check = s['body']
                    if not will_eat and len(body_to_check) > 0:
                        body_to_check = body_to_check[:-1]

                    for bp in body_to_check:
                        if nx == bp['x'] and ny == bp['y']:
                            is_occupied = True
                            break
                    if is_occupied:
                        break
                
                if not is_occupied:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
    return count

def is_largest_snake(game_state: dict) -> bool:
    """
    Checks if our snake is the largest on the board.
    """
    my_length = len(game_state['you']['body'])
    for snake in game_state['board']['snakes']:
        if snake['id'] != game_state['you']['id']:
            if len(snake['body']) >= my_length:
                return False
    return True