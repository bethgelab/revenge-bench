#!/usr/bin/env python3
import random
import typing
from collections import deque

# -----------------------------------------------------------------------------
# Battlesnake metadata
# -----------------------------------------------------------------------------
def info() -> typing.Dict:
    """
    Basic Battlesnake customization data.
    """
    print("INFO")
    return {
        "apiversion": "1",
        "author": "team-o3",
        "color": "#33ccff",
        "head": "default",
        "tail": "default",
    }

# -----------------------------------------------------------------------------
# Game lifecycle hooks
# -----------------------------------------------------------------------------
def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

# -----------------------------------------------------------------------------
# Core move logic
# -----------------------------------------------------------------------------
def move(game_state: typing.Dict) -> typing.Dict:
    """
    Strategy overview:

    1. Determine which adjacent squares are safe (not walls, bodies, or hazards).
    2. Run a quick flood-fill from each safe square to estimate free space.
    3. Prefer moves that maximise free space.
    4. Break ties by minimising distance to the nearest food.
    5. If no safe moves exist, pick a random direction to avoid crashing.

    The flood-fill step keeps the snake out of cramped corridors and dead-ends,
    leading to longer average survival without heavy computation.
    """
    # Current head position
    my_head = game_state["you"]["body"][0]
    width   = game_state["board"]["width"]
    height  = game_state["board"]["height"]

    # -------------------------------------------------------------------------
    # Build helper sets for quick lookup
    # -------------------------------------------------------------------------
    occupied = {
        (segment["x"], segment["y"])
        for snake in game_state["board"]["snakes"]
        for segment in snake["body"]
    }
    hazards = {
        (hz["x"], hz["y"])
        for hz in game_state["board"].get("hazards", [])
    }

    # Potential new coordinates for each direction
    potential = {
        "up":    (my_head["x"],     my_head["y"] + 1),
        "down":  (my_head["x"],     my_head["y"] - 1),
        "left":  (my_head["x"] - 1, my_head["y"]),
        "right": (my_head["x"] + 1, my_head["y"]),
    }

    # -------------------------------------------------------------------------
    # Filter out moves that hit walls, bodies, or hazards
    # -------------------------------------------------------------------------
    safe_moves = []
    for move, (x, y) in potential.items():
        if x < 0 or x >= width or y < 0 or y >= height:
            continue              # Wall
        if (x, y) in occupied:
            continue              # Any snake body
        if (x, y) in hazards:
            continue              # Hazard tiles cause health loss â avoid
        safe_moves.append(move)

    # -------------------------------------------------------------------------
    # Avoid potential head-to-head collisions with equal or larger snakes
    # -------------------------------------------------------------------------
    my_length = len(game_state["you"]["body"])
    dangerous_moves = set()
    for move_candidate in list(safe_moves):
        cx, cy = potential[move_candidate]
        for snake in game_state["board"]["snakes"]:
            if snake["id"] == game_state["you"]["id"]:
                continue
            opp_head   = snake["body"][0]
            opp_length = len(snake["body"])
            if abs(opp_head["x"] - cx) + abs(opp_head["y"] - cy) == 1 and opp_length >= my_length:
                dangerous_moves.add(move_candidate)

    refined_moves = [m for m in safe_moves if m not in dangerous_moves]
    if refined_moves:
        safe_moves = refined_moves

    # -------------------------------------------------------------------------
    # Emergency fallback if trapped
    # -------------------------------------------------------------------------
    if not safe_moves:
        fallback = random.choice(list(potential.keys()))
        print(f"MOVE {game_state['turn']}: No safe moves, forced to go {fallback}")
        return {"move": fallback}

    # -------------------------------------------------------------------------
    # Flood-fill to estimate free space for each safe move
    # -------------------------------------------------------------------------
    def flood_fill(start: typing.Tuple[int, int], limit: int = 100) -> int:
        """
        Returns an approximate count of reachable free squares from `start`
        (including start). Stops early at `limit` to cap CPU usage.
        """
        visited = set()
        q = deque([start])
        while q and len(visited) < limit:
            x, y = q.popleft()
            if (x, y) in visited:
                continue
            visited.add((x, y))
            for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                if 0 <= nx < width and 0 <= ny < height and \
                   (nx, ny) not in occupied and (nx, ny) not in hazards and \
                   (nx, ny) not in visited:
                    q.append((nx, ny))
        return len(visited)

    space_scores = {m: flood_fill(potential[m]) for m in safe_moves}
    max_space    = max(space_scores.values())
    roomy_moves  = [m for m in safe_moves if space_scores[m] == max_space]

    # -------------------------------------------------------------------------
    # Break ties with food distance
    # -------------------------------------------------------------------------
    chosen_pool = roomy_moves
    food = game_state["board"].get("food", [])
    if food and chosen_pool:
        def dist_to_closest(coord):
            x, y = coord
            return min(abs(x - f["x"]) + abs(y - f["y"]) for f in food)

        distances  = {m: dist_to_closest(potential[m]) for m in chosen_pool}
        min_dist   = min(distances.values())
        chosen_pool = [m for m in chosen_pool if distances[m] == min_dist]

    # -------------------------------------------------------------------------
    # Select final move
    # -------------------------------------------------------------------------
    next_move = random.choice(chosen_pool) if chosen_pool else random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}

# -----------------------------------------------------------------------------
# Local server entry-point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})