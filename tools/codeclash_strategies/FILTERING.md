# Strategy Filtering Pipeline

A three-stage pipeline that takes ~15,000 raw LLM-generated strategy files across 6 games, filters out broken code, deduplicates near-clones, scores complexity, and selects 40 diverse strategies per game with calibrated Elo ratings.

## Corpus Overview

**Source:** 1,901 tournament HTMLs from CodeClash, covering 8 LLMs and 6 competitive-programming games.

| Game | Language | HTMLs | Strategy Files | Round-1 Survivors | Unique Clusters | Selected |
|------|----------|-------|---------------|-------------------|----------------|----------|
| BattleSnake | Python | 289 | 4,372 | 438 | 116 | 40 |
| CoreWar | Redcode | 306 | 433 | 509 | 85 | 40 |
| Halite | C | 328 | 1,743 | 622 | 330 | 40 |
| HuskyBench | Python | 273 | 3,064 | 477 | 120 | 40 |
| RoboCode | Java | 280 | 1,676 | 522 | 292 | 40 |
| RobotRumble | JavaScript | 425 | 3,603 | 746 | 309 | 40 |
| **Total** | | **1,901** | **14,891** | **3,314** | **1,242** | **240** |

**Source models:** cs4-20250514, cs4-5-20250929, gemini-2.5-pro, gpt5, gpt5-mini, grok-code-fast-1, o3, qwen3-coder-plus-2025-09-23

---

## Pipeline

```
  Raw strategies (14,891)
          │
  ┌───────▼────────┐
  │ Stage 1: Hard   │  validate_strategies.py
  │ Filters         │  6 structural checks
  └───────┬────────┘
          │  3,314 survivors
  ┌───────▼────────┐
  │ Stage 2: Dedup  │  select_candidates.py
  │ + Score + Sample│  4 phases
  └───────┬────────┘
          │  240 candidates (40 per game)
  ┌───────▼────────┐
  │ Stage 3: Elo    │  elo_tournament.py
  │ Tournament      │  Swiss-system
  └───────┬────────┘
          │  Final pools with Elo ratings
          ▼
```

All scripts are **game-agnostic**: each game registers a validator and feature-extractor subclass.

---

## Stage 1 — Hard Filters (`validate_strategies.py`)

Discards strategies that are structurally broken — no simulation needed.

```bash
uv run python tools/codeclash_strategies/validate_strategies.py --game BattleSnake
```

### Checks

| # | Check | Description |
|---|-------|-------------|
| 1 | `main_file_exists` | Submission file is present (e.g. `main.py`, `main.c`, `MyRobot.java`) |
| 2 | `min_lines` | File has ≥ N lines of code (game-specific threshold) |
| 3 | `syntax_valid` | File parses without errors (`ast.parse` for Python, brace-balance for C/Java/JS) |
| 4 | `has_handlers` | Required functions/patterns are defined (e.g. `info`, `start`, `end`, `move`) |
| 5 | `has_entrypoint` | Runtime entrypoint exists (e.g. `if __name__ == "__main__"`) |
| 6 | `game_specific` | Optional per-game checks |

All checks must pass. Discovery supports both extracted (`{Game}/{tournament}/final/{model}/`) and pool (`{model}__{hash}/`) directory layouts.

---

## Stage 2 — Dedup + Score + Sample (`select_candidates.py`)

Selects ~40 candidates per game that are structurally diverse, span a range of complexities, and represent all source models.

```bash
uv run python tools/codeclash_strategies/select_candidates.py --game BattleSnake \
    --count 40 --populate data/inverse/targets/battlesnake
```

### Phase 1 — Feature Extraction (per-game methods)

Each strategy is parsed into a feature vector for cosine-similarity comparison.

#### Python games (BattleSnake, HuskyBench) — AST features

Features are extracted via `ast.parse` into a ~100-dimensional vector:

| Feature Group | Dims | Description |
|---------------|------|-------------|
| AST node distribution | ~40 | Count of each `ast.*` node type |
| Function signatures | ~10 | Functions binned by argument count |
| Call targets | ~30 | Direct function calls by name |
| Control flow | 5 | `if`, `for`, `while`, `return`, `try` counts |
| Algorithm patterns | 17 | Binary flags (`flood_fill`, `bfs`, `a_star`, `dijkstra`, `minimax`, …) |
| Size | 1 | Lines of code |

