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
import copy


# info is called when you create your Battlesnake on play.battlesnake.com
# and controls your Battlesnake's appearance
# TIP: If you open your Battlesnake URL in a browser you should see this data
def info() -> typing.Dict:
    print("INFO")

    return {
        "apiversion": "1",
        "author": "gemini-2.5-pro",
        "color": "#00FF00",  # Green
        "head": "default",
        "tail": "default",
    }


# start is called when your Battlesnake begins a game
def start(game_state: typing.Dict):
    print("GAME START")


# end is called when your Battlesnake finishes a game
def end(game_state: typing.Dict):
    print("GAME OVER\n")


def flood_fill(start_pos, game_state):
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]
    q = [start_pos]
    visited = { (start_pos["x"], start_pos["y"]) }
    count = 0

    all_snakes = []
    for snake in game_state["board"]["snakes"]:
        all_snakes.extend(snake["body"])

    while q:
        curr = q.pop(0)
        count += 1
        for move in [{"x": 0, "y": 1}, {"x": 0, "y": -1}, {"x": 1, "y": 0}, {"x": -1, "y": 0}]:
            next_pos = {"x": curr["x"] + move["x"], "y": curr["y"] + move["y"]}

            if not (0 <= next_pos["x"] < board_width and 0 <= next_pos["y"] < board_height):
                continue
            if (next_pos["x"], next_pos["y"]) in visited:
                continue
            if next_pos in all_snakes:
                continue

            visited.add((next_pos["x"], next_pos["y"]))
            q.append(next_pos)

    return count


def _get_next_head(head, move):

    next_head = head.copy()

    if move == "up":

        next_head["y"] += 1

    elif move == "down":

        next_head["y"] -= 1

    elif move == "left":

        next_head["x"] -= 1

    elif move == "right":

        next_head["x"] += 1

    return next_head

def evaluate_state(game_state, my_id):

    my_snake = None

    for snake in game_state["board"]["snakes"]:

        if snake["id"] == my_id:

            my_snake = snake

            break



    if not my_snake:

        return -float("inf")  # Snake is dead



    my_head = my_snake["body"][0]

    space = flood_fill(my_head, game_state)



    board_width = game_state["board"]["width"]

    board_height = game_state["board"]["height"]


    center_x = board_width // 2
    center_y = board_height // 2

    dist_to_center = abs(my_head["x"] - center_x) + abs(my_head["y"] - center_y)

    # Bonus for being closer to the center, scaled to be a minor factor
    center_bonus = (board_width - dist_to_center) * 0.1

    return space + center_bonus

