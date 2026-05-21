# Improved Battlesnake bot - round 10 enhancements
# - Adds stricter head-to-head avoidance for opponents of >= our length (blocks their head squares too)
# - Penalizes moves that bring us close to large opponents to avoid risky head-on collisions
# - Slightly more aggressive food-seeking when health is lower
# - Keeps reachable-space flood-fill and tail-vacancy heuristics
import random
import typing
from collections import deque

def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "",  # TODO: Your Battlesnake Username
        "color": "#888888",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

def _get_new_head_coords(head: typing.Dict, move: str) -> typing.Dict:
    if move == "up":
        return {"x": head["x"], "y": head["y"] + 1}
    if move == "down":
        return {"x": head["x"], "y": head["y"] - 1}
    if move == "left":
        return {"x": head["x"] - 1, "y": head["y"]}
    if move == "right":
        return {"x": head["x"] + 1, "y": head["y"]}
    return head

def _manhattan(a: typing.Dict, b: typing.Dict) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def _adjacent_coords(coord: typing.Dict) -> typing.Set[typing.Tuple[int,int]]:
    x = coord["x"]; y = coord["y"]
    return {(x, y+1), (x, y-1), (x-1, y), (x+1, y)}

def _flood_fill_count(start: typing.Tuple[int,int], occupied: typing.Set[typing.Tuple[int,int]], width: int, height: int) -> int:
    # BFS to count reachable squares from start, not entering occupied.
    sx, sy = start
    if (sx, sy) in occupied:
        return 0
    q = deque()
    q.append((sx, sy))
    seen = {(sx, sy)}
    count = 0
    while q:
        x, y = q.popleft()
        count += 1
        for nx, ny in ((x, y+1), (x, y-1), (x-1, y), (x+1, y)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if (nx, ny) in occupied:
                continue
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return count

def move(game_state: typing.Dict) -> typing.Dict:
    # Possible moves
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    my_head = game_state["you"]["body"][0]
    my_body = game_state["you"]["body"]
    my_neck = my_body[1] if len(my_body) > 1 else None
    my_length = len(my_body)
    my_tail = my_body[-1]

    # Don't move backwards into neck
    if my_neck:
        if my_neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    board = game_state["board"]
    width = board.get("width", 0)
    height = board.get("height", 0)
    food = board.get("food", [])
    food_set = {(f["x"], f["y"]) for f in food}

    # Avoid walls (out of bounds)
    for m in list(is_move_safe.keys()):
        if not is_move_safe[m]:
            continue
        new_head = _get_new_head_coords(my_head, m)
        if new_head["x"] < 0 or new_head["x"] >= width or new_head["y"] < 0 or new_head["y"] >= height:
            is_move_safe[m] = False

    # Build a set of occupied coordinates by all snakes
    occupied = set()
    my_id = game_state["you"].get("id")
    for snake in board.get("snakes", []):
        for part in snake.get("body", []):
            occupied.add((part["x"], part["y"]))
    # Allow tail-vacancy heuristic for opponents: if a tail is not on food, it may vacate next turn.
    for snake in board.get("snakes", []):
        tail = snake.get("body", [])[-1] if snake.get("body", []) else None
        if tail:
            tail_coord = (tail["x"], tail["y"])
            if tail_coord not in food_set:
                occupied.discard(tail_coord)

    # Build set of squares that are adjacent to opponent heads where opponent is >= our length
    # Enhance: also include the opponent head square itself to avoid head-to-head collisions.
    dangerous_head_adjacent = set()
    for snake in board.get("snakes", []):
        if snake.get("id") == my_id:
            continue
        opp_body = snake.get("body", [])
        opp_head = opp_body[0] if opp_body else None
        opp_len = len(opp_body)
        if opp_head and opp_len >= my_length:
            dangerous_head_adjacent |= _adjacent_coords(opp_head)
            dangerous_head_adjacent.add((opp_head["x"], opp_head["y"]))  # block the head square too

    # Avoid collisions with occupied squares and avoid dangerous head-adjacent squares
    for m in list(is_move_safe.keys()):
        if not is_move_safe[m]:
            continue
        new_head = _get_new_head_coords(my_head, m)
        coord = (new_head["x"], new_head["y"])
        if coord in occupied:
            # Moving into our own tail may be allowed if the tail will vacate (we are not eating)
            if coord == (my_tail["x"], my_tail["y"]) and coord not in food_set:
                pass
            else:
                is_move_safe[m] = False
                continue
        if coord in dangerous_head_adjacent:
            is_move_safe[m] = False

    # Collect safe moves
    safe_moves = [m for m, ok in is_move_safe.items() if ok]

    # Compute list of opponent heads to prefer moves away from opponents
    opponent_heads = []
    large_opponents = []  # opponents with length >= our length
    for snake in board.get("snakes", []):
        if snake.get("id") == my_id:
            continue
        opp_body = snake.get("body", [])
        opp_h = opp_body[0] if opp_body else None
        if opp_h:
            opponent_heads.append(opp_h)
            if len(opp_body) >= my_length:
                large_opponents.append(opp_h)

    def _min_opp_dist(coord):
        if not opponent_heads:
            return 0
        return min(_manhattan(coord, h) for h in opponent_heads)

    def _min_large_opp_dist(coord):
        if not large_opponents:
            return 9999
        return min(_manhattan(coord, h) for h in large_opponents)

    if not safe_moves:
        # No safe moves detected (should be rare); pick something (prefer up/down)
        fallback = random.choice(["up", "down", "left", "right"])
        print(f"MOVE {game_state.get('turn')}: No safe moves detected! Forcing {fallback}")
        return {"move": fallback}

    # Evaluate reachable space for each safe move to avoid self-trapping
    move_reachable = {}
    for m in safe_moves:
        candidate_head = _get_new_head_coords(my_head, m)
        start = (candidate_head["x"], candidate_head["y"])
        # Simulate tail vacancy: if this move does NOT eat food, our tail will vacate next turn.
        occ = set(occupied)
        # Avoid squares adjacent to large opponent heads when simulating reachable area
        occ |= dangerous_head_adjacent
        # Also conservatively block squares opponents could move into next turn.
        # For each opponent head (with length >= our length) add their adjacent squares and head into simulated occupied set.
        for snake in board.get("snakes", []):
            if snake.get("id") == my_id:
                continue
            opp_body = snake.get("body", [])
            opp_head = opp_body[0] if opp_body else None
            opp_len = len(opp_body)
            if not opp_head:
                continue
            if opp_len >= my_length:
                for ax, ay in _adjacent_coords(opp_head):
                    if 0 <= ax < width and 0 <= ay < height:
                        occ.add((ax, ay))
                occ.add((opp_head["x"], opp_head["y"]))
        tail_coord = (my_tail["x"], my_tail["y"])
        # If the candidate move does not land on food, the tail will move forward (vacate).
        if start not in food_set:
            occ.discard(tail_coord)
        # Now compute reachable area from the candidate head given the simulated occupancy
        reachable = _flood_fill_count(start, occ, width, height)
        move_reachable[m] = reachable

    # Filter out moves that lead to too-small reachable area (less than our length)
    filtered_moves = [m for m in safe_moves if move_reachable.get(m, 0) >= my_length]
    if filtered_moves:
        safe_moves = filtered_moves
    else:
        # If all moves are "small", keep original safe_moves but prefer larger spaces
        pass

    # If there's food, try to move towards the nearest food (by Manhattan distance),
    # but also prefer moves that lead to larger reachable areas.
    food = board.get("food", [])
    if food:
        my_health = game_state["you"].get("health", 100)
        # Current distance to nearest food
        current_dist = min(_manhattan(my_head, f) for f in food)
        # If health is low, prefer moves that reduce distance to food (tie-break by reachable area)
        # Make the threshold a bit more aggressive
        if my_health < 40:
            reducing = []
            for m in safe_moves:
                candidate_head = _get_new_head_coords(my_head, m)
                dist = min(_manhattan(candidate_head, f) for f in food)
                if dist < current_dist:
                    reducing.append((m, dist, move_reachable.get(m, 0)))
            if reducing:
                # choose the reducing move with largest reachable area, then smallest distance
                reducing.sort(key=lambda x: (-x[2], x[1]))
                next_move = reducing[0][0]
                print(f"MOVE {game_state.get('turn')}: Low health; choosing {next_move} to approach food (reachable={move_reachable.get(next_move)})")
                return {"move": next_move}

        # Default scoring: balance reachable space and closeness to food
        best_move = None
        best_score = None
        for m in safe_moves:
            candidate_head = _get_new_head_coords(my_head, m)
            dist = min(_manhattan(candidate_head, f) for f in food)
            reachable = move_reachable.get(m, 0)
            # Score: prioritize reachable space heavily, then closeness to food (lower is better)
            wall_dist = min(candidate_head["x"], candidate_head["y"], width-1-candidate_head["x"], height-1-candidate_head["y"])
            # Penalize being very close to a large opponent (to avoid risky head-on collisions)
            large_opp_dist = _min_large_opp_dist(candidate_head)
            large_opp_penalty = 0
            if large_opp_dist <= 1:
                # If a large opponent can reach this tile next move (or is on it), heavily penalize
                large_opp_penalty = 10000
            elif large_opp_dist == 2:
                large_opp_penalty = 2000
            score = (reachable * 1000) - dist + (_min_opp_dist(candidate_head) * 50) + (wall_dist * 20) - large_opp_penalty
            # Add a small random jitter to break ties
            score += random.random()
            if best_score is None or score > best_score:
                best_score = score
                best_move = m
        next_move = best_move if best_move is not None else random.choice(safe_moves)
        print(f"MOVE {game_state.get('turn')}: Chose {next_move} towards food (score={best_score}, reachable={move_reachable.get(next_move)})")
        return {"move": next_move}

    # No food â pick the safe move with largest reachable area
    best_move = max(safe_moves, key=lambda m: (move_reachable.get(m, 0), _min_opp_dist(_get_new_head_coords(my_head, m)), min(_get_new_head_coords(my_head, m)["x"], _get_new_head_coords(my_head, m)["y"], width-1-_get_new_head_coords(my_head, m)["x"], height-1-_get_new_head_coords(my_head, m)["y"]), random.random()))
    print(f"MOVE {game_state.get('turn')}: No food; choose move {best_move} (reachable={move_reachable.get(best_move)})")
    return {"move": best_move}

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})