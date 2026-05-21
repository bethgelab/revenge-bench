"""
Crashing strategy for testing error handling.

Crashes by accessing non-existent key.
Used to verify evaluators handle runtime errors gracefully.
"""


def move(game_state):
    """Crashes by accessing non-existent key."""
    # This will raise KeyError
    return {"move": game_state["nonexistent"]["key"]}
