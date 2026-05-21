import random
import typing


def head_to_body_collision_test(next_head: typing.Dict, body: typing.List[typing.Dict]) -> bool:
    """
    Return True if next_head would collide with a body part
    """
    return next_head in body


def move_towards_food_test(next_head: typing.Dict, food: typing.List[typing.Dict], current_head: typing.Dict) -> bool:
    """
    Return True if next_head is closer to any food than current head
    """
    if not food:
        return False

    # Calculate current distance to closest food
    min_current_distance = min(
        abs(current_head["x"] - f["x"]) + abs(current_head["y"] - f["y"]) for f in food
    )

    # Calculate new distance to closest food
    min_next_distance = min(
        abs(next_head["x"] - f["x"]) + abs(next_head["y"] - f["y"]) for f in food
    )

    return min_next_distance < min_current_distance


def get_safe_moves(my_head: typing.Dict, my_body: typing.List[typing.Dict], board_width: int, board_height: int, all_snakes: typing.List[typing.List[typing.Dict]]) -> typing.List[str]:
    """
    Get all moves that are safe (won't cause immediate collision)
    """
    possible_moves = ["up", "down", "left", "right"]
    safe_moves = []

    for move in possible_moves:
        if move == "up":
            next_head = {"x": my_head["x"], "y": my_head["y"] - 1}
        elif move == "down":
            next_head = {"x": my_head["x"], "y": my_head["y"] + 1}
        elif move == "left":
            next_head = {"x": my_head["x"] - 1, "y": my_head["y"]}
        elif move == "right":
            next_head = {"x": my_head["x"] + 1, "y": my_head["y"]}

        # Check if next_head is within board boundaries
        if (
            next_head["x"] >= 0
            and next_head["x"] < board_width
            and next_head["y"] >= 0
            and next_head["y"] < board_height
        ):
            # Check if next_head doesn't collide with my own body
            if not head_to_body_collision_test(next_head, my_body):
                # Check if next_head doesn't collide with any other snake
                is_safe = True
                for snake in all_snakes:
                    if next_head in snake:
                        is_safe = False
                        break
                
                if is_safe:
                    safe_moves.append(move)

    return safe_moves


def get_move_coords(move: str, head: typing.Dict) -> typing.Dict:
    """
    Get the coordinates of the head after making a move
    """
    if move == "up":
        return {"x": head["x"], "y": head["y"] - 1}
    elif move == "down":
        return {"x": head["x"], "y": head["y"] + 1}
    elif move == "left":
        return {"x": head["x"] - 1, "y": head["y"]}
    elif move == "right":
        return {"x": head["x"] + 1, "y": head["y"]}


def get_future_safety_score(move: str, head: typing.Dict, all_snakes: typing.List[typing.List[typing.Dict]], 
                           board_width: int, board_height: int, my_body: typing.List[typing.Dict]) -> int:
    """
    Calculate a safety score for a potential move by looking ahead
    """
    future_head = get_move_coords(move, head)
    
    # Count available moves from this position
    possible_dirs = ["up", "down", "left", "right"]
    safe_count = 0
    
    for direction in possible_dirs:
        next_pos = get_move_coords(direction, future_head)
        
        # Check if next_pos is within board boundaries
        if (
            next_pos["x"] >= 0
            and next_pos["x"] < board_width
            and next_pos["y"] >= 0
            and next_pos["y"] < board_height
        ):
            # Check if next_pos doesn't collide with my body (including future position)
            temp_body = [next_pos] + my_body  # Include new head in body
            if not head_to_body_collision_test(next_pos, temp_body[1:]):  # Don't include new head in collision check
                # Check if next_pos doesn't collide with any other snake
                is_safe = True
                for snake in all_snakes:
                    if next_pos in snake:
                        is_safe = False
                        break
                
                if is_safe:
                    safe_count += 1
    
    return safe_count


def choose_move(data: typing.Dict) -> str:
    """
    Main function to choose the next move for the snake
    """
    my_id = data["you"]["id"]
    my_body = data["you"]["body"]
    my_head = my_body[0]
    board_width = data["board"]["width"]
    board_height = data["board"]["height"]

    # Get all snake bodies (including my own) to avoid
    all_snakes = []
    for snake_data in data["board"]["snakes"]:
        if snake_data["id"] != my_id:  # Only add other snakes
            all_snakes.append(snake_data["body"])

    # Get safe moves
    safe_moves = get_safe_moves(my_head, my_body, board_width, board_height, all_snakes)

    # If no safe moves, just return a random move (will likely result in death)
    if not safe_moves:
        return random.choice(["up", "down", "left", "right"])

    # If only one safe move, take it
    if len(safe_moves) == 1:
        return safe_moves[0]

    # Get food
    food = data["board"]["food"]

    # Evaluate moves based on multiple factors
    move_scores = {}
    
    for move in safe_moves:
        score = 0
        next_head = get_move_coords(move, my_head)
        
        # Factor 1: Food attraction
        if food and move_towards_food_test(next_head, food, my_head):
            score += 10  # Higher score for moves getting closer to food
        
        # Factor 2: Future safety
        future_safety = get_future_safety_score(move, my_head, all_snakes, board_width, board_height, my_body)
        score += future_safety * 5  # Higher score for moves leading to safer positions
        
        # Factor 3: Avoid walls (prefer center positions when possible)
        distance_to_walls = min(
            next_head["x"], 
            board_width - 1 - next_head["x"], 
            next_head["y"], 
            board_height - 1 - next_head["y"]
        )
        score += distance_to_walls  # Higher score for positions further from walls
        
        move_scores[move] = score

    # Choose the move with the highest score
    best_move = max(move_scores, key=move_scores.get)
    return best_move


# Start the server and run the game
if __name__ == "__main__":
    from server import run_server
    run_server()