#### Non-Python games (CoreWar, Halite, RoboCode, RobotRumble) — Keywords + Shingles

These use **binary keyword presence** (language-specific keywords and API patterns) combined with **feature-hashed text shingles**:

1. Normalize source lines (strip whitespace, remove comments)
2. Create sliding windows of 3 consecutive non-empty lines
3. Hash each window (MD5) into one of **64 fixed buckets**
4. Count bucket hits → dense 64-dimensional vector

Keywords are binarized (0/1) for the similarity vector so that code structure (shingles) drives similarity rather than keyword frequency. Raw counts are preserved separately for complexity scoring.

| Game | Feature type | Median sim | p95 sim |
|------|-------------|-----------|---------|
| BattleSnake | Python AST | 0.991 | 0.998 |
| HuskyBench | Python AST | 0.988 | 0.996 |
| CoreWar | Redcode ops + shingles | 0.335 | 0.505 |
| Halite | Binary kw + shingles | 0.722 | 0.812 |
| RoboCode | Binary kw + shingles | 0.738 | 0.810 |
| RobotRumble | Binary kw + shingles | 0.590 | 0.763 |

### Phase 2 — Fuzzy Deduplication

Greedy representative selection with cosine similarity:

```
1. Sort strategies by complexity score (descending)
2. For each strategy s:
     If cosine_sim(s, any representative) ≥ threshold → assign to cluster
     Else → s becomes a new representative
3. Output: one representative per cluster
```

The threshold is **auto-calibrated** per game at the **95th percentile** of sampled pairwise similarities (up to 2,000 random pairs). This adapts to each game's feature-space geometry — Python/AST games calibrate to ~0.997, while C/Java/JS games calibrate to 0.50–0.81.

| Game | Auto threshold | Survivors | Clusters | Dedup % |
|------|---------------|-----------|----------|---------|
| BattleSnake | 0.9972 | 438 | 116 | 74% |
| CoreWar | 0.5045 | 509 | 85 | 83% |
| Halite | 0.8115 | 622 | 330 | 47% |
| HuskyBench | 0.9953 | 477 | 120 | 75% |
| RoboCode | 0.8095 | 522 | 292 | 44% |
| RobotRumble | 0.7634 | 746 | 309 | 59% |

### Phase 3 — Complexity Scoring

Each representative receives a composite complexity score (0–100) as a difficulty proxy. For Python games, the scoring formula is:

$$
\text{score} = \min\!\Bigl(
  \underbrace{\min\!\bigl(\tfrac{\text{LOC}}{6},\, 25\bigr)}_{\text{size}}
+ \underbrace{\min\!\bigl(\tfrac{f}{0.8},\, 20\bigr)}_{\text{functions}}
+ \underbrace{\min\!\bigl(\tfrac{d}{2},\, 15\bigr)}_{\text{nesting}}
+ \underbrace{\min\!\bigl(\tfrac{b}{2},\, 15\bigr)}_{\text{branching}}
+ \underbrace{\min\!\bigl(2a,\, 15\bigr)}_{\text{algorithms}}
+ \underbrace{\min\!\bigl(2s,\, 10\bigr)}_{\text{data structures}},\;\; 100 \Bigr)
$$

Components: LOC, function count ($f$), max nesting depth ($d$), branch count ($b$), weighted algorithm patterns ($a$), and data-structure diversity ($s$). Each is individually capped.

Strategies are assigned to complexity tiers by percentile rank:
- **Low:** ≤ 33rd percentile
- **Medium:** 33rd–67th percentile
- **High:** ≥ 67th percentile

### Phase 4 — Model-diverse Stratified Sampling

Round-robin selection across (model × tier) buckets:

```
1. Group representatives into buckets keyed by (model, tier)
2. Shuffle within each bucket (seeded RNG)
3. Cycle: tiers (low → med → high), models alphabetically
4. Pop one strategy per bucket per sweep until target count reached
```

This guarantees model diversity, difficulty spread, and deterministic selection.

**Output per strategy:** `main.*` (source) + `provenance.json` (model, tournament, complexity score, tier, breakdown).

### Phase 5 — Pool Validation (automatic during `--populate`)

After copying selected strategies to the pool, a two-phase validation gate removes broken code and backfills from spares:

**Phase 1 — Static analysis** (all games, instant):
Game-specific AST/regex checks that catch structural problems without simulation:

