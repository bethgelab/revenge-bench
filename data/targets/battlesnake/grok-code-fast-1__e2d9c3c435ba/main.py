# Welcome to
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#
# This file can be a nice home for your Battlesnake logic and helper functions.
#
# To get you started we've included code to prevent your Battlesnake from moving backwards.
# For more info see docs.battlesnake.com

import random
import typing
import heapq
def get_available_space(board, start_x, start_y):
    width = board["width"]
    height = board["height"]
    occupied = set()
    for snake in board["snakes"]:
        for segment in snake["body"]:
            occupied.add((segment["x"], segment["y"]))
    for hazard in board.get("hazards", []):
        occupied.add((hazard["x"], hazard["y"]))
    visited = set()
    queue = [(start_x, start_y)]
    visited.add((start_x, start_y))
    count = 1
    while queue:
        x, y = queue.pop(0)
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in occupied and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))
                count += 1
    return count
def a_star_path_length(board, start, goal):
    obstacles = set()
    for snake in board["snakes"]:
        for seg in snake["body"]:
            obstacles.add((seg["x"], seg["y"]))
    for haz in board.get("hazards", []):
        obstacles.add((haz["x"], haz["y"]))
    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    frontier = [(0, start)]
    came_from = {start: None}
    cost_so_far = {start: 0}
    while frontier:
        current = heapq.heappop(frontier)[1]
        if current == goal:
            break
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = current[0] + dx, current[1] + dy
            if 0 <= nx < board["width"] and 0 <= ny < board["height"] and (nx, ny) not in obstacles:
                new_cost = cost_so_far[current] + 1
                if (nx, ny) not in cost_so_far or new_cost < cost_so_far[(nx, ny)]:
                    cost_so_far[(nx, ny)] = new_cost
                    priority = new_cost + heuristic((nx, ny), goal)
                    heapq.heappush(frontier, (priority, (nx, ny)))
                    came_from[(nx, ny)] = current
    if goal not in cost_so_far:
        return float('inf')
    return cost_so_far[goal]


# info is called when you create your Battlesnake on play.battlesnake.com
# and controls your Battlesnake's appearance
# TIP: If you open your Battlesnake URL in a browser you should see this data
def info() -> typing.Dict:
    print("INFO")

    return {
        "apiversion": "1",
        "author": "",  # TODO: Your Battlesnake Username
        "color": "#888888",  # TODO: Choose color
        "head": "default",  # TODO: Choose head
        "tail": "default",  # TODO: Choose tail
    }


# start is called when your Battlesnake begins a game
def start(game_state: typing.Dict):
    print("GAME START")


