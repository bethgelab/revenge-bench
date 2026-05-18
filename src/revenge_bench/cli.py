import argparse
import copy
import json
import logging
import random
import statistics
import time
import traceback
from pathlib import Path

import yaml

from revenge_bench import CONFIG_DIR
from revenge_bench.constants import LOCAL_LOG_DIR
from revenge_bench.strategy_pool import StrategyPool
from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
from revenge_bench.tournaments.inverse_strategy_interventionist import (
    InverseStrategyInterventionistTournament,
)
from revenge_bench.tournaments.bayesian_program_inference import (
    BayesianProgramInferenceTournament,
)
from revenge_bench.tournaments.pvp import PvpTournament
from revenge_bench.utils.aws import is_running_in_aws_batch
from revenge_bench.utils.yaml_utils import resolve_includes

logger = logging.getLogger(__name__)


_INVERSE_AGENT_KEYS = ("inverse", "inverse_codex")


def get_tournament_class(config: dict):
    """Determine tournament type from config."""
    # Check explicit tournament type first
    tournament_type = config.get("tournament", {}).get("type", "")
    if tournament_type == "interventionist":
        return InverseStrategyInterventionistTournament
    if tournament_type == "bayesian_program_inference":
        return BayesianProgramInferenceTournament
    if tournament_type == "observational":
        return InverseStrategyTournament

    for player in config.get("players", []):
        if player.get("agent") in _INVERSE_AGENT_KEYS:
            return InverseStrategyTournament
    return PvpTournament


def get_tournament_prefix(config: dict) -> str:
    """Get prefix for output folder based on tournament type."""
    tournament_type = config.get("tournament", {}).get("type", "")
    if tournament_type == "interventionist":
        return "Interventionist"
    if tournament_type == "bayesian_program_inference":
        return "BayesianProgramInference"
    if tournament_type == "observational":
        return "Observational"
    for player in config.get("players", []):
        if player.get("agent") in _INVERSE_AGENT_KEYS:
            return "InverseStrategy"
    return "PvpTournament"


def _make_timestamp() -> str:
    if is_running_in_aws_batch():
        offset = random.randint(0, 600)
        return time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() + offset))
    return time.strftime("%Y%m%d_%H%M%S")


def _log_base() -> Path:
    """Root directory for all run logs."""
    if is_running_in_aws_batch():
        return LOCAL_LOG_DIR / "batch"
    return LOCAL_LOG_DIR


def _get_single_run_dir(config: dict, config_path: Path, timestamp: str, *, external_timestamp: bool) -> Path:
    """Build output dir for a single (non-pool) tournament run.

    External timestamp (from run_pool.sh via -t): grouped run — top-level dir
    uses the config's parent directory name so multiple configs share one parent,
    with config_stem as a sub-level below the arena.

    Self-generated timestamp (direct invocation): top-level dir uses config_stem
    directly, with no extra sub-level.
    """
    game = config["game"]["name"].lower()
    seed = config.get("tournament", {}).get("seed")
    seed_part = f"seed{seed}" if seed is not None else "seed0"

    if external_timestamp:
        group = config_path.parent.name.replace("-", "_")
        return _log_base() / f"{group}_{timestamp}" / game / config_path.stem / seed_part
    else:
        return _log_base() / f"{config_path.stem}_{timestamp}" / game / seed_part


def _get_learner_model_name(config: dict) -> str:
    """Return the short model name for the learner (last path component, no org prefix).

    For `inverse_codex`, reads `config.codex.model` since Codex configs do
    not use the mini-swe `config.model.model_name` shape.
    """
    for player in config.get("players", []):
        agent_type = player.get("agent")
        if agent_type == "inverse":
            model_name = player.get("config", {}).get("model", {}).get("model_name", "")
            if model_name:
                return model_name.split("/")[-1]
        elif agent_type == "inverse_codex":
            model_name = player.get("config", {}).get("codex", {}).get("model", "")
            if model_name:
                return model_name.split("/")[-1]
    return "unknown"


def _get_pool_parent_dir(config: dict, timestamp: str) -> Path:
    """Return the parent directory for a pool run: {log_base}/{name}_{timestamp}/

    Uses the top-level ``name`` field if set (useful for variant configs where multiple
    configs share the same model), otherwise falls back to the learner model name.
    """
    name = config.get("name") or _get_learner_model_name(config)
    return _log_base() / f"{name}_{timestamp}"