| Game | Check | Description |
|------|-------|-------------|
| HuskyBench | Required methods | `SimplePlayer` must implement 5 abstract `Bot` methods: `on_start`, `on_round_start`, `get_action`, `on_end_round`, `on_end_game` |
| HuskyBench | Bad imports | Rejects `from hand_evaluator import ...` (unavailable in runtime) |
| HuskyBench | Class name | Must define `SimplePlayer` or alias one to it |
| RobotRumble | Global redef | Rejects `const`/`let` redeclaration of 14 sandbox globals (`move`, `turn`, `attackActions`, etc.) |

**Phase 2 — Docker self-play** (gated per game):
Runs each strategy against itself in the game's Docker arena. Only games with reliable `valid_submit` signals are tested:

| Game | Docker validation | Reason |
|------|------------------|--------|
| BattleSnake | ✅ Enabled | Reliable crash detection |
| CoreWar | ✅ Enabled | Reliable syntax error detection |
| HuskyBench | ❌ Disabled | Timeouts cause false positives (slow strategies ≠ broken) |
| RobotRumble | ❌ Disabled | Sandbox swallows errors → false negatives |
| Halite | ❌ Disabled | Not implemented |
| RoboCode | ❌ Disabled | Not implemented |

Broken strategies are removed and replaced with the next-best spare from the deduped pool (sorted by complexity score). Replacements undergo the same validation before being added.

### Post-hoc Repair (`fix_pools.py`) — Manual

A separate tool for repairing existing pools without re-running the full pipeline. Uses the same static validators as Phase 5 and draws replacements from the spares list in `selection_report.json`.

```bash
# Preview what would be fixed
uv run python tools/codeclash_strategies/fix_pools.py --games HuskyBench CoreWar RobotRumble --dry-run

# Apply fixes
uv run python tools/codeclash_strategies/fix_pools.py --games HuskyBench CoreWar RobotRumble
```

**When to use:** Only if broken strategies are discovered after build (e.g., from a cross-game audit or manual inspection). Fresh builds handle validation automatically during `select_candidates.py --populate`.

---

## Stage 3 — Elo Tournament (`elo_tournament.py`)

Assigns each candidate a calibrated Elo rating via head-to-head simulation using a Swiss-system tournament.

```bash
uv run python tools/codeclash_strategies/elo_tournament.py \
    --pool data/inverse/targets/battlesnake --game BattleSnake \
    --rounds 15 --sims 10 --output logs/elo/BattleSnake
```

Swiss-system pairing ($O(N)$ matches vs. $O(N^2)$ round-robin): each round pairs strategies with similar Elo, runs $K$ simulations per match, and updates ratings:

$$E_A = \frac{1}{1 + 10^{(R_B - R_A)/400}}, \quad R_A' = R_A + K \cdot (S_A - E_A)$$

After 15 rounds, assigns `elo_tier` (hard/medium/easy) into each strategy's `provenance.json`.

### Results

| Game | Matches | Time | Elo Range | Spread | Errors |
|------|---------|------|-----------|--------|--------|
| BattleSnake | 284 | 88 min | 1298–1574 | 276 | 0 |
| CoreWar | 300 | 14 min | 1389–1626 | 237 | 0 |
| Halite | 300 | 54 min | 1334–1652 | 318 | 0 |
| HuskyBench | 300 | 47 min | 1440–1525 | 85 | 0 |
| RoboCode | 300 | 44 min | 1412–1584 | 172 | 0 |
| RobotRumble | 300 | 26 min | 1365–1692 | 327 | 0 |

All 6 games: **0% error rate** across 1,784 total matches. 40 strategies per game, each with final Elo rating and tier.

### Target Selection (`select_targets.py`)

After the Elo tournament assigns tiers, `select_targets.py` picks a deterministic subset of strategies as experiment targets while keeping the full 40-strategy pool available as opponents.

```bash
# Select 5 per Elo tier for all games (15 targets per game)
uv run python scripts/inverse/select_targets.py

# Dry run
uv run python scripts/inverse/select_targets.py --dry-run
```

Selection logic:
1. Read `elo_tier` (easy/medium/hard) from each strategy's `provenance.json`
2. Sort each tier alphabetically by directory name
3. Take the first $N$ per tier (default $N=5$, configurable via `--per-tier`)
4. Create relative symlinks in `data/inverse/targets_selected/<game>/`

