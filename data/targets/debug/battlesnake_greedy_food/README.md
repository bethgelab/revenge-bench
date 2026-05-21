# Greedy Food Chaser

A simple, fully deterministic BattleSnake strategy for testing the inverse strategy pipeline.

## Rules (in order)

1. **Safety First**: Never move into walls, own body, or other snakes
2. **Chase Food**: Move toward the nearest food (by Manhattan distance)
3. **Tie-breaker**: When multiple moves are equally good, prefer: right > down > left > up

## Why This Target?

- **Deterministic**: No randomness, so distance 0.0 (perfect match) is achievable
- **Simple Rules**: Easy for an LLM to discover from traces
- **Realistic**: Still plays a reasonable game of BattleSnake

## Expected Behavior

Given traces from this strategy, an agent should be able to:
1. Notice the pattern of moving toward food
2. Discover the tie-breaking order from examples
3. Implement wall/body avoidance

If the inverse strategy pipeline works correctly, mean action distance should reach near 0.0 within a few rounds.
