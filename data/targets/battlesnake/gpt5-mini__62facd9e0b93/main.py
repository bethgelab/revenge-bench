#!/usr/bin/env python3
# Improved Battlesnake bot with BFS and reachable-area heuristic
import random
import typing
from collections import deque

def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "gpt-5-mini",
        "color": "#888888",
        "head": "default",
        "tail": "default",
    }

def start(game_state: typing.Dict):
    print("GAME START")

def end(game_state: typing.Dict):
    print("GAME OVER\n")

def move(game_state: typing.Dict) -> typing.Dict:
    board = game_state["board"]
    width = board["width"]
    height = board["height"]

    me = game_state["you"]
    my_body = me["body"]
    my_head = my_body[0]
    my_length = me.get("length", len(my_body))

    moves = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
    coord_to_move = {v: k for k, v in moves.items()}

    # Prevent reversing into neck
    is_move_safe = {m: True for m in moves}
    if len(my_body) > 1:
        neck = my_body[1]
        if neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    # Build occupied set: mark all body segments as occupied except tails (they usually move)
    occupied = set()
    for snake in board.get("snakes", []):
        body = snake.get("body", [])
        for idx, seg in enumerate(body):
            # Skip the tail segment to allow moving into spaces where tails will vacate
            if idx == len(body) - 1:
                continue
            occupied.add((seg["x"], seg["y"]))

    # Estimate opponents' next positions (dangerous head-to-head squares)
    dangerous_positions = set()
    opponent_next = []
    for snake in board.get("snakes", []):
        if snake.get("id") == me.get("id"):
            continue
        head = snake["body"][0]
        neck = snake["body"][1] if len(snake["body"]) > 1 else None
        possible = set()
        for om, (odx, ody) in moves.items():
            # prevent backward move for opponent
            if neck:
                if neck["x"] < head["x"] and om == "left":
                    continue
                if neck["x"] > head["x"] and om == "right":
                    continue
                if neck["y"] < head["y"] and om == "down":
                    continue
                if neck["y"] > head["y"] and om == "up":
                    continue
            ox = head["x"] + odx
            oy = head["y"] + ody
            if ox < 0 or ox >= width or oy < 0 or oy >= height:
                continue
            possible.add((ox, oy))
        opponent_next.append({"positions": possible, "length": len(snake.get("body", []))})
        if len(snake.get("body", [])) >= my_length:
            dangerous_positions.update(possible)

    # Mark moves that are out of bounds, collide with occupied, or are dangerous
    for m, (dx, dy) in moves.items():
        nx = my_head["x"] + dx
        ny = my_head["y"] + dy
        if nx < 0 or nx >= width or ny < 0 or ny >= height:
            is_move_safe[m] = False
            continue
        if (nx, ny) in occupied:
            is_move_safe[m] = False
            continue
        if (nx, ny) in dangerous_positions:
            is_move_safe[m] = False
            continue

    safe_moves = [m for m, ok in is_move_safe.items() if ok]

    # If no safe moves found, pick a fallback in-bounds move that maximizes reachable area
    def reachable_area(start_coord: typing.Tuple[int, int], occ: typing.Set[typing.Tuple[int, int]], max_nodes: int = 1000) -> int:
        q = deque([start_coord])
        visited = {start_coord}
        count = 0
        while q and count < max_nodes:
            cur = q.popleft()
            count += 1
            for dx, dy in moves.values():
                nx = cur[0] + dx
                ny = cur[1] + dy
                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                c = (nx, ny)
                if c in visited or c in occ or c in dangerous_positions:
                    continue
                visited.add(c)
                q.append(c)
        return count

    if not safe_moves:
        # fallback candidates: any move that's in-bounds (even if occupied or dangerous)
        fallback_moves = []
        for m, (dx, dy) in moves.items():
            nx = my_head["x"] + dx
            ny = my_head["y"] + dy
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            fallback_moves.append(m)
        if fallback_moves:
            best_move = None
            best_area = -1
            for m in fallback_moves:
                dx, dy = moves[m]
                nx = my_head["x"] + dx
                ny = my_head["y"] + dy
                new_occ = set(occupied)
                new_occ.add((nx, ny))  # simulate occupying this square
                area = reachable_area((nx, ny), new_occ)
                if area > best_area:
                    best_area = area
                    best_move = m
            print(f"MOVE {game_state['turn']}: No safe moves, fallback {best_move} (area={best_area})")
            return {"move": best_move}
        else:
            # All moves out of bounds? pick a random direction (shouldn't normally happen)
            fallback = random.choice(list(moves.keys()))
            print(f"MOVE {game_state['turn']}: No moves available at all, random {fallback}")
            return {"move": fallback}

    # Try BFS to nearest food (multi-step path) avoiding occupied/dangerous squares
    food = board.get("food", [])
    if food:
        targets = set((f["x"], f["y"]) for f in food)
        start = (my_head["x"], my_head["y"])
        queue = deque([start])
        parents = {start: None}
        found_target = None
        while queue:
            cur = queue.popleft()
            if cur in targets:
                found_target = cur
                break
            for m, (mdx, mdy) in moves.items():
                nx = cur[0] + mdx
                ny = cur[1] + mdy
                coord = (nx, ny)
                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                if coord in parents:
                    continue
                # Avoid occupied and dangerous positions in pathfinding
                if coord in occupied:
                    continue
                if coord in dangerous_positions:
                    continue
                parents[coord] = cur
                queue.append(coord)

        if found_target:
            # Reconstruct path
            path = []
            cur = found_target
            while cur is not None:
                path.append(cur)
                cur = parents[cur]
            path.reverse()
            if len(path) >= 2:
                first_step = path[1]
                dx = first_step[0] - start[0]
                dy = first_step[1] - start[1]
                move_choice = coord_to_move.get((dx, dy))
                if move_choice and move_choice in safe_moves:
                    print(f"MOVE {game_state['turn']}: {move_choice} (path to food at {found_target})")
                    return {"move": move_choice}

    # Single-step greedy move towards nearest food (if any)
    if food and safe_moves:
        nearest = min(food, key=lambda f: abs(f["x"] - my_head["x"]) + abs(f["y"] - my_head["y"]))
        current_dist = abs(nearest["x"] - my_head["x"]) + abs(nearest["y"] - my_head["y"])
        best_move = None
        best_dist = current_dist
        for m in safe_moves:
            dx, dy = moves[m]
            nx = my_head["x"] + dx
            ny = my_head["y"] + dy
            dist = abs(nx - nearest["x"]) + abs(ny - nearest["y"])
            if dist < best_dist:
                best_dist = dist
                best_move = m
        if best_move:
            print(f"MOVE {game_state['turn']}: {best_move} (towards food at {nearest})")
            return {"move": best_move}

    # Otherwise, pick the safe move that maximizes reachable area (avoid traps) and use center tie-breaker
    best_move = None
    best_area = -1
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    def center_score(x: int, y: int) -> float:
        return (x - cx) ** 2 + (y - cy) ** 2

    for m in safe_moves:
        dx, dy = moves[m]
        nx = my_head["x"] + dx
        ny = my_head["y"] + dy
        new_occ = set(occupied)
        new_occ.add((nx, ny))
        area = reachable_area((nx, ny), new_occ)
        if area > best_area:
            best_area = area
            best_move = m
        elif area == best_area:
            # tie-breaker prefer more central
            cur_best_dx, cur_best_dy = moves[best_move]
            cur_best_x = my_head["x"] + cur_best_dx
            cur_best_y = my_head["y"] + cur_best_dy
            cand_center = center_score(nx, ny)
            best_center = center_score(cur_best_x, cur_best_y)
            if cand_center < best_center:
                best_move = m

    if best_move:
        print(f"MOVE {game_state['turn']}: {best_move} (area={best_area}, safe_moves={safe_moves})")
        return {"move": best_move}

    # As a final fallback (should not normally reach here), pick random safe move
    fallback = random.choice(safe_moves)
    print(f"MOVE {game_state['turn']}: final fallback {fallback}")
    return {"move": fallback}

if __name__ == "__main__":
    from server import run_server
    run_server({"info": info, "start": start, "move": move, "end": end})