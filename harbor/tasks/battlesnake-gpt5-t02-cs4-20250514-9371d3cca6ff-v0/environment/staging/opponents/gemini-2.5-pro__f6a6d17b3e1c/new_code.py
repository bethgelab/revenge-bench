# Step 4.1: Prevent head-to-head collisions with larger/equal snakes
    my_length = game_state['you']['length']
    for snake in opponents:
        if snake['id'] != game_state['you']['id']:
            if len(snake['body']) >= my_length:
                opponent_head = snake['body'][0]
                # up
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] + 1) - opponent_head['y']) == 1:
                    is_move_safe['up'] = False
                # down
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] - 1) - opponent_head['y']) == 1:
                    is_move_safe['down'] = False
                # left
                if abs((my_head['x'] - 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) == 1:
                    is_move_safe['left'] = False
                # right
                if abs((my_head['x'] + 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) == 1:
                    is_move_safe['right'] = False