# Test Fixtures for Traces Module

This directory contains test data for trace parsing.

## Structure

```
traces/
  battlesnake/
    short_game.jsonl        # 5-turn game for basic parsing tests
    draw_game.jsonl         # Game ending in a draw
    long_game.jsonl         # Longer game (20+ turns) for stress testing
  robotrumble/
    (future)
```

## BattleSnake JSONL Format

Each line is a JSON object:
- Line 1: Game metadata (id, ruleset, map, timeout)
- Lines 2..N-1: Turn records (game, turn, board, you)
- Line N: Results (winnerId, winnerName, isDraw)

## Usage

These fixtures are loaded by `tests/traces/conftest.py` and available as pytest fixtures.
