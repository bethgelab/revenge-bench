# Welcome to
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  | |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#
# Battlesnake logic and helper functions.

import math
import random
import typing
from collections import deque


def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "gpt-5",
        "color": "#22cc88",
        "head": "beluga",
        "tail": "pixel",
    }


def start(game_state: typing.Dict):
    print("GAME START")


def end(game_state: typing.Dict):
    print("GAME OVER\n")


def _neighbors(p):
    x, y = p
    return {
        "up": (x, y + 1),
        "down": (x, y - 1),
        "left": (x - 1, y),
        "right": (x + 1, y),
    }


def _in_bounds(p, w, h):
    x, y = p
    return 0 <= x < w and 0 <= y < h


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _flood_fill_space(start, blocked, w, h, limit=None):
    # Simple BFS counting reachable tiles avoiding blocked cells
    if limit is None:
        limit = w * h
    if start in blocked or not _in_bounds(start, w, h):
        return 0
    q = deque([start])
    seen = {start}
    count = 0
    while q and count < limit:
        cur = q.popleft()
        count += 1
        for nxt in _neighbors(cur).values():
            if nxt in seen:
                continue
            if not _in_bounds(nxt, w, h):
                continue
            if nxt in blocked:
                continue
            seen.add(nxt)
            q.append(nxt)
    return count


def _dist_to_center(pt, w, h):
    # Manhattan distance to the nearest center cell (supports even/odd sizes)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    candidates = [
        (math.floor(cx), math.floor(cy)),
        (math.floor(cx), math.ceil(cy)),
        (math.ceil(cx), math.floor(cy)),
        (math.ceil(cx), math.ceil(cy)),
    ]
    return min(_manhattan(pt, c) for c in candidates)


def _escape_count_for_move(target, will_eat, occupied, hazards, w, h, my_head, my_tail):
    # Estimate how many safe moves we will have on the FOLLOWING turn if we move to `target` now.
    blocked = set(occupied) | set(hazards)
    if not will_eat:
        # Tail vacates if we did not eat
        blocked.discard(my_tail)
    # Our new head occupies target next turn
    blocked.add(target)
    new_neck = my_head  # we can't move back into our current head next turn

    count = 0
    for nxt in _neighbors(target).values():
        if nxt == new_neck:
            continue
        if not _in_bounds(nxt, w, h):
            continue
        if nxt in blocked:
            continue
        count += 1
    return count


def _shortest_path_to_any(start, goals, blocked, w, h, forbid_back=None):
    # Tail-aware, static BFS shortest path from start to any goal in `goals`.
    # - blocked: set of blocked tiles
    # - forbid_back: a tile we cannot move into on the first step (our neck)
    if start in goals:
        return [start]
    q = deque([start])
    parents = {start: None}
    while q:
        cur = q.popleft()
        if cur in goals:
            # reconstruct path
            path = []
            c = cur
            while c is not None:
                path.append(c)
                c = parents[c]
            path.reverse()
            return path
        for nxt in _neighbors(cur).values():
            if cur == start and forbid_back is not None and nxt == forbid_back:
                continue
            if not _in_bounds(nxt, w, h):
                continue
            if nxt in blocked:
                continue
            if nxt in parents:
                continue
            parents[nxt] = cur
            q.append(nxt)
    return None


