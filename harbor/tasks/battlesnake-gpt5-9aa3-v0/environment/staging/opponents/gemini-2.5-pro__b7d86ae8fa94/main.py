# Welcome to
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
        "author": "gemini-2.5-pro",
        "color": "#0000FF",  # Blue
        "head": "evil",
        "tail": "round-bum",
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

    # Step 1 - Prevent your Battlesnake from moving out of bounds
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

    # Step 2 - Prevent your Battlesnake from colliding with itself
    my_body = game_state['you']['body']
    
    potential_moves = {
        "up": {"x": my_head["x"], "y": my_head["y"] + 1},
        "down": {"x": my_head["x"], "y": my_head["y"] - 1},
        "left": {"x": my_head["x"] - 1, "y": my_head["y"]},
        "right": {"x": my_head["x"] + 1, "y": my_head["y"]},
    }

    for move, pos in potential_moves.items():
        if pos in my_body:
            is_move_safe[move] = False
 
    # Step 3 - Prevent your Battlesnake from colliding with other Battlesnakes
    my_length = len(game_state['you']['body'])
    opponents = game_state['board']['snakes']
    for opponent in opponents:
        if opponent['id'] == game_state['you']['id']:
            continue
        
        opponent_body = opponent['body']
        opponent_head = opponent_body[0]

        # Calculate opponent's potential moves for head-on check
        opp_potential_moves = [
            {"x": opponent_head["x"], "y": opponent_head["y"] + 1},
            {"x": opponent_head["x"], "y": opponent_head["y"] - 1},
            {"x": opponent_head["x"] - 1, "y": opponent_head["y"]},
            {"x": opponent_head["x"] + 1, "y": opponent_head["y"]},
        ]
        
        is_opponent_bigger_or_equal = my_length <= len(opponent_body)

        for move, pos in potential_moves.items():
            # Standard body collision check
            if pos in opponent_body:
                is_move_safe[move] = False
            # Head-to-head collision check
            if is_opponent_bigger_or_equal and (pos in opp_potential_moves):
                is_move_safe[move] = False

    # Are there any safe moves left?
    safe_moves = []
    for move, isSafe in is_move_safe.items():
        if isSafe:
            safe_moves.append(move)

    if len(safe_moves) == 0:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving up")
        return {"move": "up"}

    # If only one safe move, take it
    if len(safe_moves) == 1:
        next_move = safe_moves[0]
        print(f"MOVE {game_state['turn']}: Only one safe move: {next_move}")
        return {"move": next_move}

    # Step 4: Use Flood Fill to determine the area available from each safe move
    move_areas = {}
    for move in safe_moves:
        start_pos = potential_moves[move]
        q = [start_pos]
        visited = {tuple(p.values()) for p in my_body} # Use values() for tuple conversion
        visited.add(tuple(start_pos.values()))
        count = 0
        
        while q:
            pos = q.pop(0)
            count += 1
            
            # Check neighbors
            for next_pos in [{"x": pos["x"], "y": pos["y"] + 1}, {"x": pos["x"], "y": pos["y"] - 1}, {"x": pos["x"] - 1, "y": pos["y"]}, {"x": pos["x"] + 1, "y": pos["y"]}]:
                if tuple(next_pos.values()) not in visited and \
                   0 <= next_pos['x'] < board_width and \
                   0 <= next_pos['y'] < board_height:
                    
                    is_safe_tile = True
                    for opponent in opponents:
                        if next_pos in opponent['body']:
                            is_safe_tile = False
                            break
                    
                    if is_safe_tile:
                        q.append(next_pos)
                        visited.add(tuple(next_pos.values()))
        move_areas[move] = count

    # Default to the move with the largest area
    next_move = max(move_areas, key=move_areas.get)

    # Step 5 - Move towards food, biased by available area
    food = game_state['board']['food']
    move_made = False
    if len(food) > 0:
        closest_food = min(
            food,
            key=lambda f: abs(f['x'] - my_head['x']) + abs(f['y'] - my_head['y'])
        )

        preferred_moves = []
        if closest_food['x'] < my_head['x']:
            preferred_moves.append("left")
        elif closest_food['x'] > my_head['x']:
            preferred_moves.append("right")
        
        if closest_food['y'] < my_head['y']:
            preferred_moves.append("down")
        elif closest_food['y'] > my_head['y']:
            preferred_moves.append("up")

        random.shuffle(preferred_moves)

        # Find the best preferred move that is also safe and has a large area
        best_preferred_move = ""
        max_area = -1
        for move in preferred_moves:
            if move in safe_moves and move_areas.get(move, 0) > max_area:
                max_area = move_areas[move]
                best_preferred_move = move
        
        if best_preferred_move != "":
            next_move = best_preferred_move
            move_made = True

    # Step 6: If no move towards food was made, chase tail, biased by area.
    if not move_made:
        my_tail = game_state["you"]["body"][-1]
        preferred_moves = []
        if my_tail['x'] < my_head['x']:
            preferred_moves.append("left")
        elif my_tail['x'] > my_head['x']:
            preferred_moves.append("right")

        if my_tail['y'] < my_head['y']:
            preferred_moves.append("down")
        elif my_tail['y'] > my_head['y']:
            preferred_moves.append("up")
        
        random.shuffle(preferred_moves)
        
        best_preferred_move = ""
        max_area = -1
        for move in preferred_moves:
            if move in safe_moves and move_areas.get(move, 0) > max_area:
                max_area = move_areas[move]
                best_preferred_move = move

        if best_preferred_move != "":
            next_move = best_preferred_move


    print(f"MOVE {game_state['turn']}: {next_move} (Area: {move_areas.get(next_move, 'N/A')})")
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})