def _get_target_subdir(config: dict, target_path: Path, seed: int | str | None) -> Path:
    """Per-target run directory: {arena}/target{hash}/seed{N}.

    The hash is the part after __ in the target directory name
    (e.g. grok-code-fast-1__6403c952e9eb → target6403c952e9eb/seed42).
    """
    game = config["game"]["name"].lower()
    name = target_path.name
    target_hash = name.rsplit("__", 1)[1] if "__" in name else name
    path = Path(game) / f"target{target_hash}"
    if seed is not None:
        return path / f"seed{seed}"
    return path


def _get_player_source_path(config: dict, player_name: str) -> str | None:
    """Return the source_path for a named player, or None if not found."""
    for player in config.get("players", []):
        if player.get("name") == player_name:
            return player.get("args", {}).get("source_path")
    return None


def _override_target_source(
    config: dict,
    target_path: Path,
    *,
    opponent_path: Path | None = None,
    fixed_target: bool = False,
) -> dict:
    """Deep-copy config and override source_path for target and opponent players.

    If *opponent_path* is not given and *fixed_target* is False, the opponent
    gets the same path as the target (self-play).
    If *fixed_target* is True, the target player's source_path is left unchanged.
    If *opponent_path* is None and *fixed_target* is True, the opponent is also
    left unchanged.
    """
    cfg = copy.deepcopy(config)
    for player in cfg["players"]:
        if player.get("agent") != "static":
            continue
        if player.get("name") == "target" and not fixed_target:
            player.setdefault("args", {})["source_path"] = str(target_path)
        elif player.get("name") == "opponent" and opponent_path is not None:
            player.setdefault("args", {})["source_path"] = str(opponent_path)
        elif player.get("name") == "opponent" and not fixed_target and opponent_path is None:
            # Self-play default: opponent = target
            player.setdefault("args", {})["source_path"] = str(target_path)
    return cfg


def write_benchmark_summary(parent_dir: Path, results: list[dict], config: dict) -> Path:
    """Write benchmark_summary.json with per-target results and aggregate stats."""
    distances = [r["final_distance"] for r in results if r.get("final_distance") is not None]

    aggregate = {}
    if distances:
        aggregate = {
            "mean": round(statistics.mean(distances), 4),
            "median": round(statistics.median(distances), 4),
            "std": round(statistics.stdev(distances), 4) if len(distances) > 1 else 0.0,
            "min": round(min(distances), 4),
            "max": round(max(distances), 4),
        }

    summary = {
        "num_targets": len(results),
        "num_completed": sum(1 for r in results if r.get("status") == "completed"),
        "num_failed": sum(1 for r in results if r.get("status") == "failed"),
        "aggregate": aggregate,
        "per_target": results,
        "config": {
            "game": config.get("game", {}).get("name"),
            "rounds": config.get("tournament", {}).get("rounds"),
            "sims_per_round": config.get("game", {}).get("sims_per_round"),
        },
    }

    summary_path = parent_dir / "benchmark_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"Benchmark summary written to {summary_path}")
    return summary_path


def _run_pool_eval(tournament_dir: Path, pool_dir: Path, *, sims: int, rounds: str) -> None:
    """Run pool evaluation after a tournament, skipping if already complete."""
    results_file = tournament_dir / "pool_eval" / "pool_eval_results.json"
    if results_file.exists():
        logger.info(f"  Pool eval already complete, skipping: {tournament_dir.name}")
        return
    try:
        from revenge_bench.scripts.inverse.run_pool_eval import run as pool_eval_run

        logger.info(f"  Running pool eval: {tournament_dir.name} vs {pool_dir} (sims={sims}, rounds={rounds})")
        pool_eval_run(tournament_dir, pool_dir, sims_per_opponent=sims, rounds=rounds)
    except Exception as e:
        logger.error(f"  Pool eval FAILED for {tournament_dir.name}: {e}")


