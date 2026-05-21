# Improved Battlesnake AI with flood-fill space evaluation and A* pathfinding for urgent food seeking
import random
import typing
from collections import deque
import heapq

def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "gpt-5-mini",
        "color": "#888888",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

def _get_new_head(head: typing.Dict, move: str) -> typing.Dict:
    if move == "up":
        return {"x": head["x"], "y": head["y"] + 1}
    if move == "down":
        return {"x": head["x"], "y": head["y"] - 1}
    if move == "left":
        return {"x": head["x"] - 1, "y": head["y"]}
    if move == "right":
        return {"x": head["x"] + 1, "y": head["y"]}
    raise ValueError("Invalid move")

def _manhattan(a: typing.Dict, b: typing.Dict) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def _flood_fill_count(start: typing.Tuple[int, int], obstacles: typing.Set[typing.Tuple[int, int]],
                      width: int, height: int) -> int:
    """Return number of reachable squares from start, given obstacles (tuples)."""
    q = deque()
    visited = set()
    if start in obstacles:
        return 0
    q.append(start)
    visited.add(start)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in obstacles and (nx, ny) not in visited:
                visited.add((nx, ny))
                q.append((nx, ny))
    return len(visited)

def _astar_shortest_path(start: typing.Tuple[int, int],
                         goals: typing.List[typing.Tuple[int, int]],
                         obstacles: typing.Set[typing.Tuple[int, int]],
                         width: int, height: int) -> typing.Optional[int]:
    """
    A* search to nearest goal. Returns number of steps to the nearest goal or None if unreachable.
    Uses Manhattan heuristic (admissible on grid with 4-neighbors).
    """
    if not goals:
        return None
    if start in obstacles:
        return None
    goal_set = set(goals)

    def heuristic(p):
        x, y = p
        return min(abs(x - gx) + abs(y - gy) for gx, gy in goal_set)

    open_heap = []
    gscore = {start: 0}
    heapq.heappush(open_heap, (heuristic(start), 0, start))
    visited = set()

    while open_heap:
        _, g, current = heapq.heappop(open_heap)
        if current in goal_set:
            return g
        if current in visited:
            continue
        visited.add(current)
        cx, cy = current
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            npos = (nx, ny)
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if npos in obstacles:
                continue
            ng = g + 1
            if ng < gscore.get(npos, 1e9):
                gscore[npos] = ng
                heapq.heappush(open_heap, (ng + heuristic(npos), ng, npos))
    return None

