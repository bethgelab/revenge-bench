# Step 4 - Move towards food instead of random, to regain health and survive longer
    food = game_state['board']['food']

    # Find the closest food
    closest_food = None
    min_dist = float('inf')
    for f in food:
        dist = abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y'])
        if dist < min_dist:
            min_dist = dist
            closest_food = f

    # If there is food, move towards it
    if closest_food:
        # Find the best moves towards the food
        best_moves = []
        if my_head['x'] < closest_food['x']:
            best_moves.append('right')
        elif my_head['x'] > closest_food['x']:
            best_moves.append('left')
        if my_head['y'] < closest_food['y']:
            best_moves.append('up')
        elif my_head['y'] > closest_food['y']:
            best_moves.append('down')
        
        # Filter best_moves to only include safe_moves
        food_seeking_moves = [move for move in best_moves if move in safe_moves]

        if len(food_seeking_moves) > 0:
            next_move = random.choice(food_seeking_moves)
            print(f"MOVE {game_state['turn']}: {next_move} (towards food)")
            return {"move": next_move}

    # Choose a random move from the safe ones if no food is found or no safe path to food
    next_move = random.choice(safe_moves)