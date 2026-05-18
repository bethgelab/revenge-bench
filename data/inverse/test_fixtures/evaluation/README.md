# Test Fixtures for Evaluation

This directory contains test data for the evaluation module.

## Structure

```
evaluation/
  battlesnake/
    simple_traces.json          # 5-turn trace for unit tests
    greedy_food_traces.json     # Full traces from GreedyFoodStrategy (symlink to data/traces)
    mock_perfect.py             # Strategy that matches 100%
    mock_partial.py             # Strategy that matches ~60%
    mock_crash.py               # Strategy that crashes
```

## Usage

These fixtures are loaded by `tests/evaluation/conftest.py` and available as pytest fixtures.
