# Enhanced Battlesnake logic with tail dynamics and space control (flood-fill).
import os
import random
import typing
from collections import deque

Move = typing.Literal["up", "down", "left", "right"]
Point = typing.Dict[str, int]

DIRS: typing.Dict[Move, typing.Tuple[int, int]] = {
    "up": (0, 1),
    "down": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}

def point_to_tuple(p: Point) -> typing.Tuple[int, int]:
    return (p["x"], p["y"])

def add(p: typing.Tuple[int, int], d: typing.Tuple[int, int]) -> typing.Tuple[int, int]:
    return (p[0] + d[0], p[1] + d[1])

def in_bounds(p: typing.Tuple[int, int], w: int, h: int) -> bool:
    return 0 <= p[0] < w and 0 <= p[1] < h

def manhattan(a: typing.Tuple[int, int], b: typing.Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def info() -> typing.Dict:
    # Appearance and meta
    print("INFO")
    return {
        "apiversion": "1",
        "author": "gpt-5",
        "color": "#4f46e5",
        "head": "beluga",
        "tail": "curled",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    you = game_state["you"]

    width: int = board["width"]
    height: int = board["height"]

    my_head_t = point_to_tuple(you.get("head", you["body"][0]))
    my_body_t = [point_to_tuple(p) for p in you["body"]]
    my_tail_t = my_body_t[-1] if my_body_t else my_head_t
    my_health: int = you.get("health", 100)
    my_length: int = len(my_body_t)

    # Occupied cells: all snake bodies (including our own)
    occupied: typing.Set[typing.Tuple[int, int]] = set()
    for s in board["snakes"]:
        for p in s["body"]:
            occupied.add(point_to_tuple(p))

    # Hazards (avoid)
    hazards: typing.Set[typing.Tuple[int, int]] = set()
    for hz in board.get("hazards", []):
        hazards.add(point_to_tuple(hz))

    # Foods set
    foods: typing.Set[typing.Tuple[int, int]] = set(point_to_tuple(f) for f in board.get("food", []))

    # Utility: check if cell is blocked given tail-dynamics allowance
    def is_blocked(cell: typing.Tuple[int, int]) -> bool:
        if not in_bounds(cell, width, height):
            return True
        # Treat hazards as blocked for now (conservative)
        if cell in hazards:
            return True
        if cell in occupied:
            # Allow stepping into our current tail if it will vacate (i.e., not a food cell)
            if cell == my_tail_t and cell not in foods:
                return False
            return True
        return False

    # Potential head-to-head danger squares for opponents (their possible next heads)
    opp_heads_by_len: typing.List[typing.Tuple[int, typing.Set[typing.Tuple[int, int]]]] = []

    for s in board["snakes"]:
        if s["id"] == you["id"]:
            continue
        opp_head = point_to_tuple(s.get("head", s["body"][0]))
        opp_len = len(s["body"])
        poss: typing.Set[typing.Tuple[int, int]] = set()
        for d in DIRS.values():
            np = add(opp_head, d)
            if not in_bounds(np, width, height):
                continue
            # Opponents can't move into currently occupied body cells (solid walls)
            if np in occupied:
                continue
            # Conservatively include hazards as possible (they may choose to enter)
            poss.add(np)
        if poss:
            opp_heads_by_len.append((opp_len, poss))

    # A move is unsafe if:
    # - Off the board
    # - Collides with any occupied cell (except our tail cell which vacates if not eating)
    # - Lands in hazard (avoided)
    # - Lands in a square an equal-or-longer opponent could also move into (head-to-head)
    safe_moves: typing.List[Move] = []
    move_positions: typing.Dict[Move, typing.Tuple[int, int]] = {}

    for mv, delta in DIRS.items():
        np = add(my_head_t, delta)
        move_positions[mv] = np

        if not in_bounds(np, width, height):
            continue

        # Occupancy with tail exception
        if np in occupied:
            if not (np == my_tail_t and np not in foods):
                continue

        # Avoid hazards
        if np in hazards:
            continue

        # Head-to-head risk
        head_to_head_bad = False
        for opp_len, poss in opp_heads_by_len:
            if np in poss and opp_len >= my_length:
                head_to_head_bad = True
                break
        if head_to_head_bad:
            continue

        safe_moves.append(mv)

    # Fallback if nothing safe
    if not safe_moves:
        # Choose any move that is in-bounds and not colliding with any body (allow tail exception),
        # prefer non-hazard if available.
        candidates_no_hazard: typing.List[Move] = []
        candidates_with_hazard: typing.List[Move] = []
        for mv, np in move_positions.items():
            if not in_bounds(np, width, height):
                continue
            occ = (np in occupied) and not (np == my_tail_t and np not in foods)
            if occ:
                continue
            if np in hazards:
                candidates_with_hazard.append(mv)
            else:
                candidates_no_hazard.append(mv)
        pool = candidates_no_hazard or candidates_with_hazard
        chosen = random.choice(pool) if pool else "down"
        print(f"MOVE {game_state['turn']}: No safe moves, fallback {chosen}")
        return {"move": chosen}

    # Simple liberty count (number of safe neighboring cells after making a move)
    def liberties(pos: typing.Tuple[int, int]) -> int:
        count = 0
        for d in DIRS.values():
            np = add(pos, d)
            if is_blocked(np):
                continue
            count += 1
        return count

    # Flood-fill to estimate reachable space from a position
    def flood_area(start: typing.Tuple[int, int], cap: int = 100) -> int:
        if is_blocked(start):
            return 0
        seen: typing.Set[typing.Tuple[int, int]] = set([start])
        q: deque = deque([start])
        area = 0
        while q and area < cap:
            cur = q.popleft()
            area += 1
            for d in DIRS.values():
                np = add(cur, d)
                if np in seen:
                    continue
                if is_blocked(np):
                    continue
                seen.add(np)
                q.append(np)
        return area

    # Food targeting
    foods_list = [tuple(f) for f in foods]
    target_food = None
    if foods_list:
        target_food = min(foods_list, key=lambda f: manhattan(my_head_t, f))

    # Scoring for safe moves
    hungry = my_health <= 40
    scores: typing.Dict[Move, float] = {}

    for mv in safe_moves:
        np = move_positions[mv]
        score = 0.0

        # Prefer more freedom immediately
        lib = liberties(np)
        score += lib  # 0..4

        # Prefer larger reachable area (space control)
        area = flood_area(np, cap=100)
        # Weight moderately; cap contribution to avoid overpowering
        score += 0.05 * min(area, 80)  # up to +4.0

        # Mild center preference to avoid hugging walls
        wall_dist = min(np[0], width - 1 - np[0], np[1], height - 1 - np[1])
        score += 0.1 * wall_dist  # up to ~+1 on 11x11

        # Prefer moving closer to food
        if target_food is not None:
            dist_now = manhattan(my_head_t, target_food)
            dist_next = manhattan(np, target_food)
            if dist_next < dist_now:
                score += 2.5 if hungry else 0.5
            # Bonus if landing on food, especially when hungry
            if np == target_food:
                score += 6.0 if hungry else 2.0

        # Slightly penalize being adjacent to any larger/equal opponent head (reduce future risk)
        adj_risk = 0
        for s in board["snakes"]:
            if s["id"] == you["id"]:
                continue
            opp_head = point_to_tuple(s.get("head", s["body"][0]))
            opp_len = len(s["body"])
            if opp_len >= my_length and manhattan(np, opp_head) == 1:
                adj_risk += 1
        if adj_risk:
            score -= 1.5 * adj_risk

        scores[mv] = score

    # Choose the move with the highest score; randomize ties
    best_score = max(scores.values())
    best_moves = [mv for mv, sc in scores.items() if sc == best_score]
    next_move: Move = random.choice(best_moves)

    if os.getenv("DEBUG"):
        print(
            f"TURN {game_state['turn']} | safe={safe_moves} | scores={scores} | chosen={next_move} | best={best_score:.2f}"
        )
    else:
        print(f"MOVE {game_state['turn']}: {next_move} | safe={safe_moves} | best_score={best_score:.2f}")
    return {"move": next_move}

# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})