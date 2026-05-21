# Step 4.5 - Endgame optimization: tail chasing when safe
    opponent_snakes = [s for s in opponents if s["id"] != game_state["you"]["id"]]
    
    # If no opponents left or we have significant length advantage, consider tail chasing
    should_tail_chase = False
    if len(opponent_snakes) == 0:
        should_tail_chase = True
        print(f"MOVE {game_state['turn']}: No opponents left - enabling tail chasing")
    elif len(opponent_snakes) == 1 and my_length > opponent_snakes[0].get("health", 0) + 5:
        should_tail_chase = True
        print(f"MOVE {game_state['turn']}: Large length advantage - enabling tail chasing")
    
    if should_tail_chase and my_health > 50:
        # Try to follow our own tail to maintain space
        my_tail = my_body[-1]
        tail_scores = []
        
        for direction in safe_moves:
            next_pos = get_next_position(my_head, direction)
            # Calculate distance to our tail
            tail_distance = abs(next_pos["x"] - my_tail["x"]) + abs(next_pos["y"] - my_tail["y"])
            # Also consider space control
            space_score = calculate_space_control(next_pos, game_state)
            # Combine scores (closer to tail is better, more space is better)
            combined_score = -tail_distance + space_score * 0.5
            tail_scores.append((direction, combined_score))
        
        if tail_scores:
            tail_scores.sort(key=lambda x: x[1], reverse=True)
            best_tail_move = tail_scores[0][0]
            print(f"MOVE {game_state['turn']}: Tail chasing - moving {best_tail_move}")
            return {"move": best_tail_move}