# Welcome to
import heapq
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  | |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#
# This file can be a nice home for your Battlesnake logic and helper functions.
#
# To get you started we've included code to prevent your Battlesnake from moving backwards.
# For more info see docs.battlesnake.com

import random
import typing


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


def get_distance(pos1, pos2):
    return abs(pos1['x'] - pos2['x']) + abs(pos1['y'] - pos2['y'])

def a_star_path(start, goal, obstacles, width, height):
    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # left, right, down, up
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {start: 0}
    f_score = {start: heuristic(start, goal)}
    
    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path
        
        for dx, dy in directions:
            neighbor = (current[0] + dx, current[1] + dy)
            if 0 <= neighbor[0] < width and 0 <= neighbor[1] < height and neighbor not in obstacles:
                tentative_g = g_score[current] + 1
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
    return []  # No path found


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1] if len(game_state["you"]["body"]) > 1 else None
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    my_body = game_state['you']['body']
    opponents = game_state['board']['snakes']
    food = game_state['board']['food']
    health = game_state["you"]["health"]

    possible_moves = ["up", "down", "left", "right"]
    safe_moves = []

    for move in possible_moves:
        next_x = my_head['x']
        next_y = my_head['y']
        if move == "up":
            next_y += 1
        elif move == "down":
            next_y -= 1
        elif move == "left":
            next_x -= 1
        elif move == "right":
            next_x += 1

        # Prevent moving backwards into neck
        if my_neck and ((move == "left" and my_neck["x"] < my_head["x"]) or
                        (move == "right" and my_neck["x"] > my_head["x"]) or
                        (move == "down" and my_neck["y"] < my_head["y"]) or
                        (move == "up" and my_neck["y"] > my_head["y"])):
            continue

        # Prevent out of bounds
        if next_x < 0 or next_x >= board_width or next_y < 0 or next_y >= board_height:
            continue

        # Prevent self collision
        collision = False
        for segment in my_body:
            if next_x == segment['x'] and next_y == segment['y']:
                collision = True
                break
        if not collision:
            # Prevent opponent collision
            for snake in opponents:
                # Avoid opponent's body segments (excluding head)
                for segment in snake['body'][1:]:
                    if next_x == segment['x'] and next_y == segment['y']:
                        collision = True
                        break
                if collision:
                    break
                # Check opponent's head - only collide if we are not larger
                if next_x == snake['body'][0]['x'] and next_y == snake['body'][0]['y']:
                    if len(my_body) <= len(snake['body']):
                        collision = True
                        break
        if collision:
            continue

        safe_moves.append((move, next_x, next_y))

    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    obstacles = set()
    for snake in [game_state['you']] + opponents:
        for segment in snake['body'][:-1]:  # exclude tails for trapping
            obstacles.add((segment['x'], segment['y']))

    if health >= 50:
        # Prioritize trapping by moving towards smaller opponents' tails if larger
        smaller_opponents = [s for s in opponents if len(s['body']) < len(my_body)]
        # Find the tail with the shortest A* path
        min_path_len = float('inf')
        best_path = None
        for s in smaller_opponents:
            tail = s['body'][-1]
            path = a_star_path((my_head['x'], my_head['y']), (tail['x'], tail['y']), obstacles, board_width, board_height)
            if path and len(path) < min_path_len:
                min_path_len = len(path)
                best_path = path
        if best_path:
            # Move to the first step in path
            next_pos = best_path[0]
            dx = next_pos[0] - my_head['x']
            dy = next_pos[1] - my_head['y']
            if dx == -1:
                next_move = "left"
            elif dx == 1:
                next_move = "right"
            elif dy == -1:
                next_move = "down"
            elif dy == 1:
                next_move = "up"
            else:
                next_move = random.choice([m for m, _, _ in safe_moves])
        else:
            # Move towards food with A*
            if food:
                min_path_len = float('inf')
                best_path = None
                for f in food:
                    path = a_star_path((my_head['x'], my_head['y']), (f['x'], f['y']), obstacles, board_width, board_height)
                    if path and len(path) < min_path_len:
                        min_path_len = len(path)
                        best_path = path
                if best_path:
                    next_pos = best_path[0]
                    dx = next_pos[0] - my_head['x']
                    dy = next_pos[1] - my_head['y']
                    if dx == -1:
                        next_move = "left"
                    elif dx == 1:
                        next_move = "right"
                    elif dy == -1:
                        next_move = "down"
                    elif dy == 1:
                        next_move = "up"
                    else:
                        next_move = random.choice([m for m, _, _ in safe_moves])
                else:
                    next_move = random.choice([m for m, _, _ in safe_moves])
            else:
                next_move = random.choice([m for m, _, _ in safe_moves])
    else:
        # Move towards food with A*
        if food:
            min_path_len = float('inf')
            best_path = None
            for f in food:
                path = a_star_path((my_head['x'], my_head['y']), (f['x'], f['y']), obstacles, board_width, board_height)
                if path and len(path) < min_path_len:
                    min_path_len = len(path)
                    best_path = path
            if best_path:
                next_pos = best_path[0]
                dx = next_pos[0] - my_head['x']
                dy = next_pos[1] - my_head['y']
                if dx == -1:
                    next_move = "left"
                elif dx == 1:
                    next_move = "right"
                elif dy == -1:
                    next_move = "down"
                elif dy == 1:
                    next_move = "up"
                else:
                    next_move = random.choice([m for m, _, _ in safe_moves])
            else:
                next_move = random.choice([m for m, _, _ in safe_moves])
        else:
            next_move = random.choice([m for m, _, _ in safe_moves])

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})