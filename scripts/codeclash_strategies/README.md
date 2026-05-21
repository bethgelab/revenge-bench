# CodeClash Strategy Pipeline

Download, extract, and build target strategy pools from [viewer.codeclash.ai](https://viewer.codeclash.ai).

## Quick Start

```bash
# Run from repo root — full pipeline in one command
bash scripts/codeclash_strategies/build_pool.sh --game BattleSnake --count 40

# Skip Elo tournament (just validate + select)
bash scripts/codeclash_strategies/build_pool.sh --game BattleSnake --skip-elo

# Resume Elo only (pool already populated)
bash scripts/codeclash_strategies/build_pool.sh --game BattleSnake --elo-only

# Dry-run
bash scripts/codeclash_strategies/build_pool.sh --game BattleSnake --dry-run
```

## End-to-End Pipeline

```
 Step 0: Download               download.py
 Step 1: Extract                 extract.py
 Step 2: Hard filters            validate_strategies.py          ─┐
 Step 3: Dedup + select + valid  select_candidates.py --populate  │ build_pool.sh
 Step 4: Elo tournament          elo_tournament.py               ─┘
 Step 5: Post-hoc repair         fix_pools.py (manual, if needed)
 Step 6: Target selection        select_targets.py (Elo-stratified subset)
```

Steps 2–4 are automated by `build_pool.sh`. Step 3 includes automatic
validation (static analysis + Docker self-play) during population — broken
strategies are replaced with spares before the Elo tournament runs.

Step 5 (`fix_pools.py`) is a **manual** repair tool for existing pools.
Run it only if broken strategies are discovered after the initial build.

### Running each step individually

```bash
# Run from repo root

# 0. Download artifacts from an index page
uv run python -m revenge_bench.scripts.codeclash_strategies.download --index path/to/index.html
# Downloads to: data/codeclash_html/

# 1. Extract strategies from downloaded artifacts
uv run python -m revenge_bench.scripts.codeclash_strategies.extract
# Reads from: data/codeclash_html/
# Writes to:  data/extracted_strategies/

# 2. Validate (Round 1: structural hard filters)
uv run python -m revenge_bench.scripts.codeclash_strategies.validate_strategies --game BattleSnake

# 3. Select candidates (Round 2: dedup + complexity + sampling + validation)
#    --populate copies to pool, validates via static+Docker, backfills broken
uv run python -m revenge_bench.scripts.codeclash_strategies.select_candidates --game BattleSnake \
    --count 40 --populate data/targets/battlesnake

# 4. Elo tournament (Round 3: Swiss-system, assigns elo_tier)
uv run python -m revenge_bench.scripts.codeclash_strategies.elo_tournament \
    --pool data/targets/battlesnake --game BattleSnake \
    --rounds 15 --sims 10 --output logs/elo/BattleSnake

# 5. Post-hoc repair (manual — only if broken strategies found after build)
uv run python -m revenge_bench.scripts.codeclash_strategies.fix_pools \
    --games HuskyBench CoreWar RobotRumble  # fix multiple games at once
uv run python -m revenge_bench.scripts.codeclash_strategies.fix_pools \
    --games HuskyBench --dry-run            # preview without changing anything
```

## Step Details

### 0. Download (`download.py`)
Fetches HTML tournament artifacts from viewer.codeclash.ai given an index page.

### 1. Extract (`extract.py`)
Parses downloaded HTML to extract per-model strategy source files into
`data/extracted_strategies/{Game}/{tournament}/final/{model}/`.

### 2. Validate (`validate_strategies.py`)
Round 1 hard filters — fast offline checks (no simulation):
- File exists, minimum lines, valid syntax, required handlers, entrypoint
- Game-agnostic: each game registers a validator subclass

### 3. Select + Validate (`select_candidates.py`)
Round 2 — dedup, score, sample, and validate:
- **Deduplication**: Greedy cosine similarity (threshold 0.997) on AST feature vectors
- **Complexity scoring**: Composite 0–100 score (LOC, functions, nesting, branches, algorithms, data structures)
- **Stratified sampling**: Round-robin across (model × complexity tier) buckets
- **Validation** (when `--populate` is used): Two-phase check on the populated pool:
  - *Phase 1 — Static analysis*: Game-specific checks (e.g., HuskyBench: required abstract methods, bad imports; RobotRumble: stdlib global redeclaration)
  - *Phase 2 — Docker self-play*: Runs each strategy against itself in Docker; checks `valid_submit` (BattleSnake & CoreWar only — other games have unreliable Docker signals)
  - Broken strategies are automatically replaced with the next-best spare from the deduped pool
- **Output**: Copies selected strategies + saves `selection_report.json`

### 4. Elo Tournament (`elo_tournament.py`)
Round 3 — Swiss-system Elo to rank strategies by actual game strength:
- 15 rounds of Swiss pairings, 10 sims per match
- Writes `elo`, `elo_rank`, `elo_tier` (hard/medium/easy) into each strategy's `provenance.json`
- Resumable via `elo_state.json`

### 5. Post-hoc Repair (`fix_pools.py`) — Manual
Repairs an existing pool without re-running the full pipeline:
- Re-validates the pool using the same static + Docker checks from Step 3
- Removes broken strategies and picks replacements from spares in `selection_report.json`
- Validates replacements before adding them; updates the selection report
- **When to use**: Only if broken strategies are discovered after the initial build (e.g., via a cross-game audit). Not needed for fresh builds — Step 3 handles validation automatically.

### 6. Target Selection (`select_targets.py`)
Selects a deterministic subset of strategies as experiment targets, stratified by Elo tier:
- Reads `elo_tier` (easy/medium/hard) from each strategy's `provenance.json`
- Sorts each tier alphabetically by directory name, takes the first N per tier
- Symlinks selected strategies into `data/targets_selected/<game>/`
- The full pool in `data/targets/<game>/` remains available as the opponent pool

```bash
# Select 5 per Elo tier for all games (default: 15 targets per game)
uv run python -m revenge_bench.scripts.select_targets

# Custom count or specific games
uv run python -m revenge_bench.scripts.select_targets --per-tier 3 --games battlesnake halite

# Preview without creating symlinks
uv run python -m revenge_bench.scripts.select_targets --dry-run
```

See [FILTERING.md](FILTERING.md) for algorithm details.

## Output Structure

```
data/
├── codeclash_html/              # Step 0: Downloaded HTML files
├── extracted_strategies/         # Step 1: Extracted code (git-ignored)
│   └── BattleSnake/
│       └── {tournament}/final/{model}/
├── targets/                      # Steps 2–4: Selected + rated pool (40 per game)
│   └── battlesnake/
│       ├── selection_report.json # Selection report (includes spares for fix_pools)
│       └── {model}__{hash}/
│           ├── main.py           # Strategy code (+ aux files)
│           └── provenance.json   # Source metadata + complexity + Elo
└── targets_selected/             # Step 6: Elo-stratified target subset (symlinks)
    └── battlesnake/
        └── {model}__{hash} -> ../../targets/battlesnake/{model}__{hash}

logs/elo/
└── BattleSnake/
    ├── elo_rankings.json         # Final rankings
    ├── elo_state.json            # Resumable state
    └── matches/                  # Per-round match logs
```

## Source

Download and extract scripts are adapted from [codeclash_viewer](https://github.com/your-org/codeclash_viewer).
