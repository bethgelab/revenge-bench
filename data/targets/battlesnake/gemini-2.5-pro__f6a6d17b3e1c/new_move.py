def move(game_state: typing.Dict) -> typing.Dict:
    # Step 0: Acknowledge variables from game_state
    my_head = game_state["you"]["body"][0]
    my_body = game_state['you']['body']
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    # Step 1: Get all safe moves from the current position
    safe_moves = find_safe_moves(game_state)
    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Step 2: Strategic BFS for Food
    # If hungry, iterate through all food, find the closest reachable one.
    if game_state['you']['health'] < 85: # Increased hunger threshold
        food_items = sorted(game_state['board']['food'], key=lambda f: abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y']))
        for food in food_items:
            path = bfs(game_state, my_head, food)
            if path and len(path) > 1:
                next_step = path[1]
                move_to_target = ''
                if next_step['x'] > my_head['x']: move_to_target = 'right'
                elif next_step['x'] < my_head['x']: move_to_target = 'left'
                elif next_step['y'] > my_head['y']: move_to_target = 'up'
                else: move_to_target = 'down'
                
                if move_to_target in safe_moves:
                    print(f"MOVE {game_state['turn']}: Found safe path to food! Moving {move_to_target}")
                    return {"move": move_to_target}

    # Step 3: Default Move - Flood Fill to find largest safe area
    # If no strategic move is made, find the move that leads to the most open space.
    move_area_sizes = {}
    for move in safe_moves:
        move_area_sizes[move] = find_largest_safe_area(game_state, move)
    
    # Choose the move that leads to the largest area.
    # If multiple moves have the same max area, pick one randomly.
    if move_area_sizes:
        max_area = -1
        best_moves = []
        # Sort moves to make random choice deterministic for testing if needed
        for move in sorted(move_area_sizes.keys()):
            area = move_area_sizes[move]
            if area > max_area:
                max_area = area
                best_moves = [move]
            elif area == max_area:
                best_moves.append(move)
        
        next_move = random.choice(best_moves)
        print(f"MOVE {game_state['turn']}: Defaulting to largest area ({max_area}). Moving {next_move}")
        return {"move": next_move}

    # Step 4: Fallback (should be rare)
    next_move = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: No ideal move, making random safe move: {next_move}")
    return {"move": next_move}