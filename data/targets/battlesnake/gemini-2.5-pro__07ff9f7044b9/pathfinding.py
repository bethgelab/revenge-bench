import collections
import heapq

def find_path(game_state: dict, start: dict, end: dict, health: int, unsafe_coords: set = None) -> list:
    """
    Finds the lowest-cost path from start to end using Dijkstra's algorithm.
    Moves into 'unsafe_coords' are penalized but not forbidden.
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    
    # Obstacles are absolute barriers (our body, other snake bodies)
    obstacles = set()
    for snake in game_state['board']['snakes']:
        # Our own tail is not an obstacle for the next move
        if snake['id'] == game_state['you']['id']:
            for segment in snake['body'][:-1]:
                obstacles.add((segment['x'], segment['y']))
        else:
            for segment in snake['body']:
                obstacles.add((segment['x'], segment['y']))

    # Priority queue stores (cost, path)
    # The path is a list of coordinate tuples
    pq = [(0, [(start['x'], start['y'])])]
    
    # visited keeps track of the minimum cost to reach a cell
    visited = {(start['x'], start['y']): 0}

    while pq:
        cost, path = heapq.heappop(pq)
        x, y = path[-1]

        # If we have found a better path to this cell already, skip
        if cost > visited.get((x, y), float('inf')):
            continue

        if (x, y) == (end['x'], end['y']):
            return path # Found the lowest-cost path

        for move_x, move_y in [(0, 1), (0, -1), (1, 0), (-1, 0)]: # Up, Down, Right, Left
            next_x, next_y = x + move_x, y + move_y
            next_coord = (next_x, next_y)

            # Check if the next move is within bounds and not an absolute obstacle
            if (0 <= next_x < board_width and
                0 <= next_y < board_height and
                next_coord not in obstacles):
                
                # Determine the cost of this move based on health
                if health > 80:
                    unsafe_cost = 30 # Be very cautious
                elif health < 30:
                    unsafe_cost = 5 # Be more risky
                else:
                    unsafe_cost = 15 # Standard risk
                
                move_cost = unsafe_cost if unsafe_coords and next_coord in unsafe_coords else 1
                new_cost = cost + move_cost
                
                # If we found a new cheaper path to next_coord
                if new_cost < visited.get(next_coord, float('inf')):
                    visited[next_coord] = new_cost
                    new_path = list(path)
                    new_path.append(next_coord)
                    heapq.heappush(pq, (new_cost, new_path))
    
    return None # No path found