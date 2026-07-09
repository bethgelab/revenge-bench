# Step 2.5: Aggressive head-to-head with smaller snakes
    my_length = game_state['you']['length']
    
    # Get my possible next head positions based on safe moves
    my_next_positions = {}
    for move in safe_moves:
        pos = my_head.copy()
        if move == 'up': pos['y'] += 1
        elif move == 'down': pos['y'] -= 1
        elif move == 'left': pos['x'] -= 1
        elif move == 'right': pos['x'] += 1
        my_next_positions[move] = (pos['x'], pos['y'])

    # Check for opportunities against smaller snakes
    for opponent in game_state['board']['snakes']:
        if opponent['id'] != game_state['you']['id'] and opponent['length'] < my_length:
            opponent_head = opponent['body'][0]
            
            # Find where the opponent *could* move
            possible_opponent_moves = [
                {'x': opponent_head['x'], 'y': opponent_head['y'] + 1},
                {'x': opponent_head['x'], 'y': opponent_head['y'] - 1},
                {'x': opponent_head['x'] - 1, 'y': opponent_head['y']},
                {'x': opponent_head['x'] + 1, 'y': opponent_head['y']}
            ]

            # Check if any of our next positions match a possible opponent next position
            for my_move, my_next_pos_tuple in my_next_positions.items():
                for op_next_pos in possible_opponent_moves:
                    if my_next_pos_tuple == (op_next_pos['x'], op_next_pos['y']):
                        # Potential winning collision! Check if it's safe.
                        area_size = find_largest_safe_area(game_state, my_move, future_obstacles=set())
                        if area_size > 2: # Require some wiggle room
                            print(f"MOVE {game_state['turn']}: Winning head-to-head collision! Moving {my_move}")
                            return {"move": my_move}