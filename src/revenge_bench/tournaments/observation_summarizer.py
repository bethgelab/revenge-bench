"""
Natural language observation summarizer for the inverse strategy pipeline.

When observation_mode='nl_summary', this module generates a textual description
of the target's behaviour from raw simulation traces, using a configurable LLM.
The learner then receives only this summary (no raw sim files or traces.json).
"""

import json
import logging
from pathlib import Path
from typing import Any

import litellm
import yaml

logger = logging.getLogger(__name__)

# ─── Config loading ───────────────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "inverse" / "prompts" / "summarizer"
_DEFAULT_CONFIG = _CONFIG_DIR / "default.yaml"


def _load_summarizer_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load summarizer prompts from YAML config."""
    path = config_path or _DEFAULT_CONFIG
    if not path.exists():
        logger.warning(f"Summarizer config not found at {path}, using fallback")
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


_CONFIG_CACHE: dict[str, dict[str, Any]] = {}


def _get_config(config_path: Path | None = None) -> dict[str, Any]:
    """Cached config loader."""
    key = str(config_path or _DEFAULT_CONFIG)
    if key not in _CONFIG_CACHE:
        _CONFIG_CACHE[key] = _load_summarizer_config(config_path)
    return _CONFIG_CACHE[key]


def generate_nl_observation(
    traces_json: dict[str, Any],
    sim_dir: Path,
    game_name: str,
    round_num: int,
    *,
    model_name: str = "openai/gpt-4o-mini",
    model_kwargs: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> str:
    """
    Generate a natural language summary of the target's behavior.

    Args:
        traces_json: The parsed traces.json dict (with state-action pairs).
        sim_dir: Path to the round directory containing opp_*/sim_*.* files.
        game_name: Name of the game (e.g. "BattleSnake").
        round_num: Current round number.
        model_name: LLM model for summarization.
        model_kwargs: Additional kwargs for litellm (api_base, api_key, etc.)
        config_path: Optional path to summarizer YAML config. Defaults to
            configs/inverse/prompts/summarizer/default.yaml.

    Returns:
        Natural language summary string.
    """
    cfg = _get_config(config_path)
    game_contexts = cfg.get("game_contexts", {})
    game_context = game_contexts.get(game_name, f"## Game: {game_name}\n")

    # Build observation data from traces.json
    observation_data = _format_traces_for_summarizer(traces_json, game_name)

    user_prompt_template = cfg.get("user_prompt_template", "{game_context}\n{observation_data}")
    user_prompt = user_prompt_template.format(
        game_context=game_context,
        num_sims=traces_json.get("num_simulations", "unknown"),
        observation_data=observation_data,
    )

    game_hints = cfg.get("game_hints", {}).get(game_name, "")
    system_prompt_template = cfg.get("system_prompt", "You are an expert game analyst.")
    system_prompt = system_prompt_template.format(game_hints=game_hints)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 1500,
        "temperature": 0.3,
        "drop_params": True,
    }
    if model_kwargs:
        # Support api_base, api_key, etc.
        for k, v in model_kwargs.items():
            if k not in ("model_name",):
                kwargs[k] = v

    logger.info(
        f"Generating NL observation summary for round {round_num} "
        f"using {model_name} ({game_name}, {traces_json.get('num_simulations', 0)} sims)"
    )

    try:
        resp = litellm.completion(**kwargs)
        summary = resp.choices[0].message.content
        if not summary:
            summary = "[Summarizer returned empty response]"
        logger.info(f"NL summary generated: {len(summary)} chars")
    except Exception as e:
        logger.error(f"NL summarizer failed: {e}")
        summary = (
            f"[Observation summary unavailable — summarizer error: {e}]\n\n"
            f"Round {round_num}: {traces_json.get('num_simulations', 0)} simulations "
            f"were run. Mean action distance from your current code: "
            f"{traces_json.get('mean_distance', 'N/A')}"
        )

    return summary


def _format_traces_for_summarizer(
    traces_json: dict[str, Any],
    game_name: str,
    *,
    max_chars: int | None = None,
) -> str:
    """
    Format traces.json data into a compact text block for the summarizer.

    Provides:
    1. Aggregate statistics (without per_simulation or nonzero_distances arrays).
    2. A target action frequency table from all nonzero_distance entries.
    3. A *sampled* set of compressed state → target_action pairs, dynamically
       sized to stay under *max_chars* total.
    """
    import random
    from collections import Counter

    # Per-game budget: HuskyBench states are small enough to show all examples
    if max_chars is None:
        max_chars = 40_000 if game_name == "HuskyBench" else 30_000

    # --- 1. Aggregate stats (drop bulky arrays and internal fields) ---
    skip_keys = {
        "nonzero_distances", "per_simulation", "target", "learner",
        "total_distance", "mean_distance", "mean_distance_across_sims",
        "distance_std", "distance_se", "evaluation_type",
    }
    stats = {k: v for k, v in traces_json.items() if k not in skip_keys}
    # Rename for clarity
    if "total_actions" in stats:
        stats["total_actions_observed"] = stats.pop("total_actions")
    total_nz_count = len(traces_json.get("nonzero_distances", []))
    stats["unexplained_actions"] = total_nz_count
    stats_text = json.dumps(stats, indent=2)

    # --- 2. Action frequency table ---
    nonzero = traces_json.get("nonzero_distances", [])
    total_nz = len(nonzero)

    if game_name == "Halite":
        # For Halite, show per-direction distribution instead of exact action combos
        # Actions are [[row, col, move], ...] where move: 0=STILL,1=N,2=E,3=S,4=W
        direction_names = ["STILL", "NORTH", "EAST", "SOUTH", "WEST"]
        dir_counts = Counter()
        total_cells = 0
        for e in nonzero:
            for triple in (e.get("target_action") or []):
                dir_counts[triple[2]] += 1
                total_cells += 1
        freq_lines = [
            f"### Target Move Distribution ({total_nz} turns, {total_cells} cell-moves)"
        ]
        for i, name in enumerate(direction_names):
            pct = dir_counts[i] / total_cells * 100 if total_cells else 0
            freq_lines.append(f"  {name}: {dir_counts[i]} ({pct:.1f}%)")
    else:
        target_actions = [
            json.dumps(e.get("target_action"), sort_keys=True) for e in nonzero
        ]
        action_counts = Counter(target_actions).most_common(30)
        freq_lines = [
            f"### Target Action Frequencies ({total_nz} unexplained actions)"
        ]
        for action_str, count in action_counts:
            pct = count / total_nz * 100 if total_nz else 0
            freq_lines.append(f"  {action_str}: {count} times ({pct:.1f}%)")

    header_text = "\n".join([
        "### Aggregate Statistics",
        "```json",
        stats_text,
        "```",
        "",
        "\n".join(freq_lines),
        "",
    ])

    # --- 3. Sampled state → action pairs (budget-aware) ---
    # Compress all entries first, then pick as many as fit in the budget.
    chars_budget = max_chars - len(header_text) - 200  # 200 for section header
    if chars_budget < 1000:
        chars_budget = 1000

    # Shuffle a copy and greedily fill until budget exhausted
    pool = list(nonzero)
    random.shuffle(pool)

    sample_lines: list[str] = []
    chars_used = 0
    count = 0
    for entry in pool:
        state = _compress_state(entry.get("state", {}), game_name)
        action = entry.get("target_action")
        line = (
            f"--- Example {count + 1} ---\n"
            f"State: {json.dumps(state, separators=(',', ':'))}\n"
            f"Target action: {json.dumps(action)}\n"
        )
        if chars_used + len(line) > chars_budget:
            continue  # skip large entries, keep looking for smaller ones
        sample_lines.append(line)
        chars_used += len(line)
        count += 1

    # Free the pool copy (can be hundreds of MBs for large games)
    del pool

    sample_header = (
        f"### State-Action Pairs "
        f"({count} of {total_nz} unexplained situations)"
    )

    # --- Combine ---
    parts = [
        header_text,
        sample_header,
        "\n".join(sample_lines),
    ]

    return "\n".join(parts)


# ─── Per-game state compression ──────────────────────────────────────────────

# Fields to remove from states, per game.  Keeps states compact without losing
# behaviorally-relevant information.
_STRIP_FIELDS: dict[str, set[str]] = {
    "BattleSnake": {"game", "you"},  # game=static ruleset; you=duplicates board.snakes target
    "RobotRumble": {"walls", "all_objs"},  # static grid (~18K chars)
    "Halite": {"player_names"},  # bot names leak strategy; cells handled below
}

# Fields to strip from *each snake* inside BattleSnake states.
_BATTLESNAKE_SNAKE_STRIP = {"id", "latency", "shout", "squad", "customizations"}

# Fields to strip from each unit in RobotRumble states (always "Unit"/"Soldier"/same team).
_ROBOTRUMBLE_UNIT_STRIP = {"obj_type", "type", "team"}


def _compress_state(state: Any, game_name: str) -> Any:
    """Strip redundant fields from a game state to reduce prompt size."""
    if not isinstance(state, dict):
        return state

    # Remove top-level fields
    strip = _STRIP_FIELDS.get(game_name, set())
    if strip:
        state = {k: v for k, v in state.items() if k not in strip}

    # BattleSnake: also clean up individual snake dicts
    if game_name == "BattleSnake":
        board = state.get("board")
        if isinstance(board, dict):
            snakes = board.get("snakes")
            if isinstance(snakes, list):
                board["snakes"] = [
                    {k: v for k, v in s.items() if k not in _BATTLESNAKE_SNAKE_STRIP}
                    for s in snakes
                ]

    # Halite: replace full cells grid with target's cells + opponent summary
    # Cell format: [row, col, owner, strength, production]
    # Strip owner (always == player_tag) → keep [row, col, strength, production]
    if game_name == "Halite":
        cells = state.pop("cells", [])
        if cells:
            tag = state.get("player_tag")
            my_cells = [[c[0], c[1], c[3], c[4]] for c in cells if c[2] == tag]
            opp_cells = [c for c in cells if c[2] != tag]
            state["my_cells"] = my_cells
            state["opponent_cell_count"] = len(opp_cells)
            state["opponent_total_strength"] = sum(c[3] for c in opp_cells)

    # RobotRumble: strip redundant per-unit fields (obj_type, type, team)
    if game_name == "RobotRumble":
        for key in ("my_units", "enemy_units"):
            units = state.get(key)
            if isinstance(units, list):
                state[key] = [
                    {k: v for k, v in u.items() if k not in _ROBOTRUMBLE_UNIT_STRIP}
                    for u in units
                ]

    return state
