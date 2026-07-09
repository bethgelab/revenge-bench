import typing
# Import GameState for type hinting, handle potential circular import if needed
# from game_state import GameState 

def flood_fill(start_pos: tuple, board_width: int, board_height: int, obstacles: set) -> int:
    """
    Performs a flood fill to count the number of reachable squares from a starting position.
    start_pos is now a tuple (x, y).
    """
    if start_pos in obstacles:
        return 0

    count = 0
    queue = [start_pos]
    visited = {start_pos}

    while queue:
        current_x, current_y = queue.pop(0)
        count += 1

        # Explore neighbors
        for move_offset in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            next_x = current_x + move_offset[0]
            next_y = current_y + move_offset[1]
            next_pos = (next_x, next_y)

            if (
                0 <= next_x < board_width and
                0 <= next_y < board_height and
                next_pos not in obstacles and
                next_pos not in visited
            ):
                visited.add(next_pos)
                queue.append(next_pos)

    return count

def get_safe_moves_for_snake(snake: typing.Dict, game_state) -> list:
    """
    Takes a snake dictionary (from GameState.snakes) and a GameState object.
    Returns a list of safe moves.
    """
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}
    
    # The snake body is now a list of tuples (x, y)
    head = snake["body"][0]
    head_x, head_y = head

    # Prevent moving backwards
    if len(snake["body"]) > 1:
        neck = snake["body"][1]
        neck_x, neck_y = neck
        if neck_x < head_x:
            is_move_safe["left"] = False
        elif neck_x > head_x:
            is_move_safe["right"] = False
        elif neck_y < head_y:
            is_move_safe["down"] = False
        elif neck_y > head_y:
            is_move_safe["up"] = False

    # Prevent moving out of bounds
    if head_x == 0:
        is_move_safe["left"] = False
    if head_x == game_state.width - 1:
        is_move_safe["right"] = False
    if head_y == 0:
        is_move_safe["down"] = False
    if head_y == game_state.height - 1:
        is_move_safe["up"] = False

    # Prevent collisions with all snakes
    obstacles = set()
    for s in game_state.snakes:
        # The whole body is an obstacle
        for body_part in s['body']:
            obstacles.add(body_part)

    future_head_positions = {
        "up": (head_x, head_y + 1),
        "down": (head_x, head_y - 1),
        "left": (head_x - 1, head_y),
        "right": (head_x + 1, head_y),
    }

    for move, future_head in future_head_positions.items():
        if future_head in obstacles:
            is_move_safe[move] = False

    safe_moves = [move for move, is_safe in is_move_safe.items() if is_safe]
    return safe_moves