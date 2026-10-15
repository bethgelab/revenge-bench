import typing

class GameState:
    def __init__(self, initial_state: typing.Dict):
        self.width = initial_state['board']['width']
        self.height = initial_state['board']['height']
        self.food = set((f['x'], f['y']) for f in initial_state['board']['food'])
        
        self.snakes = []
        for s in initial_state['board']['snakes']:
            snake_data = {
                'id': s['id'],
                'health': s['health'],
                'body': [(p['x'], p['y']) for p in s['body']]
            }
            self.snakes.append(snake_data)

    def clone(self):
        # This will be a much faster way to copy the state for simulation
        new_state = GameState.__new__(GameState) # Create a new instance without calling __init__
        new_state.width = self.width
        new_state.height = self.height
        new_state.food = self.food.copy()
        
        new_state.snakes = []
        for s in self.snakes:
            new_state.snakes.append({
                'id': s['id'],
                'health': s['health'],
                'body': list(s['body']) # Copy the list
            })
            
        return new_state

    def simulate_move(self, snake_id: str, move: str):
        """
        Creates a new game_state object representing the board after a single snake makes a move.
        Decrements health and handles food.
        Does NOT handle collisions, assuming the move is valid.
        Returns a NEW GameState object.
        """
        new_state = self.clone()
        
        snake_to_move = None
        for snake in new_state.snakes:
            if snake["id"] == snake_id:
                snake_to_move = snake
                break
                
        if not snake_to_move:
            return new_state

        head = snake_to_move["body"][0]
        
        move_offsets = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
        offset = move_offsets[move]
        
        new_head = (head[0] + offset[0], head[1] + offset[1])
        
        snake_to_move["body"].insert(0, new_head)
        
        if new_head in new_state.food:
            snake_to_move["health"] = 100
            new_state.food.remove(new_head)
        else:
            snake_to_move["body"].pop()
            snake_to_move["health"] -= 1
        
        return new_state