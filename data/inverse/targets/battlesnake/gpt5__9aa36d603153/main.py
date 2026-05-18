# Battlesnake bot with safer movement, head-to-head avoidance, improved food targeting,
# two-step lookahead escape checks, hazard awareness, and BFS pathing to food.
# Round 3: backup candidates when no escape, hazard-aware lookahead, contested food downweighting,
#          adjacency-to-head penalty, dynamic area weight, small-cavity penalties, and mild tail-chase.
# Round 3b: stronger escape weighting, area drop penalty vs. current, adaptive tail-chase boost when healthy/no-food-path.
# Round 3c: hazard escape term (BFS to safe tiles) and immediate exit bonus to avoid lingering in hazards.

import random
import typing
from collections import deque


def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "gpt-5",
        "color": "#22aa99",
        "head": "beluga",
        "tail": "bolt",
    }


def start(game_state: typing.Dict):
    print("GAME START")


def end(game_state: typing.Dict):
    print("GAME OVER\n")


# Helpers
DIRS = {
    "up": (0, 1),
    "down": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}


def t(pt: typing.Dict) -> typing.Tuple[int, int]:
    return (pt["x"], pt["y"])


def in_bounds(p: typing.Tuple[int, int], w: int, h: int) -> bool:
    return 0 <= p[0] < w and 0 <= p[1] < h