# end is called when your Battlesnake finishes a game
def end(game_state: typing.Dict):
    print("GAME OVER\n")


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:

    is_move_safe = {"up": True, "down": True, "left": True, "right": True}

    # We've included code to prevent your Battlesnake from moving backwards
    my_head = game_state["you"]["body"][0]  # Coordinates of your head
    my_neck = game_state["you"]["body"][1]  # Coordinates of your "neck"

    if my_neck["x"] < my_head["x"]:  # Neck is left of head, don't move left
        is_move_safe["left"] = False

    elif my_neck["x"] > my_head["x"]:  # Neck is right of head, don't move right
        is_move_safe["right"] = False

    elif my_neck["y"] < my_head["y"]:  # Neck is below head, don't move down
        is_move_safe["down"] = False

    elif my_neck["y"] > my_head["y"]:  # Neck is above head, don't move up
        is_move_safe["up"] = False

    # Prevent moving out of bounds
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]
    if my_head["x"] == 0:
        is_move_safe["left"] = False
    if my_head["x"] == board_width - 1:
        is_move_safe["right"] = False
    if my_head["y"] == 0:
        is_move_safe["down"] = False
    if my_head["y"] == board_height - 1:
        is_move_safe["up"] = False

    # Prevent self-collision
    my_body = game_state["you"]["body"]
    for segment in my_body:
        for move in is_move_safe:
            if is_move_safe[move]:
                new_x = my_head["x"]
                new_y = my_head["y"]
                if move == "left":
                    new_x -= 1
                elif move == "right":
                    new_x += 1
                elif move == "down":
                    new_y -= 1
                elif move == "up":
                    new_y += 1
                if new_x == segment["x"] and new_y == segment["y"]:
                    is_move_safe[move] = False

    # Prevent collision with other snakes
    opponents = game_state["board"]["snakes"]
    my_length = game_state["you"]["length"]
    for snake in opponents:
        for segment in snake["body"]:
            for move in is_move_safe:
                if is_move_safe[move]:
                    new_x = my_head["x"]
                    new_y = my_head["y"]
                    if move == "left":
                        new_x -= 1
                    elif move == "right":
                        new_x += 1
                    elif move == "down":
                        new_y -= 1
                    elif move == "up":
                        new_y += 1
                    if new_x == segment["x"] and new_y == segment["y"]:
                        is_move_safe[move] = False

    # Handle head-to-head collisions: only move into opponent's head if longer
    for snake in opponents:
        opp_head = snake["head"]
        opp_length = snake["length"]
        for move in is_move_safe:
            if is_move_safe[move]:
                new_x = my_head["x"]
                new_y = my_head["y"]
                if move == "left":
                    new_x -= 1
                elif move == "right":
                    new_x += 1
                elif move == "down":
                    new_y -= 1
                elif move == "up":
                    new_y += 1
                if new_x == opp_head["x"] and new_y == opp_head["y"]:
                    if my_length <= opp_length:
                        is_move_safe[move] = False

    # Avoid hazards if present
    hazards = game_state["board"].get("hazards", [])
    for hazard in hazards:
        for move in is_move_safe:
            if is_move_safe[move]:
                new_x = my_head["x"]
                new_y = my_head["y"]
                if move == "left":
                    new_x -= 1
                elif move == "right":
                    new_x += 1
                elif move == "down":
                    new_y -= 1
                elif move == "up":
                    new_y += 1
                if new_x == hazard["x"] and new_y == hazard["y"]:
                    is_move_safe[move] = False

    safe_moves = [move for move in is_move_safe if is_move_safe[move]]
    if not safe_moves:
        next_move = "up"
    else:
        candidates = []
        max_space = -1
        for move in safe_moves:
            new_x = my_head["x"]
            new_y = my_head["y"]
            if move == "left": new_x -= 1
            elif move == "right": new_x += 1
            elif move == "down": new_y -= 1
            elif move == "up": new_y += 1
            space = get_available_space(game_state["board"], new_x, new_y)
            if space > max_space:
                max_space = space
                candidates = [(move, space)]
            elif space == max_space:
                candidates.append((move, space))
        food = game_state["board"]["food"]
        my_tail = my_body[-1]
        tail_chasing = False
        if len(my_body) > 10:
            if food:
                closest_food = min(food, key=lambda f: abs(f["x"] - my_head["x"]) + abs(f["y"] - my_head["y"]))
                closest_food_dist = a_star_path_length(game_state["board"], (my_head["x"], my_head["y"]), (closest_food["x"], closest_food["y"]))
                if closest_food_dist > 10:
                    tail_chasing = True
            else:
                tail_chasing = True
        if tail_chasing:
            # Prioritize shortening path to tail
            best_score = float('inf')
            best_move = candidates[0][0]
            for move, _ in candidates:
                new_x = my_head["x"]
                new_y = my_head["y"]
                if move == "left": new_x -= 1
                elif move == "right": new_x += 1
                elif move == "down": new_y -= 1
                elif move == "up": new_y += 1
                new_tail_path = a_star_path_length(game_state["board"], (new_x, new_y), (my_tail["x"], my_tail["y"]))
                if new_tail_path < best_score:
                    best_score = new_tail_path
                    best_move = move
            next_move = best_move
        else:
            # Original food logic
            if food:
                closest_food = min(food, key=lambda f: abs(f["x"] - my_head["x"]) + abs(f["y"] - my_head["y"]))
                best_score = float('inf')
                best_move = candidates[0][0]
                for move, _ in candidates:
                    new_x = my_head["x"]
                    new_y = my_head["y"]
                    if move == "left": new_x -= 1
                    elif move == "right": new_x += 1
                    elif move == "down": new_y -= 1
                    elif move == "up": new_y += 1
                    length = a_star_path_length(game_state["board"], (new_x, new_y), (closest_food["x"], closest_food["y"]))
                    if length < best_score:
                        best_score = length
                        best_move = move
                next_move = best_move
            else:
                next_move = candidates[0][0]

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})