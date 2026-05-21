import typing
import random
import heapq


def manhattan_distance(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

def a_star_search(start_tuple, target_tuple, game_state, obstacles):
    pq = [(0, start_tuple, [])]  # (f_cost, current_pos, path)
    visited = {start_tuple}
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    g_costs = {start_tuple: 0}

    while pq:
        _, current_pos, path = heapq.heappop(pq)

        if current_pos == target_tuple:
            return path

        potential_next_steps = [
            ("up", (current_pos[0], current_pos[1] + 1)),
            ("down", (current_pos[0], current_pos[1] - 1)),
            ("left", (current_pos[0] - 1, current_pos[1])),
            ("right", (current_pos[0] + 1, current_pos[1]))
        ]

        for move_name, next_pos in potential_next_steps:
            if not (0 <= next_pos[0] < board_width and 0 <= next_pos[1] < board_height):
                continue
            if next_pos in obstacles and next_pos != target_tuple:
                continue

            new_g_cost = g_costs[current_pos] + 1

            if next_pos not in visited or new_g_cost < g_costs.get(next_pos, float('inf')):
                visited.add(next_pos)
                g_costs[next_pos] = new_g_cost
                
                h_cost = manhattan_distance(next_pos, target_tuple)
                new_f_cost = new_g_cost + h_cost
                
                new_path = path + [move_name]
                
                heapq.heappush(pq, (new_f_cost, next_pos, new_path))
                
    return None

def get_predicted_hazards(game_state: typing.Dict) -> set:
    hazards = set()
    my_id = game_state['you']['id']
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    all_snake_bodies = set()
    for snake in game_state['board']['snakes']:
        for part in snake['body']:
            all_snake_bodies.add((part['x'], part['y']))

    for opponent in game_state['board']['snakes']:
        if opponent['id'] == my_id:
            continue
        
        opponent_head = opponent['head']
        
        opponent_about_to_eat = False
        for food in game_state['board']['food']:
            if abs(opponent_head['x'] - food['x']) + abs(opponent_head['y'] - food['y']) == 1:
                opponent_about_to_eat = True
                break

        temp_obstacles = all_snake_bodies.copy()
        if len(opponent['body']) > 1:
            opponent_tail = opponent['body'][-1]
            if not opponent_about_to_eat and (opponent_tail['x'], opponent_tail['y']) in temp_obstacles:
                temp_obstacles.remove((opponent_tail['x'], opponent_tail['y']))
        if (opponent_head['x'], opponent_head['y']) in temp_obstacles:
             temp_obstacles.remove((opponent_head['x'], opponent_head['y']))

        potential_moves = [
            {'x': opponent_head['x'], 'y': opponent_head['y'] + 1},
            {'x': opponent_head['x'], 'y': opponent_head['y'] - 1},
            {'x': opponent_head['x'] - 1, 'y': opponent_head['y']},
            {'x': opponent_head['x'] + 1, 'y': opponent_head['y']}
        ]

        for move in potential_moves:
            move_tuple = (move['x'], move['y'])
            if not (0 <= move['x'] < board_width and 0 <= move['y'] < board_height):
                continue
            if move_tuple in temp_obstacles:
                continue
            hazards.add(move_tuple)

    return hazards

def get_obstacles(game_state: typing.Dict) -> set:
    obstacles = set()
    obstacles.update(get_predicted_hazards(game_state))
    my_id = game_state['you']['id']
    my_head = game_state['you']['head']

    is_about_to_eat = False
    for food in game_state['board']['food']:
        if abs(my_head['x'] - food['x']) + abs(my_head['y'] - food['y']) == 1:
            is_about_to_eat = True
            break
            
    for snake in game_state['board']['snakes']:
        body_parts = snake['body']
        if snake['id'] == my_id and not is_about_to_eat and len(body_parts) > 1:
            for part in body_parts[:-1]:
                obstacles.add((part['x'], part['y']))
        else:
            for part in body_parts:
                obstacles.add((part['x'], part['y']))
                
    return obstacles

def flood_fill(start_coord: typing.Dict, game_state: typing.Dict, obstacles: set) -> int:
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    q = [start_coord]
    visited = {(start_coord['x'], start_coord['y'])}
    area_size = 0

    while q:
        current = q.pop(0)
        area_size += 1
        
        neighbors = [
            {'x': current['x'], 'y': current['y'] + 1},
            {'x': current['x'], 'y': current['y'] - 1},
            {'x': current['x'] - 1, 'y': current['y']},
            {'x': current['x'] + 1, 'y': current['y']}
        ]

        for neighbor in neighbors:
            neighbor_tuple = (neighbor['x'], neighbor['y'])
            if neighbor_tuple in visited:
                continue
            if not (0 <= neighbor['x'] < board_width and 0 <= neighbor['y'] < board_height):
                continue
            if neighbor_tuple in obstacles:
                continue
            
            visited.add(neighbor_tuple)
            q.append(neighbor)
            
    return area_size

def get_static_obstacles(game_state: typing.Dict) -> set:
    obstacles = set()
    for snake in game_state['board']['snakes']:
        for part in snake['body']:
            obstacles.add((part['x'], part['y']))
    return obstacles

def find_trapped_opponent_move(game_state: typing.Dict, obstacles: set, potential_moves: dict) -> typing.Optional[str]:
    my_head = game_state['you']['head']
    my_length = game_state['you']['length']
    my_head_tuple = (my_head['x'], my_head['y'])
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    my_accessible_space = 0
    for move_name, next_head in potential_moves.items():
        if (next_head['x'], next_head['y']) not in obstacles:
            temp_obstacles = obstacles.copy()
            temp_obstacles.add(my_head_tuple) 
            space = flood_fill(next_head, game_state, temp_obstacles)
            if space > my_accessible_space:
                my_accessible_space = space

    for opponent in game_state['board']['snakes']:
        if opponent['id'] == game_state['you']['id']:
            continue

        opponent_head = opponent['head']
        opponent_head_tuple = (opponent_head['x'], opponent_head['y'])
        opponent_length = opponent['length']

        if opponent_length < my_length - 1:
            continue

        opponent_potential_moves = [
            {'x': opponent_head['x'], 'y': opponent_head['y'] + 1},
            {'x': opponent_head['x'], 'y': opponent_head['y'] - 1},
            {'x': opponent_head['x'] - 1, 'y': opponent_head['y']},
            {'x': opponent_head['x'] + 1, 'y': opponent_head['y']}
        ]
        
        opponent_accessible_space = 0
        opponent_obstacles = get_static_obstacles(game_state)

        opponent_about_to_eat = False
        for food in game_state['board']['food']:
            if abs(opponent_head['x'] - food['x']) + abs(opponent_head['y'] - food['y']) == 1:
                opponent_about_to_eat = True
                break
        
        if not opponent_about_to_eat and len(opponent['body']) > 1:
            opponent_tail = opponent['body'][-1]
            opponent_obstacles.discard((opponent_tail['x'], opponent_tail['y']))

        for move in opponent_potential_moves:
            move_tuple = (move['x'], move['y'])
            if not (0 <= move_tuple[0] < board_width and 0 <= move_tuple[1] < board_height):
                continue
            if move_tuple in opponent_obstacles:
                continue
            space = flood_fill(move, game_state, opponent_obstacles)
            if space > opponent_accessible_space:
                opponent_accessible_space = space

        if opponent_accessible_space < opponent_length and my_accessible_space > opponent_accessible_space:
            print(f"INFO: Trap detected! Opponent {opponent['id']} has {opponent_accessible_space} space.")
            path_to_opponent = a_star_search(my_head_tuple, opponent_head_tuple, game_state, obstacles)
            if path_to_opponent:
                print(f"INFO: Moving to intercept trapped opponent.")
                return path_to_opponent[0]

    return None

def is_path_safe(path, start_coord, obstacles, board_width, board_height, target_tuple=None):
    """
    Checks if an entire path is safe against a given set of obstacles.
    """
    current_pos = start_coord.copy()
    for move in path:
        if move == "up":
            current_pos["y"] += 1
        elif move == "down":
            current_pos["y"] -= 1
        elif move == "left":
            current_pos["x"] -= 1
        elif move == "right":
            current_pos["x"] += 1
        
        if not (0 <= current_pos['x'] < board_width and 0 <= current_pos['y'] < board_height):
            return False
            
        if (current_pos['x'], current_pos['y']) in obstacles and (current_pos['x'], current_pos['y']) != target_tuple:
            return False
            
    return True

def move(game_state: typing.Dict) -> typing.Dict:
    my_head = game_state["you"]["head"]
    my_neck = game_state["you"]["body"][1]
    
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']

    potential_moves = {
        "up": {"x": my_head["x"], "y": my_head["y"] + 1},
        "down": {"x": my_head["x"], "y": my_head["y"] - 1},
        "left": {"x": my_head["x"] - 1, "y": my_head["y"]},
        "right": {"x": my_head["x"] + 1, "y": my_head["y"]},
    }
    
    is_move_safe = {"up": True, "down": True, "left": True, "right": True}
    if my_neck["x"] < my_head["x"]:
        is_move_safe["left"] = False
    elif my_neck["x"] > my_head["x"]:
        is_move_safe["right"] = False
    elif my_neck["y"] < my_head["y"]:
        is_move_safe["down"] = False
    elif my_neck["y"] > my_head["y"]:
        is_move_safe["up"] = False

    obstacles = get_obstacles(game_state)
    
    safe_moves = []
    for move_name, next_head in potential_moves.items():
        if not is_move_safe[move_name]:
            continue
        if not (0 <= next_head['x'] < board_width and 0 <= next_head['y'] < board_height):
            continue
        if (next_head['x'], next_head['y']) not in obstacles:
            safe_moves.append(move_name)

    next_move = None
    
    trap_move = find_trapped_opponent_move(game_state, obstacles, potential_moves)
    if trap_move and trap_move in safe_moves:
        print(f"INFO: Activating trap mode!")
        next_move = trap_move

    if next_move is None:
        my_health = game_state["you"]["health"]
        my_length = game_state['you']['length']
        if my_health > 65:
            potential_targets = []
            for opponent in game_state['board']['snakes']:
                if opponent['id'] != game_state['you']['id'] and opponent['length'] < my_length:
                    dist = abs(my_head['x'] - opponent['head']['x']) + abs(my_head['y'] - opponent['head']['y'])
                    if dist < 5:
                        potential_targets.append(opponent)
            
            potential_targets.sort(key=lambda s: s['length'])
            
            if potential_targets:
                my_head_tuple = (my_head['x'], my_head['y'])
                for target in potential_targets:
                    target_head = (target['head']['x'], target['head']['y'])
                    path_to_opponent = a_star_search(my_head_tuple, target_head, game_state, obstacles)
                    if path_to_opponent and is_path_safe(path_to_opponent, my_head, obstacles, board_width, board_height, target_tuple=target_head):
                        first_step_coord = potential_moves[path_to_opponent[0]]
                        accessible_space = flood_fill(first_step_coord, game_state, obstacles)
                        if accessible_space > my_length:
                            print(f"INFO: Aggressive mode activated! Hunting snake {target['id']}")
                            next_move = path_to_opponent[0]
                            break

    if next_move is None:
        my_health = game_state["you"]["health"]
        food = game_state['board']['food']
        if my_health < 50 and len(food) > 0:
            my_head_tuple = (my_head['x'], my_head['y'])
            
            shortest_path = None
            sorted_food = sorted(food, key=lambda f: abs(my_head['x'] - f['x']) + abs(my_head['y'] - f['y']))
            
            for f in sorted_food:
                target_coord = (f['x'], f['y'])
                path = a_star_search(my_head_tuple, target_coord, game_state, obstacles)
                if path and (shortest_path is None or len(path) < len(shortest_path)):
                     if is_path_safe(path, my_head, obstacles, board_width, board_height):
                        shortest_path = path
            
            if shortest_path:
                print(f"INFO: Hunger mode activated! Seeking food.")
                next_move = shortest_path[0]

    if next_move is None:
        if safe_moves:
            print(f"INFO: Defaulting to space control.")
            best_move = random.choice(safe_moves)
            max_space = -1
            for move in safe_moves:
                next_head = potential_moves[move]
                space_size = flood_fill(next_head, game_state, obstacles)
                if space_size > max_space:
                    max_space = space_size
                    best_move = move
            next_move = best_move
        else:
            print(f"MOVE {game_state['turn']}: No safe moves detected! Moving down.")
            next_move = "down"

    print(f"MOVE {game_state['turn']}: {next_move}")
    return {"move": next_move}

def info():
    return {"apiversion": "1", "author": "MyTeam", "color": "#FF0000", "head": "default", "tail": "default"}

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})