def simulate_turn(game_state, moves):

    """

    Simulates a single turn of the game.

    moves is a dict of {snake_id: move_string}

    Returns a new game_state object.

    """

    next_state = copy.deepcopy(game_state)

    next_state["turn"] += 1

    all_snakes = next_state["board"]["snakes"]

    board_width = next_state["board"]["width"]

    board_height = next_state["board"]["height"]

    food_locations = [(f["x"], f["y"]) for f in next_state["board"]["food"]]

    new_heads = {}



    # Move snakes and find new head positions

    for snake in all_snakes:

        if snake["id"] in moves:

            move = moves[snake["id"]]

            head = snake["body"][0]

            new_head = _get_next_head(head, move)

            new_heads[snake["id"]] = new_head

            snake["body"].insert(0, new_head)

        else:

            # If no move provided, assume snake dies

            snake["health"] = 0 



    # Handle food eating

    eaten_food = []

    for snake in all_snakes:

        if (snake["body"][0]["x"], snake["body"][0]["y"]) in food_locations:

            snake["health"] = 100

            # Mark food for removal

            eaten_food.append((snake["body"][0]["x"], snake["body"][0]["y"]))

        else:
            snake["health"] -= 1
            if len(snake["body"]) > 1:
                snake["body"].pop()
    

    # Remove eaten food

    next_state["board"]["food"] = [f for f in next_state["board"]["food"] if (f["x"], f["y"]) not in eaten_food]

    
    # Handle deaths
    dead_snake_ids = set()
    # Stage 1: Wall collisions and starvation
    live_snakes = [s for s in all_snakes if s["id"] not in dead_snake_ids]
    for snake in live_snakes:
        head = snake["body"][0]
        if not (0 <= head["x"] < board_width and 0 <= head["y"] < board_height):
            dead_snake_ids.add(snake["id"])
        if snake["health"] <= 0:
            dead_snake_ids.add(snake["id"])

    # Stage 2: Head-to-head collisions
    live_snakes = [s for s in all_snakes if s["id"] not in dead_snake_ids]
    snake_heads = {}
    for snake in live_snakes:
        head = (snake["body"][0]["x"], snake["body"][0]["y"])
        if head not in snake_heads:
            snake_heads[head] = []
        snake_heads[head].append(snake["id"])
    
    for head, ids in snake_heads.items():
        if len(ids) > 1:
            # Find the longest snake(s) at this head position
            max_len = 0
            for snake_id in ids:
                snake_len = len(next(s for s in live_snakes if s["id"] == snake_id)["body"])
                max_len = max(max_len, snake_len)
            
            # All snakes that are not the max length die
            for snake_id in ids:
                snake_len = len(next(s for s in live_snakes if s["id"] == snake_id)["body"])
                if snake_len < max_len:
                    dead_snake_ids.add(snake_id)
            
            # If all snakes are same length, they all die
            num_at_max_len = sum(1 for sid in ids if len(next(s for s in live_snakes if s["id"] == sid)["body"]) == max_len)
            if num_at_max_len > 1:
                 for snake_id in ids:
                    dead_snake_ids.add(snake_id)


    # Stage 3: Body collisions
    live_snakes = [s for s in all_snakes if s["id"] not in dead_snake_ids]
    all_bodies = {} # (x, y) -> [snake_id, snake_id]
    for snake in live_snakes:
        for i, part in enumerate(snake["body"]):
            pos = (part["x"], part["y"])
            if pos not in all_bodies:
                all_bodies[pos] = []
            all_bodies[pos].append(snake["id"])

    for snake in live_snakes:
        head = (snake["body"][0]["x"], snake["body"][0]["y"])
        if len(all_bodies[head]) > 1:
            dead_snake_ids.add(snake["id"])

    # Remove dead snakes from the board
    next_state["board"]["snakes"] = [s for s in all_snakes if s["id"] not in dead_snake_ids]

    return next_state


def _get_simple_opponent_moves(game_state, my_id):
    opponent_moves = {}
    for snake in game_state["board"]["snakes"]:
        if snake["id"] == my_id:
            continue

        head = snake["body"][0]
        neck = snake["body"][1]
        
        possible_moves = ["up", "down", "left", "right"]
        if neck["x"] < head["x"]:
            possible_moves.remove("left")
        elif neck["x"] > head["x"]:
            possible_moves.remove("right")
        elif neck["y"] < head["y"]:
            possible_moves.remove("down")
        elif neck["y"] > head["y"]:
            possible_moves.remove("up")
        
        best_move = "down" # Default
        max_space = -1
        for move in possible_moves:
            next_head = _get_next_head(head, move)
            if (
                0 <= next_head["x"] < game_state["board"]["width"]
                and 0 <= next_head["y"] < game_state["board"]["height"]
            ):
                space = flood_fill(next_head, game_state)
                if space > max_space:
                    max_space = space
                    best_move = move

        opponent_moves[snake["id"]] = best_move
    return opponent_moves

