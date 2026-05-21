import typing
import flood_fill

def get_head_to_head_move(game_state: typing.Dict, safe_moves: typing.List[str], potential_moves: typing.Dict) -> typing.Union[str, None]:
    """
    Determines if a head-to-head confrontation is imminent and returns the best move
    by evaluating the resulting space from aggressive or defensive maneuvers.
    Returns None if no head-to-head situation is detected.
    """
    my_head = game_state["you"]["body"][0]
    my_length = len(game_state["you"]["body"])
    opponents = game_state["board"]["snakes"]

    for opponent in opponents:
        if opponent["id"] == game_state["you"]["id"]:
            continue

        opponent_head = opponent["body"][0]
        opponent_length = len(opponent["body"])

        distance_x = abs(my_head["x"] - opponent_head["x"])
        distance_y = abs(my_head["y"] - opponent_head["y"])

        # Only trigger in a direct line-of-sight confrontation
        if (distance_x == 2 and distance_y == 0) or (distance_x == 0 and distance_y == 2):
            
            # AGGRESSIVE: We are longer
            if my_length > opponent_length:
                print(f"HEAD-TO-HEAD: Aggressive stance against smaller snake {opponent['name']}.")
                aggressive_moves = []
                if opponent_head["x"] > my_head["x"]: aggressive_moves.append("right")
                elif opponent_head["x"] < my_head["x"]: aggressive_moves.append("left")
                if opponent_head["y"] > my_head["y"]: aggressive_moves.append("up")
                elif opponent_head["y"] < my_head["y"]: aggressive_moves.append("down")

                # Filter for safe aggressive moves
                valid_aggressive_moves = [m for m in aggressive_moves if m in safe_moves]

                if valid_aggressive_moves:
                    best_move = ""
                    max_area = -1
                    for move in valid_aggressive_moves:
                        area = flood_fill.count_accessible_area(game_state, potential_moves[move])
                        if area > max_area:
                            max_area = area
                            best_move = move
                    if best_move:
                        return best_move

            # DEFENSIVE: We are shorter or equal length
            else:
                print(f"HEAD-TO-HEAD: Defensive stance against larger/equal snake {opponent['name']}.")
                defensive_moves = []
                # Moves that create distance
                if opponent_head["x"] > my_head["x"]: defensive_moves.append("left")
                elif opponent_head["x"] < my_head["x"]: defensive_moves.append("right")
                if opponent_head["y"] > my_head["y"]: defensive_moves.append("down")
                elif opponent_head["y"] < my_head["y"]: defensive_moves.append("up")

                # Add sideways moves as escape options
                if opponent_head["x"] != my_head["x"]: # Horizontal confrontation
                    defensive_moves.extend(["up", "down"])
                if opponent_head["y"] != my_head["y"]: # Vertical confrontation
                    defensive_moves.extend(["left", "right"])

                # Filter for safe defensive moves and remove duplicates
                valid_defensive_moves = list(set([m for m in defensive_moves if m in safe_moves]))

                if valid_defensive_moves:
                    best_move = ""
                    max_area = -1
                    for move in valid_defensive_moves:
                        area = flood_fill.count_accessible_area(game_state, potential_moves[move])
                        if area > max_area:
                            max_area = area
                            best_move = move
                    if best_move:
                        return best_move

    return None