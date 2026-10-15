# Improved Battlesnake bot for round 5
# - Prevents moving backwards
# - Prevents moving out of bounds
# - Avoids collisions with our body and other snakes
# - Avoids head-to-head risky squares against equal-or-longer snakes
# - Uses flood-fill to prefer moves that lead to larger reachable area (avoid traps)
# - Moves toward the nearest food when health is low (raised threshold), otherwise prefers larger open space
# - Prefers following its tail when other heuristics tie (safe escape)
# - Deterministic tiebreaking to reduce randomness across runs

import typing
from collections import deque

def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "",  # Your Battlesnake Username
        "color": "#888888",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

def manhattan(a: typing.Dict, b: typing.Dict) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def _in_bounds(pos, width, height):
    return 0 <= pos["x"] < width and 0 <= pos["y"] < height

def _adjacent_positions(pos):
    return [
        {"x": pos["x"], "y": pos["y"] + 1},
        {"x": pos["x"], "y": pos["y"] - 1},
        {"x": pos["x"] - 1, "y": pos["y"]},
        {"x": pos["x"] + 1, "y": pos["y"]},
    ]

def _reachable_area(start_pos, occupied_set, width, height, limit=None):
    # BFS flood fill to count reachable squares from start_pos given occupied cells
    q = deque()
    seen = set()
    q.append((start_pos["x"], start_pos["y"]))
    seen.add((start_pos["x"], start_pos["y"]))
    count = 0
    while q:
        x, y = q.popleft()
        count += 1
        if limit and count >= limit:
            return count
        for nx, ny in ((x, y+1), (x, y-1), (x-1, y), (x+1, y)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in occupied_set:
                continue
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return count

def move(game_state: typing.Dict) -> typing.Dict:
    # All moves start as potentially safe
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    you = game_state["you"]
    board = game_state["board"]

    my_head = you["body"][0]
    my_length = len(you.get("body", []))
    # Protect against very short snakes (shouldn't happen in official games)
    my_neck = you["body"][1] if len(you["body"]) > 1 else None

    # Don't allow moving backwards into neck
    if my_neck is not None:
        if my_neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    # Board boundaries
    width = board["width"]
    height = board["height"]

    # Possible moves mapped to resulting coordinates
    moves_delta = {
        "up": {"x": my_head["x"], "y": my_head["y"] + 1},
        "down": {"x": my_head["x"], "y": my_head["y"] - 1},
        "left": {"x": my_head["x"] - 1, "y": my_head["y"]},
        "right": {"x": my_head["x"] + 1, "y": my_head["y"]},
    }

    # Mark moves that go out of bounds as unsafe
    for mv, pos in moves_delta.items():
        if not _in_bounds(pos, width, height):
            is_move_safe[mv] = False

    # Build a set of occupied coordinates by snakes' bodies
    # We exclude the tail of each snake to allow moving into a cell that will be vacated
    occupied = set()
    enemy_heads = []  # list of dicts with 'pos' and 'length'
    for snake in board.get("snakes", []):
        body = snake.get("body", [])
        # All but the last segment (tail) are considered occupied for this turn.
        for segment in body[:-1]:
            occupied.add((segment["x"], segment["y"]))
        # Collect head info for head-to-head logic
        if body:
            enemy_heads.append({"pos": body[0], "length": len(body), "id": snake.get("id")})

    # Also mark hazards and other permanent blocks if any (some games may provide)
    for hazard in board.get("hazards", []):
        occupied.add((hazard["x"], hazard["y"]))

    # Head-to-head avoidance:
    # If a move places us into a square that is adjacent to an enemy head and that enemy is
    # equal-or-longer length, it's risky (they could move into that square). Mark such moves unsafe.
    for mv, new_pos in moves_delta.items():
        if not is_move_safe[mv]:
            continue
        for eh in enemy_heads:
            eh_pos = eh["pos"]
            # If new_pos is equal to enemy head, it's only safe if enemy is shorter (they could move off)
            if new_pos["x"] == eh_pos["x"] and new_pos["y"] == eh_pos["y"]:
                if eh["length"] >= my_length:
                    is_move_safe[mv] = False
                    break
                else:
                    # allowed if enemy shorter (we win tie)
                    continue
            # If new_pos is adjacent to enemy head, they may move into it next turn.
            if manhattan(new_pos, eh_pos) == 1 and eh["length"] >= my_length:
                is_move_safe[mv] = False
                break

    # Also avoid moving into currently occupied cells
    for mv, new_pos in moves_delta.items():
        if not is_move_safe[mv]:
            continue
        if (new_pos["x"], new_pos["y"]) in occupied:
            is_move_safe[mv] = False

    # Collect safe moves
    safe_moves = [mv for mv, ok in is_move_safe.items() if ok]
    if not safe_moves:
        # If no safe moves, pick any legal (not out of bounds) move (we're probably trapped)
        fallback = [mv for mv, pos in moves_delta.items() if _in_bounds(pos, width, height)]
        next_move = fallback[0] if fallback else "up"
        print(f"MOVE {game_state.get('turn', '?')}: No safe moves, fallback to {next_move}")
        return {"move": next_move}

    # Compute reachable area for each safe move
    area_by_move = {}
    # Build occupied set tupled for flood fill (we already excluded tails)
    occ_for_area = set(occupied)
    # include our head (since we move from it) but exclude our tail to allow following it
    for seg in you.get("body", [])[:-1]:
        occ_for_area.add((seg["x"], seg["y"]))
    # tail cell can be considered free for floodfill because it may vacate
    # Evaluate area
    for mv in safe_moves:
        new_head = moves_delta[mv]
        area = _reachable_area(new_head, occ_for_area, width, height, limit=width*height)
        area_by_move[mv] = area

    # Helper: min distance from a position to any enemy head (current heads)
    def min_dist_to_enemy_head(pos):
        if not enemy_heads:
            return float('inf')
        return min(manhattan(pos, eh["pos"]) for eh in enemy_heads)

    # Helper: distance to board center (prefer central positions)
    center = {"x": (width - 1) / 2.0, "y": (height - 1) / 2.0}
    def dist_to_center(pos):
        return abs(pos["x"] - center["x"]) + abs(pos["y"] - center["y"])

    # Prefer food earlier than before
    food = board.get("food", [])
    LOW_HEALTH_THRESHOLD = 50  # increased threshold for earlier food seeking

    # Deterministic tiebreak order (consistent across runs)
    DIR_PRIORITY = ["up", "right", "down", "left"]

    # If low health and food exists, bias toward nearest food
    if food and you.get("health", 100) <= LOW_HEALTH_THRESHOLD:
        nearest_food = min(food, key=lambda f: manhattan(my_head, f))
        scores = {}
        for mv in safe_moves:
            new_head = moves_delta[mv]
            dist_food = manhattan(new_head, nearest_food)
            area = area_by_move.get(mv, 0)
            head_dist = min_dist_to_enemy_head(new_head)
            center_dist = dist_to_center(new_head)
            # Higher is better. We want to minimize dist_food, maximize area and head_dist,
            # and prefer being closer to center as a small bonus.
            score = (-dist_food * 1000) + (area * 10) + (head_dist * 5) - (center_dist * 1)
            scores[mv] = score
        best_score = max(scores.values())
        best_moves = [mv for mv, sc in scores.items() if sc == best_score]
        # deterministic tiebreak
        best_moves_sorted = sorted(best_moves, key=lambda m: DIR_PRIORITY.index(m))
        next_move = best_moves_sorted[0]
    else:
        # Prefer move with largest reachable area
        max_area = max(area_by_move.values())
        candidates = [mv for mv, area in area_by_move.items() if area == max_area]
        if len(candidates) > 1:
            # compute a composite score for candidates
            scores = {}
            for mv in candidates:
                new_head = moves_delta[mv]
                area = area_by_move.get(mv, 0)
                head_dist = min_dist_to_enemy_head(new_head)
                center_dist = dist_to_center(new_head)
                # area primary, then distance from enemy (want larger), then center closeness
                score = (area * 1000) + (head_dist * 10) - (center_dist * 1)
                scores[mv] = score
            best_score = max(scores.values())
            best_moves = [mv for mv, sc in scores.items() if sc == best_score]

            if len(best_moves) > 1 and food:
                # tiebreak by closer to nearest food
                nearest_food = min(food, key=lambda f: manhattan(my_head, f))
                best_moves2 = []
                best_score2 = None
                for mv in best_moves:
                    new_head = moves_delta[mv]
                    dist = manhattan(new_head, nearest_food)
                    if best_score2 is None or dist < best_score2:
                        best_score2 = dist
                        best_moves2 = [mv]
                    elif dist == best_score2:
                        best_moves2.append(mv)
                best_moves = best_moves2

            if len(best_moves) > 1:
                # As a final fallback prefer moves that move closer to our tail (escape)
                my_tail = you.get("body", [])[-1] if you.get("body") else None
                if my_tail:
                    tail_dists = {mv: manhattan(moves_delta[mv], my_tail) for mv in best_moves}
                    # prefer smaller distance to tail
                    best_tail_dist = min(tail_dists.values())
                    best_moves = [mv for mv, d in tail_dists.items() if d == best_tail_dist]

            # deterministic final tiebreak
            best_moves_sorted = sorted(best_moves, key=lambda m: DIR_PRIORITY.index(m))
            next_move = best_moves_sorted[0]
        else:
            next_move = candidates[0]

    print(f"MOVE {game_state.get('turn', '?')}: {next_move} (safe: {safe_moves}, area: {area_by_move})")
    return {"move": next_move}

if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})