def run_strategy_pool(
    config: dict,
    pool_config: dict,
    *,
    cleanup: bool,
    timestamp: str,
    keep_containers: bool,
    resume: bool = False,
    pool_eval: bool = False,
    pool_eval_sims: int = 20,
    pool_eval_rounds: str = "last",
) -> None:
    """Run one tournament per target strategy from a pool.

    Pool config options:
        pool_dir:        Directory containing strategy subdirectories (used for targets).
        opponent_pool_dir: Optional separate directory for opponent strategies.
                         When omitted, opponents are drawn from pool_dir.
        num_targets:     Optional limit on how many targets to run (ignored when fixed_target).
        seed:            Optional seed for reproducible sampling.
        fixed_target:    If true, use the target player's source_path from config
                         instead of iterating over targets from the pool.
        target_filter:   Optional dict of provenance fields to filter targets.
                         E.g. ``{elo_tier: hard}`` or ``{model: [gpt5, o3]}``.
        opponent_filter:  Optional dict of provenance fields to filter opponents.
                         Same syntax as target_filter. In case of maching filters,
                         opponent pool will be the same as target pool to save time.
    """
    pool_dir = Path(pool_config["pool_dir"])
    opponent_pool_dir = Path(pool_config.get("opponent_pool_dir", pool_config["pool_dir"]))
    game_name = config["game"]["name"]

    # Build separate filters for targets and opponents.
    # When the keys are absent the dicts are empty → no filtering (backward-compatible).
    target_filter = pool_config.get("target_filter", {})
    opponent_filter = pool_config.get("opponent_filter", {})

    # Target pool (may have its own filter)
    target_pool = StrategyPool(pool_dir, game_name, filters=target_filter)

    # Opponent pool — use opponent_pool_dir if specified, otherwise fall back to
    # pool_dir.  Re-use target pool when both dirs and filters are identical.
    if opponent_pool_dir == pool_dir and opponent_filter == target_filter:
        opponent_pool = target_pool
    else:
        opponent_pool = StrategyPool(opponent_pool_dir, game_name, filters=opponent_filter)

    # Legacy alias kept for the rest of the function
    pool = target_pool

    fixed_target = pool_config.get("fixed_target", False)
    sampling_seed = pool_config.get("seed")
    tournament_seed = config.get("tournament", {}).get("seed")

    # --- Determine targets ---
    if fixed_target:
        # Use the target source_path from config as-is; pool is only for opponents
        target_source = _get_player_source_path(config, "target")
        if target_source is None:
            raise ValueError("strategy_pool.fixed_target is true but no target source_path found in config")
        targets = [Path(target_source)]
        logger.info(f"Strategy pool: fixed target = {targets[0].name}")
    else:
        if not pool.strategies:
            raise RuntimeError(f"No valid strategies found in {pool_dir} for {game_name}")
        target_names = pool_config.get("target_names")
        top_elo_targets = pool_config.get("top_elo_targets")
        num_targets = pool_config.get("num_targets")
        if target_names is not None:
            # Explicit list of target directory names to run
            name_set = set(target_names)
            targets = [s for s in pool.strategies if s.name in name_set]
            missing = name_set - {s.name for s in targets}
            if missing:
                logger.warning(f"target_names not found in pool: {missing}")
        elif top_elo_targets is not None:
            targets = pool.top_by_elo(top_elo_targets)
        elif num_targets is not None:
            targets = pool.sample(num_targets, seed=sampling_seed)
        else:
            targets = pool.strategies
        logger.info(f"Strategy pool: {len(targets)} targets selected from {len(pool.strategies)} available")

    if not opponent_pool.strategies:
        raise RuntimeError(
            f"No valid strategies found in {opponent_pool_dir} for {game_name} (needed for opponent pool)"
            + (f" with filters {opponent_filter}" if opponent_filter else "")
        )

    parent_dir = _get_pool_parent_dir(config, timestamp)
    parent_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    for idx, target_path in enumerate(targets):
        target_name = target_path.name
        tournament_dir = parent_dir / _get_target_subdir(config, target_path, tournament_seed)

        logger.info(f"[{idx + 1}/{len(targets)}] Running tournament with target: {target_name}")

        # --- Determine opponents ---
        opponents_per_round = config.get("tournament", {}).get("opponents_per_round", 1)
        target_resolved = target_path.resolve()
        available = [s for s in opponent_pool.strategies if s.resolve() != target_resolved]
        if not available:
            raise RuntimeError(
                f"Opponent pool contains only the target '{target_name}' — add at least one other strategy."
            )
        opponent_rng = random.Random(sampling_seed + idx if sampling_seed is not None else None)
        n_pick = min(opponents_per_round, len(available))
        opponents = opponent_rng.sample(available, n_pick)

        # --- Build config overrides ---
        target_config = _override_target_source(
            config, target_path, opponent_path=opponents[0], fixed_target=fixed_target
        )

        result: dict = {
            "index": idx,
            "target": target_name,
            "target_path": str(target_path),
            "output_dir": str(tournament_dir),
            "opponents": [str(p) for p in opponents],
            "opponents_per_round": opponents_per_round,
            "fixed_target": fixed_target,
        }

        if resume and (tournament_dir / "metadata.json").exists():
            logger.info(f"  SKIP (completed): {target_name}")
            result["status"] = "skipped"
            result["final_distance"] = None
            result["distance_history"] = {}
            results.append(result)
            continue

        try:
            tournament_class = get_tournament_class(target_config)
            tournament = tournament_class(
                target_config,
                output_dir=tournament_dir,
                cleanup=cleanup,
                keep_containers=keep_containers,
            )
            tournament.run(opponents=opponents)

            # Read distance from metadata
            metadata_file = tournament_dir / "metadata.json"
            if metadata_file.exists():
                metadata = json.loads(metadata_file.read_text())
                distance_history = metadata.get("distance_history", {})
                result["distance_history"] = distance_history
                if distance_history:
                    last_round = max(distance_history.keys(), key=int)
                    result["final_distance"] = distance_history[last_round]
                else:
                    result["final_distance"] = None
            else:
                result["final_distance"] = None
                result["distance_history"] = {}

            result["status"] = "completed"
            logger.info(f"  Target {target_name}: final distance = {result['final_distance']}")

            if pool_eval:
                _run_pool_eval(
                    tournament_dir,
                    opponent_pool_dir,
                    sims=pool_eval_sims,
                    rounds=pool_eval_rounds,
                )

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            result["traceback"] = traceback.format_exc()
            result["final_distance"] = None
            result["distance_history"] = {}
            logger.error(f"  Target {target_name} FAILED: {e}")

        results.append(result)

    summary_path = write_benchmark_summary(parent_dir, results, config)

    # Print summary to console
    completed = [r for r in results if r["status"] == "completed"]
    failed = [r for r in results if r["status"] == "failed"]
    print(f"\n{'=' * 60}")
    print(f"Benchmark complete: {len(completed)}/{len(results)} targets succeeded")
    if completed:
        distances = [r["final_distance"] for r in completed if r["final_distance"] is not None]
        if distances:
            print(f"  Mean distance: {statistics.mean(distances):.4f}")
            print(f"  Min: {min(distances):.4f}  Max: {max(distances):.4f}")
    if failed:
        print(f"  Failed targets: {', '.join(r['target'] for r in failed)}")
    print(f"  Summary: {summary_path}")
    print(f"{'=' * 60}\n")


