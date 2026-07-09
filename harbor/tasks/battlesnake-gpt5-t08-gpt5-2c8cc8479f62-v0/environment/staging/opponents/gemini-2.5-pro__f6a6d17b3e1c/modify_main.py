import sys

with open('main.py', 'r') as f:
    lines = f.readlines()

new_code = """
    # Step 4.1: Prevent head-to-head collisions with larger/equal snakes
    my_length = game_state['you']['length']
    for snake in opponents:
        if snake['id'] != game_state['you']['id']:
            if len(snake['body']) >= my_length:
                opponent_head = snake['body'][0]
                # up
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] + 1) - opponent_head['y']) < 2:
                    is_move_safe['up'] = False
                # down
                if abs(my_head['x'] - opponent_head['x']) + abs((my_head['y'] - 1) - opponent_head['y']) < 2:
                    is_move_safe['down'] = False
                # left
                if abs((my_head['x'] - 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) < 2:
                    is_move_safe['left'] = False
                # right
                if abs((my_head['x'] + 1) - opponent_head['x']) + abs(my_head['y'] - opponent_head['y']) < 2:
                    is_move_safe['right'] = False
"""

# Find the line index to insert after
insert_index = -1
for i, line in enumerate(lines):
    if "Step 4: Prevent your Battlesnake from colliding with other Battlesnakes" in line:
        insert_index = i
        break

if insert_index != -1:
    # dedent the new_code block
    import textwrap
    # split into lines, dedent, and then add 4 spaces to each line
    dedented_code = textwrap.dedent(new_code).strip()
    indented_code_lines = ["    " + line for line in dedented_code.split('\\n')]
    final_code_to_insert = "\\n".join(indented_code_lines) + "\\n"
    lines.insert(insert_index + 1, final_code_to_insert)


with open('main.py', 'w') as f:
    f.writelines(lines)