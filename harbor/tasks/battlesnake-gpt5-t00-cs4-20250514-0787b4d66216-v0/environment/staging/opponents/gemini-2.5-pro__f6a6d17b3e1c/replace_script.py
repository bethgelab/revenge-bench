import re

with open('main.py', 'r') as f:
    content = f.read()

old_block = """    move_area_sizes = {}
    for move in safe_moves:
        move_area_sizes[move] = find_largest_safe_area(game_state, move)"""

new_block = """    move_area_sizes = {}
    # Step 3.1: Calculate future threats from opponents
    future_obstacles = set()
    opponents = game_state['board']['snakes']
    my_id = game_state['you']['id']
    for snake in opponents:
        if snake['id'] != my_id:
            opponent_head = snake['body'][0]
            # Use _get_moves_from_pos, which is a bit more general and safer here.
            possible_moves = _get_moves_from_pos(opponent_head, game_state)
            for move in possible_moves:
                if move == 'up': future_obstacles.add((opponent_head['x'], opponent_head['y'] + 1))
                elif move == 'down': future_obstacles.add((opponent_head['x'], opponent_head['y'] - 1))
                elif move == 'left': future_obstacles.add((opponent_head['x'] - 1, opponent_head['y']))
                elif move == 'right': future_obstacles.add((opponent_head['x'] + 1, opponent_head['y']))

    # Step 3.2: Run flood fill for each of our safe moves, considering future threats
    for move in safe_moves:
        move_area_sizes[move] = find_largest_safe_area(game_state, move, future_obstacles=future_obstacles)"""

new_content = content.replace(old_block, new_block)

with open('main.py', 'w') as f:
    f.write(new_content)