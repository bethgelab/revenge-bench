# Step 4: Move towards food
    food = game_state['board']['food']
    my_head = game_state['you']['head']

    # Find the closest food
    closest_food = None
    min_distance = float('inf')

    for a_food in food:
        distance = abs(a_food['x'] - my_head['x']) + abs(a_food['y'] - my_head['y'])
        if distance < min_distance:
            min_distance = distance
            closest_food = a_food

    # If there is food on the board, move towards it
    if closest_food:
        move_to_food = []
        if closest_food['x'] > my_head['x']:
            move_to_food.append("right")
        elif closest_food['x'] < my_head['x']:
            move_to_food.append("left")
        
        if closest_food['y'] > my_head['y']:
            move_to_food.append("up")
        elif closest_food['y'] < my_head['y']:
            move_to_food.append("down")
        
        # Choose a safe move that moves towards the food
        for move in move_to_food:
            if move in safe_moves:
                print(f"MOVE {game_state['turn']}: {move} (towards food)")
                return {"move": move}

    # If no safe move towards food, make a random safe move
    next_move = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: {next_move} (random safe move)")
    return {"move": next_move}