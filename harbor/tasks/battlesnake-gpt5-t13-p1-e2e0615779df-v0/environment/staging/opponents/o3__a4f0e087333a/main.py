import random
import typing
from collections import deque

# -----------------------------------------------------------------------------
# Appearance & metadata
def info() -> typing.Dict:
    return {
        "apiversion": "1",
        "author": "team-o3",
        "color": "#00BFFF",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

# -----------------------------------------------------------------------------
# Helpers
DIRECTIONS = {
    "up": (0, 1),
    "down": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}

def adjacent(coord: typing.Dict[str, int], direction: str) -> typing.Dict[str, int]:
    dx, dy = DIRECTIONS[direction]
    return {"x": coord["x"] + dx, "y": coord["y"] + dy}

def manhattan(a: typing.Dict[str, int], b: typing.Dict[str, int]) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def possible_head_moves(head, width, height):
    """Squares a head could move to next turn (ignores bodies)."""
    moves = set()
    for dx, dy in DIRECTIONS.values():
        nx, ny = head["x"] + dx, head["y"] + dy
        if 0 <= nx < width and 0 <= ny < height:
            moves.add((nx, ny))
    return moves

def flood_fill(start_xy: tuple[int, int], blocked: set[tuple[int, int]],
               width: int, height: int, max_iter: int = 200) -> int:
    """
    Simple BFS counting reachable empty squares from start_xy.
    The search is capped at max_iter to keep runtime bounded.
    """
    if start_xy in blocked:
        return 0
    q = deque([start_xy])
    visited = {start_xy}
    while q and len(visited) < max_iter:
        x, y = q.popleft()
        for dx, dy in DIRECTIONS.values():
            nx, ny = x + dx, y + dy
            if (0 <= nx < width and 0 <= ny < height
                    and (nx, ny) not in blocked
                    and (nx, ny) not in visited):
                visited.add((nx, ny))
                q.append((nx, ny))
    return len(visited)

# -----------------------------------------------------------------------------
# Core move logic
def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    you = game_state["you"]
    width, height = board["width"], board["height"]
    head = you["head"]

    # Track safety of each move
    is_move_safe = {d: True for d in DIRECTIONS.keys()}

    # -------------------------------------------------------------------------
    # 1. Out-of-bounds prevention
    for d in is_move_safe.keys():
        nx, ny = adjacent(head, d).values()
        if not (0 <= nx < width and 0 <= ny < height):
            is_move_safe[d] = False

    # -------------------------------------------------------------------------
    # 2. Body collision prevention
    occupied = set()
    tails_to_free = set()
    for snake in board["snakes"]:
        for i, seg in enumerate(snake["body"]):
            occupied.add((seg["x"], seg["y"]))
            # Save tail segments to potentially free (snake tails move next turn)
            if i == len(snake["body"]) - 1:
                tails_to_free.add((seg["x"], seg["y"]))

    for d in is_move_safe.keys():
        next_xy = tuple(adjacent(head, d).values())
        if next_xy in occupied:
            is_move_safe[d] = False

    # -------------------------------------------------------------------------
    # 3. Head-to-head avoidance
    safe_moves = [m for m, ok in is_move_safe.items() if ok]
    if safe_moves:
        my_len = len(you["body"])
        danger = set()
        for snake in board["snakes"]:
            if snake["id"] == you["id"]:
                continue
            if len(snake["body"]) >= my_len:
                danger.update(possible_head_moves(snake["head"], width, height))
        safer = [m for m in safe_moves
                 if tuple(adjacent(head, m).values()) not in danger]
        if safer:
            safe_moves = safer

    # If no safe moves, fallback
    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves, moving down")
        return {"move": "down"}

    # -------------------------------------------------------------------------
    # 4. Evaluate space availability via floodâfill
    #    Allow tails to be free (remove them from blocked set)
    blocked = occupied - tails_to_free
    space_by_move = {}
    for m in safe_moves:
        nx, ny = adjacent(head, m).values()
        space_by_move[m] = flood_fill((nx, ny), blocked, width, height)

    # -------------------------------------------------------------------------
    # 5. Food targeting with space awareness
    food_list = board["food"]
    seek_food_threshold = 50
    should_seek_food = you["health"] < seek_food_threshold and food_list

    if should_seek_food:
        best_score = None
        best_moves = []
        for m in safe_moves:
            nx, ny = adjacent(head, m).values()
            dist = min(manhattan({"x": nx, "y": ny}, food) for food in food_list)
            score = (dist, -space_by_move[m])  # prefer shorter distance, then larger space
            if best_score is None or score < best_score:
                best_score = score
                best_moves = [m]
            elif score == best_score:
                best_moves.append(m)
        chosen = random.choice(best_moves)
        print(f"MOVE {game_state['turn']}: {chosen} (seek food, health {you['health']}, space {space_by_move[chosen]})")
        return {"move": chosen}

    # -------------------------------------------------------------------------
    # 6. Otherwise choose move with largest space
    max_space = max(space_by_move.values())
    candidates = [m for m, s in space_by_move.items() if s == max_space]
    chosen = random.choice(candidates)
    print(f"MOVE {game_state['turn']}: {chosen} (max space {max_space})")
    return {"move": chosen}

# -----------------------------------------------------------------------------
# Stand-alone server run (used by BattleSnake engine)
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})