def manhattan(a: typing.Tuple[int, int], b: typing.Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors(p: typing.Tuple[int, int]) -> typing.List[typing.Tuple[int, int]]:
    return [(p[0] + dx, p[1] + dy) for dx, dy in DIRS.values()]


def flood_fill_area(start: typing.Tuple[int, int], w: int, h: int, blocked: typing.Set[typing.Tuple[int, int]], cap: int = 250) -> int:
    # Count reachable cells from start, avoiding blocked cells.
    if not in_bounds(start, w, h) or start in blocked:
        return 0
    seen = set([start])
    q = deque([start])
    count = 0
    limit = min(cap, w * h)  # Simple cap for speed on large boards
    while q and count < limit:
        cur = q.popleft()
        count += 1
        for n in neighbors(cur):
            if in_bounds(n, w, h) and n not in blocked and n not in seen:
                seen.add(n)
                q.append(n)
    return count


def bfs_distance_to_targets(
    start: typing.Tuple[int, int],
    targets: typing.Set[typing.Tuple[int, int]],
    w: int,
    h: int,
    blocked: typing.Set[typing.Tuple[int, int]],
    cap: int | None = None,
) -> typing.Optional[int]:
    """
    Return shortest number of steps from start to any target using 4-neighborhood BFS.
    Returns 0 if start is already a target. Returns None if unreachable.
    """
    if not in_bounds(start, w, h) or start in blocked:
        return None
    if start in targets:
        return 0

    seen = set([start])
    q = deque([(start, 0)])
    visited_count = 0
    hard_cap = cap if cap is not None else (w * h)
    while q and visited_count < hard_cap:
        cur, d = q.popleft()
        visited_count += 1
        nd = d + 1
        for n in neighbors(cur):
            if not in_bounds(n, w, h) or n in blocked or n in seen:
                continue
            if n in targets:
                return nd
            seen.add(n)
            q.append((n, nd))
    return None


def count_safe_escapes(
    nxt: typing.Tuple[int, int],
    will_grow: bool,
    w: int,
    h: int,
    my_body: typing.List[typing.Tuple[int, int]],
    others_bodies: typing.Set[typing.Tuple[int, int]],
    h2h_danger: typing.Set[typing.Tuple[int, int]],
    food_set: typing.Set[typing.Tuple[int, int]],
    hazard_set: typing.Set[typing.Tuple[int, int]],
    my_health: int,
) -> int:
    """
    Count how many safe immediate moves exist on the following turn if we move to 'nxt' now.
    Considers our own body update with growth, other bodies (static), head-to-head danger,
    and hazards as blocking when health is low.
    """
    # Compute our body after moving to nxt
    if will_grow:
        new_body = [nxt] + my_body  # grow: tail stays
    else:
        new_body = [nxt] + my_body[:-1]  # normal move: tail moves

    new_head = new_body[0]
    new_neck = new_body[1] if len(new_body) > 1 else None
    new_tail = new_body[-1]

    # Food set after this move (consumed if present)
    new_food_set = set(food_set)
    if nxt in new_food_set:
        new_food_set.remove(nxt)

    # When health is low, treat hazards as blocked for escapes
    avoid_hazards = my_health <= 25

    escapes = 0
    for dx, dy in DIRS.values():
        n2 = (new_head[0] + dx, new_head[1] + dy)

        # Prevent moving backwards into the neck
        if new_neck is not None and n2 == new_neck:
            continue

        # In bounds
        if not in_bounds(n2, w, h):
            continue

        # Optionally avoid hazards
        if avoid_hazards and n2 in hazard_set:
            continue

        # Self collision on next turn, with tail exception if not growing next turn
        will_grow_next = n2 in new_food_set
        my_blocked2 = set(new_body)
        if not will_grow_next:
            my_blocked2.discard(new_tail)  # tail will move away if we don't eat next

        if n2 in my_blocked2:
            continue

        # Avoid others' bodies
        if n2 in others_bodies:
            continue

        # Avoid head-to-head danger
        if n2 in h2h_danger:
            continue

        escapes += 1

    return escapes


def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    you = game_state["you"]

    w, h = board["width"], board["height"]
    my_body = [t(p) for p in you["body"]]
    my_head = my_body[0]
    my_neck = my_body[1] if len(my_body) > 1 else None
    my_tail = my_body[-1]
    my_length = you.get("length", len(my_body))
    my_health = you.get("health", 100)

    food = [t(f) for f in board.get("food", [])]
    food_set = set(food)

    # Hazards (Royale and other maps)
    hazards = [t(hz) for hz in board.get("hazards", [])]
    hazard_set = set(hazards)

    # Opponents
    others = [s for s in board.get("snakes", []) if s["id"] != you["id"]]
    others_bodies = set()
    opp_heads = []
    for s in others:
        body = [t(p) for p in s["body"]]
        others_bodies.update(body)  # conservative: include their tail as blocking
        if body:
            opp_heads.append((body[0], s.get("length", len(body))))

    # Head-to-head danger: squares adjacent to equal-or-longer opponent heads
    h2h_danger = set()
    for head_pos, opp_len in opp_heads:
        if opp_len >= my_length:
            for n in neighbors(head_pos):
                if in_bounds(n, w, h):
                    h2h_danger.add(n)

    # Build candidate moves and evaluate safety
    candidates = []
    backup_candidates = []  # moves with 0 next-turn escapes; used only if no primary candidates

    # Pre-calc nearest food target (for tie-breaking)
    nearest_food = None
    if food:
        nearest_food = min(food, key=lambda f: manhattan(my_head, f))

    # Determine whether nearest food is contested by an equal-or-longer opponent (rough via Manhattan)
    contested_nearest = False
    if nearest_food is not None:
        my_mhd_to_nearest = manhattan(my_head, nearest_food)
        for head_pos, opp_len in opp_heads:
            if opp_len >= my_length:
                if manhattan(head_pos, nearest_food) <= my_mhd_to_nearest:
                    contested_nearest = True
                    break

    # Small helper: penalty for being adjacent to any opponent head (even if shorter)
    def adj_to_any_head(p: typing.Tuple[int, int]) -> bool:
        for head_pos, _ in opp_heads:
            if manhattan(p, head_pos) == 1:
                return True
        return False

    # Compute base-area from current head to discourage drastic reductions
    blocked_for_area_base = set(my_body) | others_bodies | h2h_danger
    if hazard_set and my_health <= 25:
        blocked_for_area_base |= hazard_set
    blocked_for_area_base_nohead = set(blocked_for_area_base)
    blocked_for_area_base_nohead.discard(my_head)
    base_area = flood_fill_area(my_head, w, h, blocked_for_area_base_nohead, cap=400)

    # Precompute safe (non-hazard) targets for hazard escape BFS
    safe_targets = {(x, y) for x in range(w) for y in range(h) if (x, y) not in hazard_set}
    in_hazard_now = my_head in hazard_set

    for mv, (dx, dy) in DIRS.items():
        nxt = (my_head[0] + dx, my_head[1] + dy)

        # 1) Prevent moving backwards into neck
        if my_neck is not None and nxt == my_neck:
            continue

        # 2) Stay in bounds
        if not in_bounds(nxt, w, h):
            continue

        # 3) Self-collision (allow moving into our tail only if we won't grow)
        will_grow = nxt in food_set
        my_blocked = set(my_body)
        if not will_grow:
            # Tail will move away if we don't eat
            my_blocked.discard(my_tail)
        if nxt in my_blocked:
            continue

        # 4) Avoid other snakes' bodies
        if nxt in others_bodies:
            continue

        # 5) Avoid head-to-head with equal-or-larger snakes
        if nxt in h2h_danger:
            continue

        # 5.5) Two-step lookahead: ensure there is at least one safe escape next turn
        escapes = count_safe_escapes(
            nxt=nxt,
            will_grow=will_grow,
            w=w,
            h=h,
            my_body=my_body,
            others_bodies=others_bodies,
            h2h_danger=h2h_danger,
            food_set=food_set,
            hazard_set=hazard_set,
            my_health=my_health,
        )

        # 6) Heuristic scoring:
        #    - Larger reachable area is better (dynamic weight by health)
        #    - Prefer moving closer to food as health drops (BFS path distance)
        #    - Downweight food if contested by equal-or-longer opponents
        #    - Big reward for eating immediately
        #    - Prefer staying away from walls as a small tie-breaker
        #    - Penalize entering hazards based on current health
        #    - Penalize adjacency to any opponent head (reduce entanglements)
        #    - Mild tail-chase to reduce self-collision loops when healthy
        #    - Penalize drastic area drops relative to current position
        #    - Hazard escape: when in hazard or stepping into it, penalize distance to the nearest safe tile and reward immediate exits
        # Build blocked set for flood-fill and BFS from next position
        blocked_for_area = set(my_blocked) | others_bodies | h2h_danger
        # Treat hazards as blocked when health is low to avoid paths through them
        if hazard_set and my_health <= 25:
            blocked_for_area |= hazard_set

        area = flood_fill_area(nxt, w, h, blocked_for_area, cap=400)

        # Dynamic area weight by health: focus on space when healthy; reduce when starving
        if my_health > 70:
            area_w = 7
        elif my_health > 40:
            area_w = 6
        elif my_health > 20:
            area_w = 5
        else:
            area_w = 4

        # Food distance components using BFS to reachable food
        food_term = 0.0
        eat_now_bonus = 0.0
        bfs_dist_to_food = None
        if nearest_food is not None:
            # Use BFS from nxt to any food that's reachable under current blocked set
            bfs_dist_to_food = bfs_distance_to_targets(nxt, food_set, w, h, blocked_for_area, cap=800)
            # Fall back to Manhattan if no path is found
            if bfs_dist_to_food is None:
                nxt_dist = manhattan(nxt, nearest_food)
            else:
                nxt_dist = bfs_dist_to_food

            cur_dist_manhattan = manhattan(my_head, nearest_food)

            # Hunger-weighted pull toward food (closer is better)
            # Scale weight from 2 (healthy) up to 14 (starving)
            if my_health > 60:
                food_weight = 2.0
            elif my_health > 35:
                food_weight = 4.0
            elif my_health > 20:
                food_weight = 8.0
            else:
                food_weight = 14.0

            # Downweight food pull if nearest is contested by equal-or-longer opponents
            if contested_nearest:
                food_weight = max(1.0, food_weight * 0.6)

            food_term = -float(nxt_dist) * food_weight

            # Reward for getting closer this turn (still using Manhattan for a cheap tie-break)
            if nxt_dist < cur_dist_manhattan:
                food_term += 6.0

            # Big reward for eating immediately; slightly scale by missing health
            if nxt in food_set:
                eat_now_bonus = 80.0 + max(0, 100 - my_health) // 4

        # Wall distance (prefer center a little)
        wall_clearance = min(nxt[0], w - 1 - nxt[0], nxt[1], h - 1 - nxt[1])

        # Hazard penalty
        hazard_penalty = 0.0
        if nxt in hazard_set:
            if my_health > 60:
                hazard_penalty = -30.0
            elif my_health > 35:
                hazard_penalty = -45.0
            elif my_health > 20:
                hazard_penalty = -60.0
            else:
                hazard_penalty = -80.0

        # Small-cavity penalties to avoid getting stuck in tiny pockets
        trap_penalty = 0.0
        if area < 4:
            trap_penalty -= 40.0
        elif area < 8:
            trap_penalty -= 10.0

        # Penalty if adjacent to any opponent head (even if shorter)
        adj_head_penalty = -8.0 if adj_to_any_head(nxt) else 0.0

        # Mild tail-chase: encourage getting closer to our predicted tail when healthy
        tail_term = 0.0
        if my_health > 60:
            # Predict tail after our move
            if will_grow or len(my_body) <= 1:
                predicted_tail = my_tail  # tail doesn't move if we grow; or trivial body
            else:
                predicted_tail = my_body[-2]  # tail moves forward by one segment
            # Allow BFS to step onto predicted tail by removing it from the blocked set
            blocked_tail = set(blocked_for_area)
            if predicted_tail in blocked_tail:
                blocked_tail.remove(predicted_tail)
            tail_dist = bfs_distance_to_targets(nxt, {predicted_tail}, w, h, blocked_tail, cap=600)
            if tail_dist is None:
                tail_dist = manhattan(nxt, predicted_tail)
            # Weight baseline
            tail_weight = 1.8
            # Boost when no reachable food and reasonably healthy
            if bfs_dist_to_food is None and my_health > 40:
                tail_weight *= 1.5
            # Reduce if we are about to eat or a food is very close/reachable
            if will_grow:
                tail_weight *= 0.5
            if bfs_dist_to_food is not None and bfs_dist_to_food <= 3:
                tail_weight *= 0.5
            # If very long snake, prefer tail chasing a bit more to avoid knots
            if my_length > (w * h) // 2:
                tail_weight *= 1.3
            tail_term = -float(tail_dist) * tail_weight

        # Area drop penalty relative to current position
        delta_area = area - base_area
        area_delta_penalty = 0.0
        if delta_area <= -20:
            area_delta_penalty = -25.0
        elif delta_area <= -12:
            area_delta_penalty = -10.0

        # Hazard escape term: push toward safe tiles if we are in or moving into hazard
        hazard_escape_term = 0.0
        hazard_exit_bonus = 0.0
        nxt_in_hazard = nxt in hazard_set
        if in_hazard_now or nxt_in_hazard:
            # Build blocked set for escape BFS (do not block hazards; we want path length to safety)
            blocked_for_escape = set(my_blocked) | others_bodies | h2h_danger
            # If not growing, our tail moves; already removed above in my_blocked
            # Compute distance to any safe (non-hazard) tile
            dist_to_safe = bfs_distance_to_targets(nxt, safe_targets, w, h, blocked_for_escape, cap=800)
            # Weight scales with urgency (lower health => stronger)
            if my_health <= 35:
                escape_w = 20.0
            elif my_health <= 60:
                escape_w = 16.0
            else:
                escape_w = 12.0
            if dist_to_safe is None:
                # Strong penalty if we remain in hazard with no visible path to safety
                if nxt_in_hazard:
                    hazard_escape_term -= 120.0
            else:
                hazard_escape_term -= float(dist_to_safe) * escape_w
                # Bonus if we immediately exit hazard
                if in_hazard_now and not nxt_in_hazard:
                    hazard_exit_bonus = 30.0

        # Compose score
        score = area * area_w
        score += food_term + eat_now_bonus
        score += wall_clearance
        score += escapes * 12.0  # stronger preference for more next-turn options
        score += hazard_penalty
        score += trap_penalty
        score += adj_head_penalty
        score += tail_term
        score += area_delta_penalty
        score += hazard_escape_term + hazard_exit_bonus

        # Store into appropriate candidate list
        if escapes == 0:
            # Risky: keep only as backup if no primary safe-escape moves exist
            backup_candidates.append((score, mv))
            continue

        candidates.append((score, mv))

    # Choose best move
    chosen_pool = candidates if candidates else backup_candidates

    if not chosen_pool:
        # No safe moves detected; try a very naive fallback (avoid crashing server)
        print(f"MOVE {game_state.get('turn', '?')}: No candidates! Moving down")
        return {"move": "down"}

    # Choose the move with the highest score; break ties randomly for unpredictability
    max_score = max(s for s, _ in chosen_pool)
    best = [mv for s, mv in chosen_pool if s == max_score]
    next_move = random.choice(best)

    print(f"MOVE {game_state.get('turn', '?')}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})