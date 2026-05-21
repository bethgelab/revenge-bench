import random
import typing
from collections import deque

# --- Battlesnake meta ---------------------------------------------------------
def info() -> typing.Dict:
    return {
        "apiversion": "1",
        "author": "team_o3",  # Battlesnake Username
        "color": "#228B22",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

# --- Helpers ------------------------------------------------------------------
def _adjacent(coord: typing.Dict[str, int], direction: str) -> typing.Dict[str, int]:
    if direction == "up":
        return {"x": coord["x"], "y": coord["y"] + 1}
    if direction == "down":
        return {"x": coord["x"], "y": coord["y"] - 1}
    if direction == "left":
        return {"x": coord["x"] - 1, "y": coord["y"]}
    if direction == "right":
        return {"x": coord["x"] + 1, "y": coord["y"]}
    raise ValueError("Invalid direction")

def _manhattan(a: typing.Dict[str, int], b: typing.Dict[str, int]) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def _flood_fill_size(
    start: typing.Dict[str, int],
    board_width: int,
    board_height: int,
    blocked: set[tuple[int, int]],
    max_iter: int = 100,
) -> int:
    """
    Simple BFS flood fill that counts how many squares are reachable from
    `start` without crossing any cell in `blocked`. Capped by `max_iter`
    for performance.
    """
    sx, sy = start["x"], start["y"]
    if (sx, sy) in blocked or sx < 0 or sy < 0 or sx >= board_width or sy >= board_height:
        return 0

    visited: set[tuple[int, int]] = set()
    q: deque[tuple[int, int]] = deque()
    q.append((sx, sy))

    while q and len(visited) < max_iter:
        x, y = q.popleft()
        if (x, y) in visited or (x, y) in blocked:
            continue
        visited.add((x, y))

        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < board_width
                and 0 <= ny < board_height
                and (nx, ny) not in blocked
                and (nx, ny) not in visited
            ):
                q.append((nx, ny))

    return len(visited)

# --- Core move logic ----------------------------------------------------------
def move(game_state: typing.Dict) -> typing.Dict:
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1] if len(game_state["you"]["body"]) > 1 else None
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]

    # -------------------------------------------------------------------------
    # Build occupied and danger sets
    occupied: set[tuple[int, int]] = set()
    dangerous: set[tuple[int, int]] = set()

    my_length = len(game_state["you"]["body"])

    # Other snakes: segments occupied + adjacent danger if head-to-head possible
    for snake in game_state["board"]["snakes"]:
        snake_id = snake["id"]
        opp_len = len(snake["body"])
        head = snake["body"][0]

        # All body segments are occupied
        for segment in snake["body"]:
            occupied.add((segment["x"], segment["y"]))

        # If opponent is equal or longer, their head neighbors are dangerous
        if snake_id != game_state["you"]["id"] and opp_len >= my_length:
            for mv2 in ("up", "down", "left", "right"):
                adj = _adjacent(head, mv2)
                if 0 <= adj["x"] < board_width and 0 <= adj["y"] < board_height:
                    dangerous.add((adj["x"], adj["y"]))

    # -------------------------------------------------------------------------
    # Determine safe moves
    possible_moves = ("up", "down", "left", "right")
    safe_moves: list[str] = []

    for mv in possible_moves:
        nx, ny = _adjacent(my_head, mv)["x"], _adjacent(my_head, mv)["y"]

        # Avoid reversing into neck
        if my_neck and (nx, ny) == (my_neck["x"], my_neck["y"]):
            continue
        # Within bounds
        if nx < 0 or nx >= board_width or ny < 0 or ny >= board_height:
            continue
        # Avoid bodies
        if (nx, ny) in occupied:
            continue
        # Avoid dangerous future head positions
        if (nx, ny) in dangerous:
            continue

        safe_moves.append(mv)

    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves. Moving down.")
        return {"move": "down"}

    # -------------------------------------------------------------------------
    # Evaluate space for each safe move (flood fill)
    blocked_cells = occupied.union(dangerous)
    space_scores: dict[str, int] = {}
    for mv in safe_moves:
        next_coord = _adjacent(my_head, mv)
        space_scores[mv] = _flood_fill_size(
            next_coord, board_width, board_height, blocked_cells, max_iter=150
        )

    max_space = max(space_scores.values())
    roomy_moves = [mv for mv, score in space_scores.items() if score == max_space]

    # -------------------------------------------------------------------------
    # Food consideration
    food_items = game_state["board"]["food"]
    health = game_state["you"]["health"]
    next_move: str

    if food_items and (health < 70 or len(roomy_moves) == 1):
        # Among roomy moves, pick the one that gets closest to food
        def dist_to_closest_food(mv: str) -> int:
            next_coord = _adjacent(my_head, mv)
            return min(_manhattan(next_coord, f) for f in food_items)

        next_move = min(roomy_moves, key=dist_to_closest_food)
    else:
        next_move = random.choice(roomy_moves)

    print(
        f"MOVE {game_state['turn']}: {next_move} | "
        f"safe={len(safe_moves)} roomy={len(roomy_moves)} "
        f"spacescore={space_scores[next_move]} health={health}"
    )
    return {"move": next_move}

# -----------------------------------------------------------------------------


if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})