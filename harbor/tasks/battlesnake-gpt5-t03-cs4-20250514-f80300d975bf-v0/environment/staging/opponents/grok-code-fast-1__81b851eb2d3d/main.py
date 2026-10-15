# Welcome to
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#
# This file can be a nice home for your Battlesnake logic and helper functions.
#
# To get you started we've included code to prevent your Battlesnake from moving backwards.
# For more info see docs.battlesnake.com

import random
import heapq
import typing
from collections import deque


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


def is_out_of_bounds(pos, board):
    return pos['x'] < 0 or pos['x'] >= board['width'] or pos['y'] < 0 or pos['y'] >= board['height']


def is_head_to_head_risk(pos, you, opponents, predicted_opp_heads):
    for opponent in opponents:
        if you["length"] <= opponent["length"]:
            head = opponent["head"]
            if abs(pos["x"] - head["x"]) + abs(pos["y"] - head["y"]) == 1:
                return True
    for phead in predicted_opp_heads:
        if abs(pos["x"] - phead["x"]) + abs(pos["y"] - phead["y"]) == 1:
            return True
    return False


def is_collision(pos, snakes):
    for snake in snakes:
        if pos in snake['body']:
            return True
    return False


def get_available_space(head, board, snakes):
    visited = set()
    queue = deque([(head["x"], head["y"])])
    visited.add((head["x"], head["y"]))
    count = 1
    while queue:
        x, y = queue.popleft()
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x + dx, y + dy
            pos = {"x": nx, "y": ny}
            if not is_out_of_bounds(pos, board) and (nx, ny) not in visited and not is_collision(pos, snakes):
                visited.add((nx, ny))
                queue.append((nx, ny))
                count += 1
    return count

def heuristic(pos, goals):
    return min(abs(pos["x"] - g["x"]) + abs(pos["y"] - g["y"]) for g in goals)

def get_shortest_path_next_move(head, goals, board, snakes):
    if not goals:
        return None
    directions = [(-1, 0, 'left'), (1, 0, 'right'), (0, -1, 'down'), (0, 1, 'up')]
    visited = set()
    pq = []
    heapq.heappush(pq, (0 + heuristic(head, goals), 0, head['x'], head['y'], []))  # f, g, x, y, path
    visited.add((head['x'], head['y']))
    while pq:
        f, g, x, y, path = heapq.heappop(pq)
        for dx, dy, move in directions:
            nx, ny = x + dx, y + dy
            pos = {'x': nx, 'y': ny}
            if not is_out_of_bounds(pos, board) and (nx, ny) not in visited and not is_collision(pos, snakes):
                new_path = path + [move]
                if pos in goals:
                    return new_path[0] if new_path else None
                visited.add((nx, ny))
                new_g = g + 1
                new_f = new_g + heuristic(pos, goals)
                heapq.heappush(pq, (new_f, new_g, nx, ny, new_path))
    return None


# move is called on every turn and returns your next move
# Valid moves are "up", "down", "left", or "right"
# See https://docs.battlesnake.com/api/example-move for available data
def move(game_state: typing.Dict) -> typing.Dict:

    board = game_state['board']
    you = game_state['you']
    head = you['body'][0]
    body = you['body']
    opponents = board['snakes']
    snakes = [you] + opponents
    predicted_opp_heads = []
    for opp in opponents:
        if len(opp['body']) > 1:
            dx = opp['head']['x'] - opp['body'][1]['x']
            dy = opp['head']['y'] - opp['body'][1]['y']
            pred_x = opp['head']['x'] + dx
            pred_y = opp['head']['y'] + dy
            pred_pos = {'x': pred_x, 'y': pred_y}
            if not is_out_of_bounds(pred_pos, board):
                predicted_opp_heads.append(pred_pos)

    possible_moves = {
        "up": {"x": head["x"], "y": head["y"] + 1},
        "down": {"x": head["x"], "y": head["y"] - 1},
        "left": {"x": head["x"] - 1, "y": head["y"]},
        "right": {"x": head["x"] + 1, "y": head["y"]},
    }

    safe_moves = []
    for move, pos in possible_moves.items():
        if not is_out_of_bounds(pos, board) and not is_collision(pos, [you] + opponents) and not is_head_to_head_risk(pos, you, opponents, predicted_opp_heads):
            safe_moves.append(move)
    filtered_safe = [m for m in safe_moves if get_available_space(possible_moves[m], board, snakes) >= 10]
    if filtered_safe:
        safe_moves = filtered_safe

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    snakes = [you] + opponents
    food = board['food']
    next_move = None

    # Prioritize food
    if food:
        next_move = get_shortest_path_next_move(head, food, board, snakes)

    # If no food path or not safe, try attack if larger
    if not next_move or next_move not in safe_moves:
        if you['length'] > max([opp['length'] for opp in opponents] + [0]) + 1 and len(food) < 2 and get_available_space(head, board, snakes) < 30:
            opponent_adjacent = []
            for opp in opponents:
                if len(opp['body']) > 1:
                    tail = opp['body'][-1]
                    opponent_adjacent.append(tail)
            attack_move = get_shortest_path_next_move(head, opponent_adjacent, board, snakes)
            if attack_move and attack_move in safe_moves:
                next_move = attack_move

    # Fallback to center or random
    if not next_move or next_move not in safe_moves:
        if you['health'] < 20:
            center = [{'x': board['width'] // 2, 'y': board['height'] // 2}]
            center_move = get_shortest_path_next_move(head, center, board, snakes)
            if center_move and center_move in safe_moves:
                next_move = center_move
            else:
                # Fallback greedy to center
                center_x = board['width'] // 2
                center_y = board['height'] // 2
                move_distances = {}
                for move in safe_moves:
                    pos = possible_moves[move]
                    dist = abs(pos['x'] - center_x) + abs(pos['y'] - center_y)
                    move_distances[move] = dist
                next_move = min(move_distances, key=move_distances.get)
        else:
            # Choose move with most available space for safety
            space_scores = {}
            for move in safe_moves:
                pos = possible_moves[move]
                space = get_available_space(pos, board, snakes)
                space_scores[move] = space
            next_move = max(space_scores, key=space_scores.get)

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}

# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})