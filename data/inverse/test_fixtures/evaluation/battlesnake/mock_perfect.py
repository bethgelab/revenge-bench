"""
Perfect match strategy for testing.

Hardcoded to match simple_traces.json exactly.
Expected distance: 0.0 (all actions match)
"""


def move(game_state):
    """Perfect match to simple_traces - hardcoded responses."""
    head = game_state["you"]["head"]
    x, y = head["x"], head["y"]
    
    # Hardcoded to match simple_traces exactly
    responses = {
        (5, 5): "up",
        (5, 6): "up", 
        (5, 7): "left",
        (4, 7): "left",
        (3, 7): "right",
    }
    
    action = responses.get((x, y), "up")
    return {"move": action}