Old symlinks are cleaned up before each run so tier changes don't leave stale entries. Experiment configs then set `pool_dir` to the selected subset and `opponent_pool_dir` to the full pool, reducing experiment count (e.g., from 40 to 15 targets) without narrowing opponent diversity.

### Tournament features

- **Resumable:** Restart with the same command — picks up from `elo_state.json`
- **Dry-run:** `--dry-run` shows pairings without running matches
- **Per-game args:** `_GAME_ARGS` dict provides game-specific config (e.g., `nodisplay`/`nosound` for RoboCode)
- **Provenance update:** Writes `elo`, `elo_rank`, `elo_tier`, `elo_win_rate` to `provenance.json`

---

## Per-Game Fixes

### Halite — 4 strategy replacements

4 strategies failed `gcc main.c -o main.o` compilation (missing `-lm` flag or references to non-existent `hlt/hlt.h` header). Replaced with tier-matched candidates validated against the Docker arena:

| Removed | Replacement | Tier | Cause |
|---------|-------------|------|-------|
| `gemini-2.5-pro__bb71d0d06020` | `qwen3-coder-plus__eed2231c2d69` | medium | Missing `-lm` for `pow()` |
| `qwen3-coder-plus__455878a5b02f` | `qwen3-coder-plus__ecd0ae6e5654` | medium | Non-existent header |
| `qwen3-coder-plus__8702b9bc979a` | `qwen3-coder-plus__76c2ebfcd3bc` | low | Non-existent header |
| `qwen3-coder-plus__caec8fe27bbb` | `qwen3-coder-plus__a0f176397851` | high | Non-existent header |

### RoboCode — 4 strategy replacements + engine fix

**Strategy replacements:** 4 strategies failed Java compilation. Replaced with tier-matched candidates (all validated via compile + battle against `sample.Tracker`):

| Removed | Replacement | Tier | Cause |
|---------|-------------|------|-------|
| `gemini25pro__e5da7fc4da43` | `claudesonnet420250514__8a399fce4996` | low | Undefined inner classes |
| `gpt5mini__80ddae40c438` | `grokcodefast1__80d01e2ea502` | high | Double `package` declaration |
| `qwen3coderplus20250923__43243471e5a2` | `grokcodefast1__2a2abccdfd8e` | low | Extends `Robot`, calls `AdvancedRobot` methods |
| `qwen3coderplus20250923__d3696c81be95` | `grokcodefast1__e08a71d91855` | high | Ambiguous `Robot` import |

**Engine fix (robocode.py):** Robocode enforces a 32-character max package name. Agent names like `claudesonnet420250514__1993874f22ea` (35 chars) were silently rejected — the engine ran but produced empty results. 17/40 strategies exceeded the limit. Fix: `execute_round()` now uses short aliases (`p0`, `p1`) with a `_pkg_to_agent` mapping for score attribution.

---

## Data Locations

| Data | Location |
|------|----------|
| Extracted strategies | `data/inverse/extracted_strategies/{Game}/*/final/{model}/main.*` |
| Tournament HTMLs | `data/inverse/codeclash_html/completed/*.html` |
| Target pools (40 each) | `data/inverse/targets/{game}/` |
| Target subsets (symlinks) | `data/inverse/targets_selected/{game}/` |
| Selection reports | `data/inverse/targets/{game}/selection_report.json` |
| Elo rankings | `logs/elo/{Game}/elo_rankings.json` |

---

## Design Decisions

**Complexity over win rate.** Win rate from CodeClash tournaments is a poor proxy for inverse-strategy difficulty — a sophisticated A* bot may lose on timeouts while a trivial heuristic wins. Complexity scoring captures structural richness of the code an LLM must recover.

**Greedy dedup over embeddings.** No external model dependency (runs offline with `ast` + hashing), interpretable feature vectors, calibrated thresholds tuned on known near-duplicates, and $O(N \times R)$ complexity. Embedding approaches (CodeBERT, UniXcoder) add overhead without clear benefit at this scale (~500 strategies per game).

**Swiss-system over round-robin.** For $N=40$, round-robin requires $\binom{40}{2} = 780$ matches. Swiss converges to the same ranking with ~300 matches (60% fewer), ~1 hour vs. ~3 hours per game.
