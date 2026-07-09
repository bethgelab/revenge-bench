# Of the moves with the largest area, prefer those that move closer to the center
        board_height = game_state['board']['height']
        center_x = board_width // 2
        center_y = board_height // 2

        best_center_dist = float('inf')
        best_move_for_center = None
        
        my_head = game_state["you"]["body"][0]

        for move in best_moves:
            head_copy = my_head.copy()
            if move == 'up':
                head_copy['y'] += 1
            elif move == 'down':
                head_copy['y'] -= 1
            elif move == 'left':
                head_copy['x'] -= 1
            elif move == 'right':
                head_copy['x'] += 1

            dist_to_center = abs(head_copy['x'] - center_x) + abs(head_copy['y'] - center_y)
            if dist_to_center < best_center_dist:
                best_center_dist = dist_to_center
                best_move_for_center = move
        
        next_move = best_move_for_center if best_move_for_center else random.choice(best_moves)