def minimax(game_state, depth, alpha, beta, is_maximizing_player, my_id): 
    if depth == 0 or not any(s["id"] == my_id for s in game_state["board"]["snakes"]): 
        return evaluate_state(game_state, my_id) 

    my_snake = next((s for s in game_state["board"]["snakes"] if s["id"] == my_id), None)

    if my_snake is None: # Our snake is not on the board 
        return evaluate_state(game_state, my_id) 

    my_head = my_snake["body"][0] 
    my_neck = my_snake["body"][1] 

    possible_moves = ["up", "down", "left", "right"] 
    if my_neck["x"] < my_head["x"]: 
        possible_moves.remove("left") 
    elif my_neck["x"] > my_head["x"]: 
        possible_moves.remove("right") 
    elif my_neck["y"] < my_head["y"]: 
        possible_moves.remove("down") 
    elif my_neck["y"] > my_head["y"]: 
        possible_moves.remove("up") 

    safe_moves = [] 
    all_snakes_bodies = [p for s in game_state["board"]["snakes"] for p in s["body"]]

    for move in possible_moves: 
        next_head = _get_next_head(my_head, move) 
        if ( 
            0 <= next_head["x"] < game_state["board"]["width"] 
            and 0 <= next_head["y"] < game_state["board"]["height"] 
            and next_head not in all_snakes_bodies 
        ): 
            safe_moves.append(move) 

    if not safe_moves: 
        return evaluate_state(game_state, my_id) 

    if is_maximizing_player:
        best_score = -float("inf") 
        for move in safe_moves: 
            opponent_moves = _get_simple_opponent_moves(game_state, my_id) 
            all_moves = {my_id: move} 
            all_moves.update(opponent_moves) 
            next_game_state = simulate_turn(game_state, all_moves) 
            score = minimax(next_game_state, depth - 1, alpha, beta, False, my_id) 
            best_score = max(best_score, score)
            alpha = max(alpha, best_score)
            if beta <= alpha:
                break
        return best_score 
    else: # Minimizing player
        best_score = float("inf")
        # In this simple model, the minimizer is just our snake in the future.
        # We'll use the same logic as the maximizer but flip the perspective.
        # A true minimax would iterate through opponent moves here.
        # For now, we simulate our own moves and assume opponents play simply.
        for move in safe_moves: 
            opponent_moves = _get_simple_opponent_moves(game_state, my_id) 
            all_moves = {my_id: move} 
            all_moves.update(opponent_moves) 
            next_game_state = simulate_turn(game_state, all_moves) 
            score = minimax(next_game_state, depth - 1, alpha, beta, True, my_id) 
            best_score = min(best_score, score)
            beta = min(beta, best_score)
            if beta <= alpha:
                break
        return best_score

def move(game_state: typing.Dict) -> typing.Dict:
    my_head = game_state["you"]["body"][0]
    my_neck = game_state["you"]["body"][1]
    my_id = game_state["you"]["id"]
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]

    possible_moves = ["up", "down", "left", "right"]
    if my_neck["x"] < my_head["x"]:
        possible_moves.remove("left")
    elif my_neck["x"] > my_head["x"]:
        possible_moves.remove("right")
    elif my_neck["y"] < my_head["y"]:
        possible_moves.remove("down")
    elif my_neck["y"] > my_head["y"]:
        possible_moves.remove("up")

    safe_moves = []
    all_snakes_bodies = [p for s in game_state["board"]["snakes"] for p in s["body"]]
    for move in possible_moves:
        next_head = _get_next_head(my_head, move)
        if (
            0 <= next_head["x"] < board_width
            and 0 <= next_head["y"] < board_height
            and next_head not in all_snakes_bodies
        ):
            safe_moves.append(move)

    if not safe_moves:
        print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down")
        return {"move": "down"}

    # Use 3-ply look-ahead with Alpha-Beta Pruning
    move_scores = {}
    SEARCH_DEPTH = 3 # The total number of plies (our move + 2 more)
    for move in safe_moves:
        opponent_moves = _get_simple_opponent_moves(game_state, my_id)
        all_moves = {my_id: move}
        all_moves.update(opponent_moves)
        next_game_state = simulate_turn(game_state, all_moves)
        # After our move, it's the opponent's turn (minimizing player), so is_maximizing_player = False
        move_scores[move] = minimax(next_game_state, SEARCH_DEPTH - 1, -float("inf"), float("inf"), False, my_id)
    
    if move_scores:
        best_move = max(move_scores, key=move_scores.get)
        print(f"MOVE {game_state['turn']}: Best move is {best_move} with score {move_scores[best_move]}")
    else:
        best_move = random.choice(safe_moves)
        print(f"MOVE {game_state['turn']}: Scoring failed, choosing random safe move {best_move}")

    return {"move": best_move}


# Start server when run directly
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})