def move(game_state: typing.Dict) -> typing.Dict:
    # Basic safety map
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    my_head = game_state["you"]["body"][0]
    my_body = game_state["you"]["body"]
    my_id = game_state["you"]["id"]
    my_length = game_state["you"].get("length", len(my_body))
    my_health = game_state["you"].get("health", 100)

    # Prevent moving backwards into the neck
    if len(my_body) > 1:
        my_neck = my_body[1]
        if my_neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    width = game_state["board"]["width"]
    height = game_state["board"]["height"]

    # Prevent moves that go out of bounds
    if my_head["x"] == 0:
        is_move_safe["left"] = False
    if my_head["x"] == width - 1:
        is_move_safe["right"] = False
    if my_head["y"] == 0:
        is_move_safe["down"] = False
    if my_head["y"] == height - 1:
        is_move_safe["up"] = False

    # Build occupied set of all snake segments and list of opponent heads with lengths
    occupied_all = set()
    opponents = []
    for snake in game_state["board"]["snakes"]:
        for seg in snake["body"]:
            occupied_all.add((seg["x"], seg["y"]))
        if snake["id"] != my_id:
            head_seg = snake["body"][0]
            opponents.append((head_seg["x"], head_seg["y"], snake.get("length", len(snake["body"]))))

    food = game_state["board"].get("food", [])
    my_tail = my_body[-1] if len(my_body) > 0 else None

    # Evaluate each move for immediate safety
    for m in list(is_move_safe.keys()):
        if not is_move_safe[m]:
            continue
        new_head = _get_new_head(my_head, m)
        nx, ny = new_head["x"], new_head["y"]

        # Check bounds again defensively
        if not (0 <= nx < width and 0 <= ny < height):
            is_move_safe[m] = False
            continue

        # Will this move eat food?
        will_eat = any(f["x"] == nx and f["y"] == ny for f in food)

        # Collision with any body (allow moving into our own tail if it will be vacated)
        if (nx, ny) in occupied_all:
            if my_tail and (nx, ny) == (my_tail["x"], my_tail["y"]) and not will_eat:
                # allowed: tail will move away
                pass
            else:
                is_move_safe[m] = False
                continue

        # Avoid head-on collisions: if an opponent head is at or adjacent and opponent is equal or longer, avoid
        dangerous = False
        for ox, oy, olen in opponents:
            dist = abs(ox - nx) + abs(oy - ny)
            if dist <= 1 and olen >= my_length:
                dangerous = True
                break
        if dangerous:
            is_move_safe[m] = False
            continue

    safe_moves = [m for m, ok in is_move_safe.items() if ok]

    if len(safe_moves) == 0:
        print(f"MOVE {game_state.get('turn')}: No safe moves detected! Choosing random move")
        return {"move": random.choice(list(is_move_safe.keys()))}

    # Build dangerous squares set: squares that are occupied or reachable next-turn by larger-or-equal opponents
    dangerous_squares = set()
    for ox, oy, olen in opponents:
        if olen >= my_length:
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                dangerous_squares.add((ox + dx, oy + dy))

    # If health is low, prioritize moves that have a safe path to food (A*), while still avoiding traps
    if food and my_health <= 50:
        candidate_moves = []
        food_coords = [(f["x"], f["y"]) for f in food]
        for m in safe_moves:
            new_head = _get_new_head(my_head, m)
            nx, ny = new_head["x"], new_head["y"]
            will_eat = any(f["x"] == nx and f["y"] == ny for f in food)

            obstacles = set(occupied_all)
            if my_tail and not will_eat:
                obstacles.discard((my_tail["x"], my_tail["y"]))
            # Add dangerous squares to discourage moving next to bigger opponents
            obstacles |= dangerous_squares
            obstacles.discard((nx, ny))

            # Try to find an actual safe path to a food using A*
            path_len = _astar_shortest_path((nx, ny), food_coords, obstacles, width, height)
            if path_len is None:
                # fallback distance = Manhattan
                dist_to_food = min(_manhattan({"x": nx, "y": ny}, f) for f in food)
            else:
                dist_to_food = path_len

            reachable = _flood_fill_count((nx, ny), obstacles, width, height)
            candidate_moves.append((m, dist_to_food, reachable, will_eat, path_len is not None))

        # Prefer moves with an actual path to food
        moves_with_path = [c for c in candidate_moves if c[4]]
        if moves_with_path:
            min_dist = min(c[1] for c in moves_with_path)
            best = [c for c in moves_with_path if c[1] == min_dist]
        else:
            # fallback to choosing by Manhattan distance then reach
            min_dist = min(c[1] for c in candidate_moves)
            best = [c for c in candidate_moves if c[1] == min_dist]

        eaters = [c for c in best if c[3]]
        if eaters:
            chosen = random.choice(eaters)
        else:
            max_reach = max(c[2] for c in best)
            best2 = [c for c in best if c[2] == max_reach]
            chosen = random.choice(best2)
        print(f"MOVE {game_state.get('turn')}: {chosen[0]} (health={my_health}, food_dist={chosen[1]}, reach={chosen[2]}, path_exists={chosen[4]})")
        return {"move": chosen[0]}

    # Otherwise, evaluate each safe move by flood-fill reachable area (excluding dangerous squares)
    move_scores = []
    for m in safe_moves:
        new_head = _get_new_head(my_head, m)
        nx, ny = new_head["x"], new_head["y"]
        will_eat = any(f["x"] == nx and f["y"] == ny for f in food)

        obstacles = set(occupied_all)
        if my_tail and not will_eat:
            obstacles.discard((my_tail["x"], my_tail["y"]))
        obstacles |= dangerous_squares
        obstacles.discard((nx, ny))

        reachable = _flood_fill_count((nx, ny), obstacles, width, height)

        if food:
            dist_to_food = min(_manhattan({"x": nx, "y": ny}, f) for f in food)
        else:
            dist_to_food = None

        move_scores.append((m, reachable, dist_to_food, will_eat))

    # Choose move with maximum reachable area; tie-breaker: prefer moves that eat, then closer to food, then random
    max_reach = max(ms[1] for ms in move_scores)
    best = [ms for ms in move_scores if ms[1] == max_reach]

    # Prefer eating moves among best
    eaters = [b for b in best if b[3]]
    if eaters:
        chosen = random.choice(eaters)
    else:
        if len(best) > 1 and food:
            min_dist = min(b[2] for b in best if b[2] is not None)
            best = [b for b in best if b[2] == min_dist]
        chosen = random.choice(best)

    print(f"MOVE {game_state.get('turn')}: {chosen[0]} (reach={chosen[1]}, food_dist={chosen[2]}, health={my_health})")
    return {"move": chosen[0]}

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})