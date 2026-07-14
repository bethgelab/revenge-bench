import typing
import random
from utils import flood_fill, get_safe_moves_for_snake
from game_state import GameState

def evaluate_board(game_state: GameState, my_id: str) -> float:
    """
    Scores the current game state from the perspective of our snake.
    Higher scores are better.
    This evaluation now considers our snake's status, opponent status, and food control.
    """
    my_snake = next((s for s in game_state.snakes if s["id"] == my_id), None)

    if my_snake is None:
        return -float('inf')

    if len(game_state.snakes) == 1:
        return float('inf')

    # Basic scores
    health_score = my_snake["health"]
    length_score = len(my_snake["body"])

    # Space control score (using flood fill)
    my_head = my_snake["body"][0]
    obstacles = set()
    for s in game_state.snakes:
        for body_part in s["body"]:
            obstacles.add(body_part)
    my_space_score = flood_fill(my_head, game_state.width, game_state.height, obstacles)

    # Opponent analysis
    opponent_space_score = 0
    opponent_threat_score = 0
    opponents = [s for s in game_state.snakes if s["id"] != my_id]
    
    for opponent in opponents:
        opponent_head = opponent["body"][0]
        
        # Calculate opponent's space and subtract it (less space for them is good)
        opponent_space = flood_fill(opponent_head, game_state.width, game_state.height, obstacles)
        opponent_space_score -= opponent_space

        # Threat analysis: penalize being next to a larger opponent's head
        if len(opponent["body"]) >= length_score:
            if abs(my_head[0] - opponent_head[0]) + abs(my_head[1] - opponent_head[1]) == 1:
                opponent_threat_score -= 500 # Heavy penalty for each threat

    # Food control score
    food_score = 0
    if game_state.food:
        food_distances = [abs(f[0] - my_head[0]) + abs(f[1] - my_head[1]) for f in game_state.food]
        # Bonus for being close to food, especially when hungry
        food_score = (100 - min(food_distances)) * (1.5 - (health_score / 100))

    # Final weighted score
    final_score = (
        health_score * 0.1
        + length_score * 50
        + my_space_score * 1.0
        + opponent_space_score * 0.5
        + opponent_threat_score
        + food_score * 0.5
    )
    
    return final_score

def minimax(game_state: GameState, depth: int, alpha: float, beta: float, maximizing_player: bool, my_id: str, opponent_ids: list[str]):
    """
    Minimax algorithm with alpha-beta pruning, adapted for multiple opponents.
    """
    my_snake = next((s for s in game_state.snakes if s["id"] == my_id), None)
    
    active_opponents = [s for s in game_state.snakes if s["id"] in opponent_ids]
    
    if depth == 0 or my_snake is None or not active_opponents or my_snake["health"] <= 0:
        return evaluate_board(game_state, my_id)

    if maximizing_player:
        max_eval = -float('inf')
        safe_moves = get_safe_moves_for_snake(my_snake, game_state)
        if not safe_moves:
            return evaluate_board(game_state, my_id)

        for move in safe_moves:
            future_state = game_state.simulate_move(my_id, move)
            eval = minimax(future_state, depth - 1, alpha, beta, False, my_id, opponent_ids)
            max_eval = max(max_eval, eval)
            alpha = max(alpha, eval)
            if beta <= alpha:
                break
        return max_eval
    else: # Minimizing player (Paranoid Minimax)
        min_eval = float('inf')
        
        # Find the opponent move that is worst for us
        for opponent in active_opponents:
            opponent_worst_case = float('inf')
            safe_moves = get_safe_moves_for_snake(opponent, game_state)
            if not safe_moves:
                # If an opponent has no moves, this is good for us, but for paranoia, let's just evaluate
                eval = evaluate_board(game_state, my_id)
            else:
                for move in safe_moves:
                    future_state = game_state.simulate_move(opponent["id"], move)
                    eval = minimax(future_state, depth - 1, alpha, beta, True, my_id, opponent_ids)
                    opponent_worst_case = min(opponent_worst_case, eval)
            
            # The overall worst case is the minimum of all opponents' worst cases
            min_eval = min(min_eval, opponent_worst_case)
            beta = min(beta, min_eval)
            if beta <= alpha:
                break # Prune
        
        return min_eval

def find_best_move_with_lookahead(game_state_dict: typing.Dict, depth: int) -> typing.Optional[str]:
    gs = GameState(game_state_dict)

    my_snake_data = next((s for s in gs.snakes if s["id"] == game_state_dict["you"]["id"]), None)
    if not my_snake_data: return "up"

    opponents = [s for s in gs.snakes if s["id"] != my_snake_data["id"]]
    
    if not opponents:
        safe_moves = get_safe_moves_for_snake(my_snake_data, gs)
        return random.choice(safe_moves) if safe_moves else "up"

    opponent_ids = [o["id"] for o in opponents]
    safe_moves = get_safe_moves_for_snake(my_snake_data, gs)
    
    if not safe_moves:
        return None

    best_move = random.choice(safe_moves) if safe_moves else "up"
    best_score = -float('inf')

    for move in safe_moves:
        future_state = gs.simulate_move(my_snake_data["id"], move)
        score = minimax(future_state, depth - 1, -float('inf'), float('inf'), False, my_snake_data["id"], opponent_ids)
        
        if score > best_score:
            best_score = score
            best_move = move
            
    return best_move