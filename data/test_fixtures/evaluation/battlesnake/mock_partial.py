"""
Partial match strategy for testing.

Matches ~60% of simple_traces.json actions.
Expected mean distance: 0.4 (2/5 actions differ)

Matching turns: 0, 1, 4
Mismatching turns: 2, 3 (goes right instead of left)
"""


def move(game_state):
    """Partial match - gets some right, some wrong."""
    head = game_state["you"]["head"]
    x, y = head["x"], head["y"]
    
    # Matches 3/5 actions from simple_traces
    if y < 7:
        return {"move": "up"}  # Correct for turns 0, 1
    elif x > 3:
        return {"move": "right"}  # Wrong for turns 2, 3 (should be left)
    else:
        return {"move": "right"}  # Correct for turn 4
