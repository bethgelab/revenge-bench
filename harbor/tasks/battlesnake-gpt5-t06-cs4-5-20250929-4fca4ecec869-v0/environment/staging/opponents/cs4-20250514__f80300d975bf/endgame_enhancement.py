# Endgame enhancement for tail-chasing when we have length advantage

def should_use_tail_chasing(game_state):
    """Determine if we should use tail-chasing strategy"""
    my_snake = game_state['you']
    my_length = len(my_snake['body'])
    
    # Only consider tail-chasing if we have significant length advantage
    opponents = [s for s in game_state['board']['snakes'] if s['id'] != my_snake['id']]
    if not opponents:
        return False
    
    max_opponent_length = max(len(opp['body']) for opp in opponents)
    
    # Use tail-chasing if we're significantly longer AND health is decent
    length_advantage = my_length - max_opponent_length
    my_health = my_snake['health']
    
    return length_advantage >= 5 and my_health > 30

def get_tail_chasing_move(game_state, safe_moves):
    """Get move that follows our own tail when we have length advantage"""
    if not safe_moves:
        return None
    
    my_head = game_state['you']['head']
    my_tail = game_state['you']['body'][-1]
    
    # Calculate distance to tail for each safe move
    tail_distances = []
    for direction in safe_moves:
        from main import get_next_position, manhattan_distance
        next_pos = get_next_position(my_head, direction)
        distance = manhattan_distance(next_pos, my_tail)
        tail_distances.append((direction, distance))
    
    # Choose move that gets us closest to our tail
    tail_distances.sort(key=lambda x: x[1])
    return tail_distances[0][0]