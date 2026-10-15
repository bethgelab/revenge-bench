import typing
import random
import time
from minimax import find_best_move_with_lookahead
from game_state import GameState
from utils import get_safe_moves_for_snake


def info():
    """
    This function is called once at the start of the game.
    It's an opportunity to personalize your snake.
    """
    print("info")
    return {
        "apiversion": "1",
        "author": "gemini-2.5-pro",
        "color": "#00FF00",  # A nice green
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    """
    This function is called once at the start of every game.
    """
    print("GAME START")

def end(game_state: typing.Dict):
    """
    This function is called when a game is over.
    """
    print("GAME OVER\n")



def move(game_state: typing.Dict) -> typing.Dict:
    """
    This function is called on every turn. It uses iterative deepening
    to find the best move within the time limit.
    """
    start_time = time.time()
    time_limit = 0.45  # 450ms, leaving a 50ms buffer

    print(f"MOVE {game_state['turn']}:")

    # Opening book: for the first 2 turns, move towards the center
    if game_state['turn'] < 2:
        print("Using opening book: moving to center")
        try:
            gs = GameState(game_state)
            my_snake_data = game_state['you']
            safe_moves = get_safe_moves_for_snake(my_snake_data, gs)

            if safe_moves:
                my_head = game_state['you']['head']
                center_x, center_y = game_state['board']['width'] // 2, game_state['board']['height'] // 2
                
                dx = center_x - my_head['x']
                dy = center_y - my_head['y']
                
                prefs = []
                if abs(dx) > abs(dy):
                    if dx > 0: prefs.append('right')
                    elif dx < 0: prefs.append('left')
                    if dy > 0: prefs.append('up')
                    elif dy < 0: prefs.append('down')
                else:
                    if dy > 0: prefs.append('up')
                    elif dy < 0: prefs.append('down')
                    if dx > 0: prefs.append('right')
                    elif dx < 0: prefs.append('left')

                # Add remaining moves as random fallbacks
                all_moves = ['up', 'down', 'left', 'right']
                random.shuffle(all_moves)
                for m in all_moves:
                    if m not in prefs:
                        prefs.append(m)

                for move in prefs:
                    if move in safe_moves:
                        print(f"Opening move: {move}")
                        return {"move": move}
        except Exception as e:
            print(f"Error in opening book: {e}")
            # Fall through to main logic on error
    
    best_move = "up"  # Default move in case of timeout on first iteration
    
    # Iterative deepening loop
    for depth in range(2, 20, 2): # Start with depth 2 and increase by 2
        try:
            print(f"Searching with depth: {depth}...")
            current_best_move = find_best_move_with_lookahead(game_state, depth)
            
            if current_best_move:
                best_move = current_best_move
            
            # Check time after a successful search
            elapsed_time = time.time() - start_time
            if elapsed_time > time_limit:
                print(f"Time limit reached ({elapsed_time:.2f}s). Using move from depth {depth}.")
                break
                
        except Exception as e:
            print(f"Error during search at depth {depth}: {e}")
            break # Stop searching if an error occurs

    print(f"Moving {best_move}")
    return {"move": best_move}

# Start server when run directly
if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})