import random
import typing
from collections import deque

def bfs_distance(start, goal, obstacles, board_width, board_height):
    if start == goal:
        return 0
    obs = set(obstacles)
    queue = deque([(start[0], start[1], 0)])
    visited = set()
    visited.add(start)
    while queue:
        x, y, dist = queue.popleft()
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < board_width and 0 <= ny < board_height and (nx, ny) not in obs and (nx, ny) not in visited:
                if (nx, ny) == goal:
                    return dist + 1
                visited.add((nx, ny))
                queue.append((nx, ny, dist + 1))
    return None

def info() -> typing.Dict:
    return {
        "apiversion": "1",
        "author": "grok-code-fast-1",
        "color": "#888888",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    pass

def end(game_state: typing.Dict):
    pass

def move(game_state: typing.Dict) -> typing.Dict:
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]

    if my_neck["x"] < my_head["x"]:
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:
        is_move_safe["up"] = False

    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    if my_head["x"] == 0:
        is_move_safe["left"] = False
    if my_head["x"] == board_width - 1:
        is_move_safe["right"] = False
    if my_head["y"] == 0:
        is_move_safe["down"] = False
    if my_head["y"] == board_height - 1:
        is_move_safe["up"] = False

    my_body = game_state['you']['body']
    body_positions = set((part["x"], part["y"]) for part in my_body[1:])

    for move in ["up", "down", "left", "right"]:
        if move == "up":
            x, y = my_head["x"], my_head["y"] - 1
        elif move == "down":
            x, y = my_head["x"], my_head["y"] + 1
        elif move == "left":
            x, y = my_head["x"] - 1, my_head["y"]
        elif move == "right":
            x, y = my_head["x"] + 1, my_head["y"]
        if (x, y) in body_positions:
            is_move_safe[move] = False

    opponents = game_state['board']['snakes']
    opponent_positions = set()
    for snake in opponents:
        opponent_positions.update((part["x"], part["y"]) for part in snake["body"])

    for move in ["up", "down", "left", "right"]:
        if move == "up":
            x, y = my_head["x"], my_head["y"] - 1
        elif move == "down":
            x, y = my_head["x"], my_head["y"] + 1
        elif move == "left":
            x, y = my_head["x"] - 1, my_head["y"]
        elif move == "right":
            x, y = my_head["x"] + 1, my_head["y"]
        if (x, y) in opponent_positions:
            is_move_safe[move] = False

    safe_moves = [move for move in ["up", "down", "left", "right"] if is_move_safe[move]]

    if not safe_moves:
        return {"move": "up"}

    food = game_state['board']['food']
    if food:
        obstacles = body_positions | opponent_positions
        best_moves = []
        best_dist = float('inf')
        for move in safe_moves:
            if move == "up":
                x, y = my_head["x"], my_head["y"] - 1
            elif move == "down":
                x, y = my_head["x"], my_head["y"] + 1
            elif move == "left":
                x, y = my_head["x"] - 1, my_head["y"]
            elif move == "right":
                x, y = my_head["x"] + 1, my_head["y"]
            dist = min(bfs_distance((x, y), (f["x"], f["y"]), obstacles, board_width, board_height) or float('inf') for f in food)
            if dist < best_dist:
                best_dist = dist
                best_moves = [move]
            elif dist == best_dist:
                best_moves.append(move)
        next_move = random.choice(best_moves)
    else:
        next_move = random.choice(safe_moves)

    return {"move": next_move}

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})