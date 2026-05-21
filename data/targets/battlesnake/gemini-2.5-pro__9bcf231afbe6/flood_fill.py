def flood_fill(start_pos: typing.Dict, board_width: int, board_height: int, obstacles: set) -> int:
    """
    Performs a flood fill to count the number of reachable squares from a starting position.
    """
    if (start_pos["x"], start_pos["y"]) in obstacles:
        return 0

    count = 0
    queue = [start_pos]
    visited = {(start_pos["x"], start_pos["y"])}

    while queue:
        current_pos = queue.pop(0)
        count += 1

        # Explore neighbors
        for move_offset in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            next_pos = {"x": current_pos["x"] + move_offset[0], "y": current_pos["y"] + move_offset[1]}

            if (
                0 <= next_pos["x"] < board_width and
                0 <= next_pos["y"] < board_height and
                (next_pos["x"], next_pos["y"]) not in obstacles and
                (next_pos["x"], next_pos["y"]) not in visited
            ):
                visited.add((next_pos["x"], next_pos["y"]))
                queue.append(next_pos)

    return count