def main(
    config_path: Path,
    *,
    cleanup: bool = False,
    timestamp: str | None = None,
    keep_containers: bool = False,
    resume: bool = False,
    pool_eval: bool = False,
    pool_eval_sims: int = 20,
    pool_eval_rounds: str = "last",
):
    yaml_content = config_path.read_text()
    preprocessed_yaml = resolve_includes(yaml_content, base_dir=CONFIG_DIR)
    config = yaml.safe_load(preprocessed_yaml)

    external_timestamp = timestamp is not None
    if not external_timestamp:
        timestamp = _make_timestamp()

    pool_config = config.get("strategy_pool")
    if pool_config and issubclass(get_tournament_class(config), InverseStrategyTournament):
        run_strategy_pool(
            config,
            pool_config,
            cleanup=cleanup,
            timestamp=timestamp,
            keep_containers=keep_containers,
            resume=resume,
            pool_eval=pool_eval,
            pool_eval_sims=pool_eval_sims,
            pool_eval_rounds=pool_eval_rounds,
        )
    else:
        full_output_dir = _get_single_run_dir(config, config_path, timestamp, external_timestamp=external_timestamp)
        if resume and (full_output_dir / "metadata.json").exists():
            logger.info(f"SKIP (completed): {full_output_dir}")
            return
        tournament_class = get_tournament_class(config)
        tournament = tournament_class(
            config,
            output_dir=full_output_dir,
            cleanup=cleanup,
            keep_containers=keep_containers,
        )
        tournament.run()


def main_cli(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="RevengeBench")
    parser.add_argument(
        "config_path",
        type=Path,
        help="Path to the config file.",
    )
    parser.add_argument(
        "-c",
        "--cleanup",
        action="store_true",
        help="If set, do not clean up the game environment after running.",
    )
    parser.add_argument(
        "-t",
        "--timestamp",
        type=str,
        help="Shared timestamp for grouping parallel runs (e.g. from run_pool.sh). Auto-generated if omitted.",
        default=None,
    )
    parser.add_argument(
        "-k",
        "--keep-containers",
        action="store_true",
        help="Do not remove containers after games/agent finish",
    )
    parser.add_argument(
        "-r",
        "--resume",
        action="store_true",
        help="Skip runs whose output directory already contains metadata.json.",
    )
    parser.add_argument(
        "--pool-eval",
        action="store_true",
        help="Run full-pool evaluation after each completed tournament.",
    )
    parser.add_argument(
        "--pool-eval-sims",
        type=int,
        default=20,
        help="Simulations per opponent in pool eval (default: 20).",
    )
    parser.add_argument(
        "--pool-eval-rounds",
        type=str,
        default="last",
        help="Which rounds to evaluate: 'last' (default), 'all', or comma-separated e.g. '1,3,5'.",
    )
    args = parser.parse_args(argv)
    main(**vars(args))


if __name__ == "__main__":
    main_cli()
