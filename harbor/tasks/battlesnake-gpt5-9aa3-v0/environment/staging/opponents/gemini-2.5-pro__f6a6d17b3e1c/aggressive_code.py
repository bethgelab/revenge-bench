# Step 2.5: Aggressive head-to-head with smaller snakes
    my_length = game_state['you']['length']
    for move in safe_moves:
        next_head_pos = my_head.copy()
        if move == 'up': next_head_pos['y'] += 1
        elif move == 'down': next_head_pos['y'] -= 1
        elif move == 'left': next_head_pos['x'] -= 1
        elif move == 'right': next_head_pos['x'] += 1

        for opponent in game_state['board']['snakes']:
            if opponent['id'] != game_state['you']['id'] and opponent['length'] < my_length:
                opponent_head = opponent['body'][0]
                # Check if our next move is a potential head-on collision spot
                if abs(next_head_pos['x'] - opponent_head['x']) + abs(next_head_pos['y'] - opponent_head['y']) == 1:
                    print(f"MOVE {game_state['turn']}: Aggressive move {move} towards smaller snake {opponent['id']}")
                    return {"move": move}