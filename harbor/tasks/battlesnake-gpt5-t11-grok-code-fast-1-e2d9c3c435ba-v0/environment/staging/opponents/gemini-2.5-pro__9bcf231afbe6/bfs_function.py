def find_shortest_path(game_state: typing.Dict, start: typing.Dict, food: typing.Dict) -> typing.Optional[list]:
    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]
    obstacles = set()
    # Add all snake bodies to obstacles.
    for snake in game_state["board"]["snakes"]:
        # The tail of a snake is a special case. A simple BFS can't easily predict
        # if it will move, so for now we treat all body parts as obstacles.
        for body_part in snake["body"]:
            obstacles.add((body_part["x"], body_part["y"]))

    queue = [(start, [])]  # queue of (position, path)
    visited = {(start["x"], start["y"])}

    while queue:
        current_pos, path = queue.pop(0)

        if current_pos["x"] == food["x"] and current_pos["y"] == food["y"]:
            return path

        # Explore neighbors
        for move_name, move_offset in {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}.items():
            next_pos = {"x": current_pos["x"] + move_offset[0], "y": current_pos["y"] + move_offset[1]}

            if (
                0 <= next_pos["x"] < board_width and
                0 <= next_pos["y"] < board_height and
                (next_pos["x"], next_pos["y"]) not in obstacles and
                (next_pos["x"], next_pos["y"]) not in visited
            ):
                visited.add((next_pos["x"], next_pos["y"]))
                new_path = path + [move_name]
                queue.append((next_pos, new_path))

    return None