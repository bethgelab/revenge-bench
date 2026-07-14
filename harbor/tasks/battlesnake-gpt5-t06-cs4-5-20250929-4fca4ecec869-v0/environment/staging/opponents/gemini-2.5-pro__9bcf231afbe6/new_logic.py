# When health is high, move to maximize space
    if my_health >= 50:
        best_move = ""
        max_space = -1
        
        # Create a set of all obstacles for flood fill
        obstacles_for_flood_fill = set()
        for snake in game_state["board"]["snakes"]:
            for body_part in snake["body"]:
                obstacles_for_flood_fill.add((body_part["x"], body_part["y"]))

        for move in safe_moves:
            future_head = future_head_positions[move]
            space = flood_fill(future_head, board_width, board_height, obstacles_for_flood_fill)
            if space > max_space:
                max_space = space
                best_move = move
        
        if best_move:
            next_move = best_move
        else:
            # Fallback to random if no move improves space (should not happen with safe_moves)
            next_move = random.choice(safe_moves)
    else:
        # Find paths to all food
        paths_to_food = []
        for food in game_state['board']['food']:
            path = find_shortest_path(game_state, my_head, food)
            if path:
                paths_to_food.append(path)

        # Choose the shortest path
        if paths_to_food:
            shortest_path = min(paths_to_food, key=len)
            if shortest_path[0] in safe_moves:
                next_move = shortest_path[0]
        else:
            # If no path to food, try to maximize space instead of just random
            best_move = ""
            max_space = -1
            
            obstacles_for_flood_fill = set()
            for snake in game_state["board"]["snakes"]:
                for body_part in snake["body"]:
                    obstacles_for_flood_fill.add((body_part["x"], body_part["y"]))

            for move in safe_moves:
                future_head = future_head_positions[move]
                space = flood_fill(future_head, board_width, board_height, obstacles_for_flood_fill)
                if space > max_space:
                    max_space = space
                    best_move = move
            
            if best_move:
                next_move = best_move
            else:
                next_move = random.choice(safe_moves)