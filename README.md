# RevengeBench

Reverse-engineering code-space policies from behavioral experiments.

RevengeBench poses an inverse problem in code-space: given only behavioral
traces of an opaque target agent acting in a programming-game arena, can a
learner reconstruct a runnable program that reproduces the target's behavior?
The benchmark is built on **75 LLM-generated, Elo-calibrated target policies**
across five arenas: BattleSnake, Halite, HuskyBench, RoboCode, and RobotRumble.

The protocol pairs **passive observation with constrained active intervention**.
The learner watches the hidden target play sampled opponents and may author
*probe opponents*: runnable policies whose interaction with the target induces
new trajectories. A probe acts only through the normal gameplay channel and has
no privileged access to target source or internal state. The learner submits one
executable hypothesis, which is scored by action-distance on held-out target
states and by downstream player-versus-player tournaments.

This public release keeps upstream CodeClash as a git submodule and places the
RevengeBench-specific package in `src/revenge_bench`.

## Layout

```text
revenge-bench/
├── vendor/codeclash/          # Upstream CodeClash submodule
├── src/revenge_bench/         # RevengeBench package
│   ├── arenas/                # Release arena wrappers/extensions
│   ├── tournaments/           # Inverse-strategy, Forward-PvP, and BPI tournaments
│   ├── agents/                # LLM agent wrappers
│   ├── traces/                # Per-arena trace parsers
│   └── scripts/               # Importable pipeline utilities
├── configs/
│   ├── inverse/pool/          # Main model x arena configs
│   ├── inverse/conditions/    # Public optional conditions: no-probe, NL observation
│   ├── inverse/baselines/     # Public baselines, including BPI
│   ├── inverse/prompts/       # Runtime prompt templates
│   └── forward_pvp/           # Forward-PvP configs
├── data/inverse/targets/      # Target policy pools
├── scripts/                   # Runtime and evaluation entry points
├── tools/codeclash_strategies/ # Optional target-pool generation tooling
├── tests/
└── main.py                    # Compatibility entry point
```

## Installation

```bash
git clone --recurse-submodules <repo-url> revenge-bench
cd revenge-bench
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e .
```

If you cloned without submodules:

```bash
git submodule update --init --recursive
```

You also need Docker, or Singularity/Apptainer with `CODECLASH_RUNTIME` set.
Copy `.env.example` to `.env` and fill in the API keys for the LLM providers
you plan to use.

## Running The Benchmark

Main pool run:

```bash
bash scripts/inverse/run_pool.sh --seeds "42"
```

This iterates over `configs/inverse/pool/<model>/<model>_<game>.yaml`.
Useful runner flags include `--dry-run`, `--resume`, `--parallel N`,
`--configs "name_a name_b"`, and `--config-dir <dir>`.

Public optional conditions and baselines use the same runner:

```bash
bash scripts/inverse/run_no_probe.sh --seeds "42"
bash scripts/inverse/run_nl_observation.sh --seeds "42"
bash scripts/inverse/run_bpi.sh --seeds "42"
```

Forward-PvP runs use the curated configs under `configs/forward_pvp/`:

```bash
bash scripts/forward_pvp/run_forward_pvp.sh \
    --challengers "gpt5 gpt5-mini gpt-oss-120b grok-4.1-fast kimi-k2.6 deepseek-v3.2"
```

## Optional Tracks

The main benchmark condition is active inverse-strategy recovery with probes.
The public release also includes:

- `configs/inverse/conditions/no_probe/`: trace-only recovery with active probes disabled.
- `configs/inverse/conditions/nl_observation/`: recovery from LLM-generated natural-language summaries of traces.
- `configs/inverse/baselines/bpi/`: Bayesian Program Inference baseline configs.
- `configs/forward_pvp/`: downstream PvP configs comparing blind, recovered, and oracle opponent intelligence.

Paper-only plotting, history-compaction sweeps, reset-memory sweeps, and probe
prompt ablation suites are intentionally not part of this release package.

## Adding Target Policies

Create a directory under `data/inverse/targets/<arena>/<policy_name>/` with a
`main.py` implementing the arena's player API. See the existing target pools
for examples.

Optional CodeClash target-pool generation helpers live under
`tools/codeclash_strategies/`. They can download CodeClash viewer artifacts,
extract runnable strategies, validate them, and run Elo selection:

```bash
bash tools/codeclash_strategies/build_pool.sh --game BattleSnake --count 40
```

## Relationship To CodeClash

RevengeBench started from CodeClash and still relies on CodeClash's arena and
execution abstractions. The upstream CodeClash source is preserved as a
submodule in `vendor/codeclash`; RevengeBench-specific code lives in
`src/revenge_bench` so the benchmark can evolve without modifying the vendored
upstream tree.

## Citation

{Placeholder}

## License

This repository is released under the MIT License. See `LICENSE` for details.