def _shortest_path_to_any_with_hazards(start, goals, occupied, hazards, w, h, forbid_back=None, max_hazard_steps=0):
    """
    BFS that allows stepping through a limited number of hazard tiles.
    Tracks hazard-step budget (<= max_hazard_steps). Returns path if found.
    """
    if start in goals:
        return [start]
    # state: (pos, hazard_used)
    parents = {}  # key: (pos, used) -> (prev_pos, prev_used)
    best_used = {start: 0}
    q = deque()
    q.append((start, 0))
    parents[(start, 0)] = (None, 0)

    blocked_solid = set(occupied)  # hazards not solid; they consume budget
    while q:
        cur, used = q.popleft()
        if cur in goals:
            # reconstruct path using the state key that reached goal
            path = []
            key = (cur, used)
            while key[0] is not None:
                path.append(key[0])
                key = parents[key]
            path.reverse()
            return path
        for nxt in _neighbors(cur).values():
            if cur == start and forbid_back is not None and nxt == forbid_back:
                continue
            if not _in_bounds(nxt, w, h):
                continue
            if nxt in blocked_solid:
                continue
            nxt_used = used + (1 if nxt in hazards else 0)
            if nxt_used > max_hazard_steps:
                continue
            # We keep the best (lowest) hazard_used we've seen for each cell
            if nxt not in best_used or nxt_used < best_used[nxt]:
                best_used[nxt] = nxt_used
                q.append((nxt, nxt_used))
                parents[(nxt, nxt_used)] = (cur, used)
    return None


def _voronoi_control_score(our_pos, will_eat, occupied, hazards, w, h, my_tail, enemy_heads):
    """
    Multi-source BFS to estimate territory control.
    Returns our controlled cell count minus max enemy controlled cell count.
    - Blocks bodies and hazards (tail-aware for our tail if not eating).
    - Seeds: our_pos (owner=0) and each enemy head (owner=1..n).
    - Contested cells (equal distance) are not counted for anyone.
    """
    blocked = set(occupied) | set(hazards)
    if not will_eat:
        blocked.discard(my_tail)

    # State: (pos, dist, owner)
    q = deque()
    seen = {}  # pos -> (dist, owner_id or -1 for contested)

    # Our seed
    q.append((our_pos, 0, 0))
    seen[our_pos] = (0, 0)

    # Enemy seeds
    owner_id = 1
    for eh in enemy_heads:
        q.append((eh, 0, owner_id))
        seen[eh] = (0, owner_id)
        owner_id += 1

    while q:
        pos, d, owner = q.popleft()
        for nxt in _neighbors(pos).values():
            if not _in_bounds(nxt, w, h):
                continue
            if nxt in blocked:
                continue
            if nxt not in seen:
                seen[nxt] = (d + 1, owner)
                q.append((nxt, d + 1, owner))
            else:
                prev_d, prev_owner = seen[nxt]
                if prev_d == d + 1 and prev_owner != owner and prev_owner != -1:
                    # Mark contested; we don't need to enqueue contested state
                    seen[nxt] = (prev_d, -1)

    # Count territories
    counts = {}
    for _, (_, owner) in seen.items():
        if owner >= 0:
            counts[owner] = counts.get(owner, 0) + 1

    ours = counts.get(0, 0)
    max_enemy = 0
    for oid, cnt in counts.items():
        if oid == 0:
            continue
        if cnt > max_enemy:
            max_enemy = cnt
    return ours - max_enemy


