# Target Strategies

Sample target strategies for testing the inverse strategy recovery pipeline.

## Usage

In your config YAML, specify the target:

```yaml
players:
  - agent: static
    name: target
    editable: false
    args:
      source_path: data/targets/<target_name>
```

## Adding New Targets

1. Create a directory under `data/targets/<target_name>/`
2. Add a `main.py` implementing the game's API (see game-specific docs in `data/<game>/`)
3. Add a `README.md` documenting the strategy's rules
4. (Optional) Create a test config in `configs/test/`

## Target Complexity Levels

- **Simple**: Deterministic, rule-based (easy to recover)
- **Medium**: Some lookahead or state tracking
- **Complex**: Multi-factor scoring, game tree search

Start with simple targets to validate the pipeline, then progress to complex ones.
