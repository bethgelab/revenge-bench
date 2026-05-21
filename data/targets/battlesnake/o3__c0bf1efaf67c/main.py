import random
import typing

# ---------------- Battlesnake API ---------------- #
def info() -> typing.Dict:
    """
    Called when registering the snake. Adjust appearance here.
    """
    return {
        "apiversion": "1",
        "author": "team-o3",          # Battlesnake username / team
        "color": "#3366ff",
        "head": "beluga",
        "tail": "bolt",
    }

def start(game_state: typing.Dict):
    print(f"GAME START: {game_state.get('game', {}).get('id', '')}")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

# -------------------------------------------------- #
# Helper utilities                                   #
# -------------------------------------------------- #
Point = typing.Dict[str, int]  # simple alias


def adjacent(p: Point, move: str) -> Point:
    """Return the coordinate obtained by moving one step from p in given direction."""
    if move == "up":
        return {"x": p["x"], "y": p["y"] + 1}
    if move == "down":
        return {"x": p["x"], "y": p["y"] - 1}
    if move == "left":
        return {"x": p["x"] - 1, "y": p["y"]}
    if move == "right":
        return {"x": p["x"] + 1, "y": p["y"]}
    raise ValueError(f"Invalid move {move}")


def manhattan(a: Point, b: Point) -> int:
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def build_hazards(game_state: typing.Dict) -> typing.Set[typing.Tuple[int, int]]:
    """
    Build a set of coordinates regarded as hazardous (snake bodies).
    """
    hazards: typing.Set[typing.Tuple[int, int]] = set()
    for snake in game_state["board"]["snakes"]:
        for segment in snake["body"]:
            hazards.add((segment["x"], segment["y"]))
    return hazards


def opponent_head_threats(game_state: typing.Dict, my_length: int) -> typing.Set[typing.Tuple[int, int]]:
    """
    Squares that could be occupied by an opponent head next turn where the opponent
    is equal or longer than us (head-to-head collision hazard).
    """
    threats: typing.Set[typing.Tuple[int, int]] = set()
    for snake in game_state["board"]["snakes"]:
        if snake["id"] == game_state["you"]["id"]:
            continue
        if len(snake["body"]) < my_length:
            # Smaller snake; head-to-head favours us, can ignore.
            continue
        head = snake["body"][0]
        for move in ["up", "down", "left", "right"]:
            n = adjacent(head, move)
            threats.add((n["x"], n["y"]))
    return threats


def safe_moves(game_state: typing.Dict) -> typing.List[str]:
    """
    Return list of moves safe w.r.t walls, bodies, and dangerous head-to-head.
    """
    board_w = game_state["board"]["width"]
    board_h = game_state["board"]["height"]
    head = game_state["you"]["body"][0]
    neck = game_state["you"]["body"][1] if len(game_state["you"]["body"]) > 1 else None

    hazards = build_hazards(game_state)
    threats = opponent_head_threats(game_state, len(game_state["you"]["body"]))

    moves = []
    for mv in ["up", "down", "left", "right"]:
        nxt = adjacent(head, mv)

        # prevent moving backwards into neck
        if neck and nxt["x"] == neck["x"] and nxt["y"] == neck["y"]:
            continue

        # wall check
        if not (0 <= nxt["x"] < board_w and 0 <= nxt["y"] < board_h):
            continue

        # body collision check
        if (nxt["x"], nxt["y"]) in hazards:
            continue

        # head-to-head threat
        if (nxt["x"], nxt["y"]) in threats:
            continue

        moves.append(mv)
    return moves


def choose_move_towards_food(safe: typing.List[str], game_state: typing.Dict) -> str:
    """
    Pick among safe moves the one that brings us closest to nearest food.
    If no food or tie, choose randomly.
    """
    if not safe:
        return "down"  # fallback

    foods = game_state["board"]["food"]
    if not foods:
        return random.choice(safe)

    head = game_state["you"]["body"][0]
    # find nearest food
    nearest = min(foods, key=lambda f: manhattan(head, f))
    # evaluate moves by distance after move
    best_moves = []
    best_dist = None
    for mv in safe:
        nxt = adjacent(head, mv)
        dist = manhattan(nxt, nearest)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_moves = [mv]
        elif dist == best_dist:
            best_moves.append(mv)
    return random.choice(best_moves) if best_moves else random.choice(safe)

# -------------------------------------------------- #
# Main move logic                                    #
# -------------------------------------------------- #
def move(game_state: typing.Dict) -> typing.Dict:
    turn = game_state.get("turn", 0)
    safe = safe_moves(game_state)

    if not safe:
        # desperation: move any direction (will likely die)
        print(f"MOVE {turn}: No safe moves. Defaulting down.")
        return {"move": "down"}

    # health-based priority: if health below 40, prioritise going to food
    next_move = choose_move_towards_food(safe, game_state) if game_state["you"]["health"] < 40 else choose_move_towards_food(safe, game_state)

    print(f"MOVE {turn}: {next_move} (safe:{len(safe)})")
    return {"move": next_move}


# Local testing server
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})