def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    you = game_state["you"]

    width = board["width"]
    height = board["height"]
    my_id = you["id"]
    my_body = you["body"]
    my_length = len(my_body)
    my_head = (my_body[0]["x"], my_body[0]["y"])
    my_tail = (my_body[-1]["x"], my_body[-1]["y"])
    my_health = you.get("health", 100)

    # Foods (as tuple coords)
    foods = [(f["x"], f["y"]) for f in board.get("food", [])]

    # Occupied cells (all snake bodies)
    occupied = set()
    enemy_heads_list = []
    enemy_lengths = []
    for s in board["snakes"]:
        for p in s["body"]:
            occupied.add((p["x"], p["y"]))
        if s["id"] != my_id and s["body"]:
            head = (s["body"][0]["x"], s["body"][0]["y"])
            enemy_heads_list.append(head)
            enemy_lengths.append(len(s["body"]))

    # Hazards (Royale, etc.) - avoid by default
    hazards = set()
    for p in board.get("hazards", []):
        hazards.add((p["x"], p["y"]))

    # Determine backward (neck) move to avoid turning into our neck
    backward_move = None
    neck = None
    if len(my_body) > 1:
        neck = (my_body[1]["x"], my_body[1]["y"])
        for mv, pt in _neighbors(my_head).items():
            if pt == neck:
                backward_move = mv
                break

    # Potential enemy head positions (for head-to-head avoidance)
    enemy_head_moves = []  # list of tuples (set_of_positions, enemy_length)
    for s in board["snakes"]:
        if s["id"] == my_id:
            continue
        body = s["body"]
        head = (body[0]["x"], body[0]["y"])
        s_len = len(body)
        s_neck = (body[1]["x"], body[1]["y"]) if len(body) > 1 else None
        poss = set()
        for mv, pt in _neighbors(head).items():
            if s_neck is not None and pt == s_neck:
                continue  # they won't move backwards
            if not _in_bounds(pt, width, height):
                continue
            # conservative: assume they avoid currently occupied cells
            if pt in occupied:
                continue
            poss.add(pt)
        if poss:
            enemy_head_moves.append((poss, s_len))

    # Evaluate safety for each move
    # We will store candidates as tuples: (mv, target, will_eat)
    candidates = []
    for mv, target in _neighbors(my_head).items():
        if mv == backward_move:
            continue
        # In bounds
        if not _in_bounds(target, width, height):
            continue

        # Determine if this move would eat (affects tail movement)
        will_eat = target in foods

        # Avoid bodies, but allow stepping into our own tail if it will vacate
        if target in occupied:
            if not (target == my_tail and not will_eat):
                continue

        # Avoid hazards by default
        if target in hazards:
            continue

        # Head-to-head risk: if any enemy of equal/greater length can also move here
        h2h_danger = False
        for poss, s_len in enemy_head_moves:
            if target in poss and s_len >= my_length:
                h2h_danger = True
                break
        if h2h_danger:
            continue

        candidates.append((mv, target, will_eat))

    # If no candidates, relax hazards (allow moving into hazards if necessary)
    if not candidates:
        for mv, target in _neighbors(my_head).items():
            if mv == backward_move:
                continue
            if not _in_bounds(target, width, height):
                continue
            will_eat = target in foods
            if target in occupied:
                if not (target == my_tail and not will_eat):
                    continue
            # allow hazards now
            h2h_danger = False
            for poss, s_len in enemy_head_moves:
                if target in poss and s_len >= my_length:
                    h2h_danger = True
                    break
            if h2h_danger:
                continue
            candidates.append((mv, target, will_eat))

    # If still no candidates, do anything legal in-bounds not backwards
    if not candidates:
        fallback = []
        for mv, target in _neighbors(my_head).items():
            if mv == backward_move:
                continue
            if _in_bounds(target, width, height):
                fallback.append((mv, target))
        if not fallback:
            print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
            return {"move": "down"}
        mv, _ = random.choice(fallback)
        print(f"MOVE {game_state['turn']}: Fallback {mv}")
        return {"move": mv}

    # Add escape counts and center distances for candidates
    cand_enh = []
    for mv, target, will_eat in candidates:
        esc = _escape_count_for_move(
            target, will_eat, occupied, hazards, width, height, my_head, my_tail
        )
        center_d = _dist_to_center(target, width, height)
        cand_enh.append((mv, target, will_eat, esc, center_d))

    # Prefer moves that don't dead-end: require esc>=2 if available, else esc>=1 if available
    cand_ge2 = [c for c in cand_enh if c[3] >= 2]
    if cand_ge2:
        cand_enh = cand_ge2
    else:
        cand_ge1 = [c for c in cand_enh if c[3] >= 1]
        if cand_ge1:
            cand_enh = cand_ge1
        # else keep all (including esc==0) if nothing else exists

    # Strategy: seek food if we're not healthy; otherwise maximize space
    go_for_food = len(foods) > 0 and (my_health < 50 or my_length < 10)

    # Precompute nearest food distance from a point
    def nearest_food_dist(pt):
        if not foods:
            return None
        return min(_manhattan(pt, f) for f in foods)

    # Base blocked set for space evaluation (avoid bodies and hazards)
    blocked_base = set(occupied) | set(hazards)

    # If going for food, try BFS shortest path to any food first
    if go_for_food and foods:
        blocked_path = set(blocked_base)
        # Tail-aware: if we don't eat this turn, tail vacates; allow path planning through current tail
        blocked_path.discard(my_tail)
        path = _shortest_path_to_any(my_head, set(foods), blocked_path, width, height, forbid_back=neck)
        if not path or len(path) < 2:
            # Try hazard-aware BFS if we have health to spare and hazards exist
            if hazards:
                # Assume default Royale hazard damage per turn ~14; keep buffer of 30 HP
                HAZARD_DAMAGE_PER_TURN = 14
                spare = max(0, my_health - 30)
                max_hazard_steps = spare // HAZARD_DAMAGE_PER_TURN
                if max_hazard_steps > 0:
                    path = _shortest_path_to_any_with_hazards(
                        my_head, set(foods), occupied, hazards, width, height, forbid_back=neck, max_hazard_steps=max_hazard_steps
                    )
        if path and len(path) >= 2:
            first_step = path[1]
            for mv, target, will_eat, esc, center_d in cand_enh:
                if target == first_step:
                    print(f"MOVE {game_state['turn']}: Food mode (BFS) -> {mv}")
                    return {"move": mv}

    # Precompute some opponent metrics for scoring
    max_enemy_len = max(enemy_lengths) if enemy_lengths else 0

    # Scoring helpers: Voronoi control and enemy proximity preference
    def enemy_distance_pref(pt):
        if not enemy_heads_list:
            return 0
        dmin = min(_manhattan(pt, eh) for eh in enemy_heads_list)
        # If we are shorter or equal to the longest enemy, prefer being farther; if longer, prefer being closer
        return dmin if my_length <= max_enemy_len else -dmin

    # If going for food but BFS wasn't used, choose based on food distance, Voronoi, space, escape, enemy proximity, center bias
    if go_for_food and foods:
        # Pick moves that minimize distance to nearest food; tie-break with voronoi control, space (tail-aware),
        # then escapes, then enemy proximity, then center bias
        best_dist = None
        for _, target, _, _, _ in cand_enh:
            d = nearest_food_dist(target)
            if d is None:
                continue
            if best_dist is None or d < best_dist:
                best_dist = d

        scored = []
        for mv, target, will_eat, esc, center_d in cand_enh:
            d = nearest_food_dist(target)
            if d is None or d != best_dist:
                continue
            # Tail-aware space: if not eating, tail vacates
            blocked = set(blocked_base)
            if not will_eat:
                blocked.discard(my_tail)
            space = _flood_fill_space(target, blocked, width, height, limit=width * height)
            # Voronoi control score
            vor = _voronoi_control_score(target, will_eat, occupied, hazards, width, height, my_tail, enemy_heads_list)
            edp = enemy_distance_pref(target)
            scored.append((vor, space, esc, edp, -center_d, mv))

        if scored:
            scored.sort(reverse=True)  # sort by tuple desc
            next_move = scored[0][5]
            print(f"MOVE {game_state['turn']}: Food mode -> {next_move}")
            return {"move": next_move}

    # Otherwise maximize space (tail-aware), with Voronoi control first, tie-break by space, escapes, enemy proximity, center bias
    best = []
    for mv, target, will_eat, esc, center_d in cand_enh:
        blocked = set(blocked_base)
        if not will_eat:
            blocked.discard(my_tail)
        space = _flood_fill_space(target, blocked, width, height, limit=width * height)
        vor = _voronoi_control_score(target, will_eat, occupied, hazards, width, height, my_tail, enemy_heads_list)
        edp = enemy_distance_pref(target)
        best.append((vor, space, esc, edp, -center_d, mv))

    if best:
        best.sort(reverse=True)
        next_move = best[0][5]
        print(f"MOVE {game_state['turn']}: Space mode -> {next_move}")
        return {"move": next_move}

    # Should not reach here; but in case, pick any candidate move
    mv = random.choice([mv for mv, _, _, _, _ in cand_enh])
    print(f"MOVE {game_state['turn']}: Default pick -> {mv}")
    return {"move": mv}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})