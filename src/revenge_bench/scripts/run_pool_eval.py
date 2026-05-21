#!/usr/bin/env python3
"""Full-pool post-hoc evaluation for a completed InverseStrategy tournament.

Takes a completed tournament directory and a directory of opponent strategies.
For each round's submitted learner code and each opponent in the pool:

  1. **Simulation** (reuses pipeline code):
     Runs BattleSnake games (target vs opponent) in Docker using the same
     arena + Static agent infra as the main pipeline.
  2. **Evaluation** (reuses pipeline code):
     Offline eval — calls learner's move() on each target state from the
     sim traces and compares to the target's actual action.

Produces a per-round × per-opponent accuracy matrix.

Usage::

    python -m revenge_bench.scripts.run_pool_eval \
        --tournament-dir logs/gpt52_halite_20260405_143000/target6403c952e9eb/seed42 \
        --pool-dir data/targets/battlesnake \
        --sims 20

    # Evaluate ALL rounds' learner code (not just last)
    python -m revenge_bench.scripts.run_pool_eval \
        --tournament-dir logs/gpt52_halite_20260405_143000/target6403c952e9eb/seed42 \
        --pool-dir data/targets/battlesnake \
        --rounds all --sims 10

    # Evaluate specific rounds
    python -m revenge_bench.scripts.run_pool_eval \
        --tournament-dir logs/gpt52_halite_20260405_143000/target6403c952e9eb/seed42 \
        --pool-dir data/targets/battlesnake \
        --rounds 3,4,5 --sims 10
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
#  Bootstrap imports in the right order to avoid the known circular import:
#  agents → player → tournaments/__init__ → pvp → agents.
# ---------------------------------------------------------------------------
import revenge_bench  # noqa: F401
import revenge_bench.tournaments.inverse_strategy  # noqa: F401
from revenge_bench.agents import get_agent
from revenge_bench.agents.player import Player
from revenge_bench.arenas import get_arena
from revenge_bench.arenas.arena import CodeArena
from revenge_bench.constants import DIR_WORK
from revenge_bench.game_context import GameContext
from revenge_bench.traces.parsers.battlesnake import (
    actions_equal,
    extract_state_action_pairs,
)
from revenge_bench.utils.log import get_logger

# ═══════════════════════════════════════════════════════════════════════════
# Tournament data helpers
# ═══════════════════════════════════════════════════════════════════════════


def load_metadata(tournament_dir: Path) -> dict:
    meta_file = tournament_dir / "metadata.json"
    if not meta_file.exists():
        raise FileNotFoundError(f"metadata.json not found in {tournament_dir}")
    return json.loads(meta_file.read_text())


def resolve_target_source(metadata: dict) -> str:
    """Get target player's source_path from tournament metadata."""
    for p in metadata.get("config", {}).get("players", []):
        if p.get("name") == "target":
            src = p.get("args", {}).get("source_path")
            if src:
                return src
    raise ValueError("Could not find target source_path in metadata")


def get_round_archives(tournament_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted list of (round_num, archive_path)."""
    rounds_dir = tournament_dir / "rounds"
    if not rounds_dir.exists():
        raise FileNotFoundError(f"No rounds directory in {tournament_dir}")
    archives = []
    for arc in sorted(rounds_dir.glob("round_*.tar.gz")):
        base = arc.name.split(".")[0]  # "round_0"
        rnum = int(base.split("_")[1])  # 0
        archives.append((rnum, arc))
    return archives


def extract_learner_code(archive: Path, round_num: int, dest_dir: Path) -> Path | None:
    """Extract learner's main.py from a round archive.  Returns path or None."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    main_py = dest_dir / "main.py"
    try:
        with tarfile.open(archive, "r:gz") as tar:
            member = tar.getmember(f"{round_num}/learner_code/workspace/main.py")
            f = tar.extractfile(member)
            if f is not None:
                main_py.write_bytes(f.read())
                return main_py
    except (KeyError, tarfile.TarError):
        pass
    return None


def discover_strategies(pool_dir: Path, game_name: str = "BattleSnake") -> list[Path]:
    """Find all valid strategy directories under pool_dir."""
    ext_map = {
        "BattleSnake": ".py",
        "CoreWar": ".red",
        "Halite": ".c",
        "HuskyBench": ".py",
    }
    ext = ext_map.get(game_name, ".py")
    strategies = []
    for entry in sorted(pool_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if any(f.suffix == ext for f in entry.iterdir() if f.is_file()):
            strategies.append(entry)
    return strategies


# ═══════════════════════════════════════════════════════════════════════════
# Arena + agent setup  (same flow as InverseStrategyTournament.__init__)
# ═══════════════════════════════════════════════════════════════════════════


def setup_arena_and_agents(
    game_config: dict,
    target_source: str,
    initial_opponent_source: str,
    output_dir: Path,
) -> tuple[CodeArena, Player, Player]:
    """Create game arena and two Static agents (target + opponent).

    Each agent gets its own Docker container (via game.get_environment),
    and strategy code is copied in during Static.__init__().
    This is the same approach as InverseStrategyTournament.get_agent().
    """
    tournament_id = f"pool_eval.{time.strftime('%y%m%d%H%M%S')}"

    config = {
        "game": game_config,
        "players": [
            {
                "agent": "static",
                "name": "target",
                "editable": False,
                "args": {"source_path": target_source},
            },
            {
                "agent": "static",
                "name": "opponent",
                "editable": False,
                "args": {"source_path": initial_opponent_source},
            },
        ],
        "prompts": {},
        "tournament": {"rounds": 0},
    }

    # Creates the game Docker container (same as pipeline)
    game: CodeArena = get_arena(
        config,
        tournament_id=tournament_id,
        local_output_dir=output_dir,
        keep_containers=True,  # keep alive for the opponent-swap loop
    )

    prompts: dict = {}

    def make_agent(agent_conf: dict) -> Player:
        """Same as InverseStrategyTournament.get_agent()."""
        env = game.get_environment(f"{game.game_id}.{agent_conf['name']}")
        ctx = GameContext(
            id=game.game_id,
            log_env=game.log_env,
            log_local=game.log_local,
            name=game.name,
            player_id=agent_conf["name"],
            prompts=prompts,
            round=1,
            rounds=0,
            working_dir=str(DIR_WORK),
        )
        return get_agent(agent_conf, ctx, env)

    target_agent = make_agent(config["players"][0])
    opponent_agent = make_agent(config["players"][1])

    return game, target_agent, opponent_agent


# ═══════════════════════════════════════════════════════════════════════════
# Simulation phase  (same as InverseStrategyTournament.run_simulation_phase)
# ═══════════════════════════════════════════════════════════════════════════


def run_sim(
    game: CodeArena,
    game_agents: list[Player],
    round_num: int,
    logger,
) -> None:
    """Run sims and copy logs to host — same as pipeline's run_simulation_phase.

    game.run_round() does:
      1. _pre_round_setup: copies agent codebases from their containers
         into the game container at /{agent.name}/
      2. execute_round: starts snake servers, runs simulations
      3. copy_logs_from_env: copies /logs/ to host
    """
    logger.info(f"Sim: {game_agents[0].name} vs {game_agents[1].name}")
    stats = game.run_round(game_agents, round_num)
    logger.info(stats)


# ═══════════════════════════════════════════════════════════════════════════
# Evaluation phase  (same as InverseStrategyTournament._process_traces)
# ═══════════════════════════════════════════════════════════════════════════


def load_learner_module(main_py: Path) -> Any | None:
    """Load learner's main.py and return its move function.

    Same logic as InverseStrategyTournament._load_learner_module.
    """
    if not main_py.exists():
        return None

    code_dir = str(main_py.parent)
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)

    spec = importlib.util.spec_from_file_location("learner_main", main_py)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        with open(os.devnull, "w") as devnull:
            old_stdout = sys.stdout
            sys.stdout = devnull
            try:
                spec.loader.exec_module(module)
            finally:
                sys.stdout = old_stdout
    except Exception as exc:
        print(f"  WARNING: Failed to import {main_py}: {exc}", file=sys.stderr)
        return None

    for attr in ("move", "choose_move"):
        if hasattr(module, attr):
            return getattr(module, attr)
    return None


def query_learner(move_func: Any, state: dict) -> str | None:
    """Call learner's move function.  Same as InverseStrategyTournament._query_learner."""
    try:
        with open(os.devnull, "w") as devnull:
            old_stdout = sys.stdout
            sys.stdout = devnull
            try:
                result = move_func(state)
            finally:
                sys.stdout = old_stdout
        if isinstance(result, dict):
            return result.get("move", "")
        return str(result) if result else None
    except Exception:
        return None


def evaluate_traces(
    move_func: Any,
    traces_dir: Path,
    target_name: str,
) -> dict[str, Any] | None:
    """Offline evaluation of learner code against sim traces.

    Same core as InverseStrategyTournament._process_traces — finds sim files,
    iterates state-action pairs, calls learner's move, compares to target.
    """
    sim_files = sorted(traces_dir.glob("sim_*.jsonl")) + sorted(
        traces_dir.glob("sim_*.json")
    )
    if not sim_files:
        return None

    total_actions = 0
    matching_actions = 0
    per_sim: list[dict] = []

    for sim_file in sim_files:
        try:
            pairs = extract_state_action_pairs(sim_file, target_name)
        except Exception:
            continue

        sim_total = 0
        sim_matching = 0

        for _turn, (target_state, target_action) in enumerate(pairs):
            learner_action = query_learner(move_func, target_state)
            if learner_action is None:
                continue
            sim_total += 1
            if actions_equal(learner_action, target_action):
                sim_matching += 1

        total_actions += sim_total
        matching_actions += sim_matching
        per_sim.append(
            {
                "file": sim_file.name,
                "total": sim_total,
                "matching": sim_matching,
                "accuracy": sim_matching / sim_total if sim_total > 0 else 0.0,
            }
        )

    if total_actions == 0:
        return None

    accuracy = matching_actions / total_actions
    sim_accs = [s["accuracy"] for s in per_sim if s["total"] > 0]

    return {
        "total_actions": total_actions,
        "matching_actions": matching_actions,
        "accuracy": accuracy,
        "mean_sim_accuracy": statistics.mean(sim_accs) if sim_accs else 0.0,
        "std_sim_accuracy": statistics.stdev(sim_accs) if len(sim_accs) > 1 else 0.0,
        "num_simulations": len(per_sim),
        "per_simulation": per_sim,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════


def run(
    tournament_dir: Path,
    pool_dir: Path,
    *,
    sims_per_opponent: int = 20,
    output_dir: Path | None = None,
    rounds: str | list[int] = "last",
) -> dict:
    """Run full-pool evaluation.

    1. Create BattleSnake arena + target/opponent Static agents (Docker).
    2. For each opponent in pool: swap opponent strategy, run sims via
       game.run_round(), collect traces.
    3. For each round's learner code: evaluate against all opponent traces.
    4. Print per-round × per-opponent accuracy matrix.
    """
    metadata = load_metadata(tournament_dir)
    target_source = resolve_target_source(metadata)
    game_config = metadata.get("config", {}).get("game", {})
    game_name = game_config.get("name", "BattleSnake")

    if game_name != "BattleSnake":
        raise ValueError(f"Only BattleSnake supported, got {game_name}")

    # Resolve relative paths
    if not Path(target_source).is_absolute():
        target_source = str(Path.cwd() / target_source)

    # Discover opponents
    opponents = discover_strategies(pool_dir, game_name)
    if not opponents:
        raise RuntimeError(f"No strategies found in {pool_dir}")

    # Round archives (skip round 0 — no learner code)
    all_archives = get_round_archives(tournament_dir)
    all_archives = [(r, a) for r, a in all_archives if r >= 1]  # always skip R0
    if not all_archives:
        raise ValueError("No rounds to evaluate")

    if rounds == "last":
        all_archives = [all_archives[-1]]
    elif rounds == "all":
        pass  # keep all
    elif isinstance(rounds, list):
        all_archives = [(r, a) for r, a in all_archives if r in rounds]
        if not all_archives:
            raise ValueError(f"None of the requested rounds {rounds} exist")

    eval_rounds = [r for r, _ in all_archives]

    if output_dir is None:
        output_dir = tournament_dir / "pool_eval"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = get_logger("pool_eval", log_path=output_dir / "pool_eval.log", emoji="📊")

    print(f"Tournament:    {tournament_dir}")
    print(f"Target:        {Path(target_source).name}")
    print(f"Pool:          {pool_dir}  ({len(opponents)} opponents)")
    print(f"Sims/opponent: {sims_per_opponent}")
    print(f"Rounds:        {eval_rounds}")
    print()

    # ──────────────────────────────────────────────────────────────────
    # Phase 1: Simulation — run target vs each opponent
    # ──────────────────────────────────────────────────────────────────
    print("=" * 60)
    print("PHASE 1: Running simulations (target vs each opponent)")
    print("=" * 60)

    # Override sims_per_round
    game_config = dict(game_config)
    game_config["sims_per_round"] = sims_per_opponent

    # Create arena + agents using pipeline infrastructure
    game, target_agent, opponent_agent = setup_arena_and_agents(
        game_config,
        target_source,
        str(opponents[0]),  # initial opponent
        output_dir,
    )
    game_agents = [target_agent, opponent_agent]

    traces_root = output_dir / "traces"
    traces_root.mkdir(parents=True, exist_ok=True)

    try:
        for i, opp_path in enumerate(opponents):
            opp_name = opp_path.name
            opp_trace_dir = traces_root / opp_name

            # Skip if already cached
            if opp_trace_dir.exists() and list(opp_trace_dir.glob("sim_*")):
                n = len(list(opp_trace_dir.glob("sim_*")))
                print(f"  [{i+1}/{len(opponents)}] {opp_name:<45s}  cached ({n} sims)")
                continue

            # Swap opponent strategy (same as pipeline's _swap_opponent)
            opponent_agent.update_strategy(opp_path)

            # Use a unique round_num per opponent so logs don't collide
            round_num = i

            # Clean local round dir if it exists from a previous partial run
            round_dir = game.log_local / "rounds" / str(round_num)
            if round_dir.exists():
                shutil.rmtree(round_dir)

            t0 = time.time()
            run_sim(game, game_agents, round_num, logger)
            elapsed = time.time() - t0

            # Move sim files from rounds/{round_num}/ to per-opponent dir
            round_dir = game.log_local / "rounds" / str(round_num)
            opp_trace_dir.mkdir(parents=True, exist_ok=True)
            for sim_file in sorted(round_dir.glob("sim_*.jsonl")) + sorted(
                round_dir.glob("sim_*.json")
            ):
                shutil.move(str(sim_file), str(opp_trace_dir / sim_file.name))

            n_sims = len(list(opp_trace_dir.glob("sim_*")))
            print(
                f"  [{i+1}/{len(opponents)}] {opp_name:<45s}  {n_sims} sims  ({elapsed:.1f}s)"
            )

    finally:
        game.end(cleanup=True)

    # Collect traces
    opp_traces: dict[str, Path] = {}
    for opp_path in opponents:
        d = traces_root / opp_path.name
        if d.exists() and list(d.glob("sim_*")):
            opp_traces[opp_path.name] = d

    print(f"\nTraces collected for {len(opp_traces)} opponents\n")

    # ──────────────────────────────────────────────────────────────────
    # Phase 2: Extract learner code per round
    # ──────────────────────────────────────────────────────────────────
    tmpdir = tempfile.mkdtemp(prefix="pool_eval_code_")
    learner_code: dict[int, Path | None] = {}
    for rnum, arc in all_archives:
        dest = Path(tmpdir) / f"round_{rnum}"
        learner_code[rnum] = extract_learner_code(arc, rnum, dest)

    loaded = sum(1 for v in learner_code.values() if v is not None)
    print(f"Extracted learner code: {loaded}/{len(eval_rounds)} rounds")

    # ──────────────────────────────────────────────────────────────────
    # Phase 3: Offline evaluation  (same core as _process_traces)
    # ──────────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("PHASE 2: Offline evaluation (learner code vs target traces)")
    print("=" * 60)

    target_name = "target"
    results: dict[int, dict[str, dict]] = {}

    for rnum in eval_rounds:
        code_path = learner_code.get(rnum)
        if code_path is None:
            print(f"\n  Round {rnum}: no learner code, skipping")
            continue

        move_func = load_learner_module(code_path)
        if move_func is None:
            print(f"\n  Round {rnum}: failed to load module, skipping")
            continue

        round_results: dict[str, dict] = {}

        for opp_name, trace_dir in sorted(opp_traces.items()):
            summary = evaluate_traces(move_func, trace_dir, target_name)
            if summary is None:
                continue
            round_results[opp_name] = summary
            acc = summary["accuracy"] * 100
            n = summary["total_actions"]
            print(f"  R{rnum} vs {opp_name[:45]:<45s}  acc={acc:5.1f}%  ({n} actions)")

        # Aggregate across opponents
        accs = [v["accuracy"] for v in round_results.values() if v["total_actions"] > 0]
        r_mean = statistics.mean(accs) if accs else 0.0
        r_std = statistics.stdev(accs) if len(accs) > 1 else 0.0
        round_results["__aggregate__"] = {
            "mean_accuracy": r_mean,
            "std_accuracy": r_std,
            "n_opponents": len(accs),
        }
        results[rnum] = round_results
        print(f"  R{rnum} MEAN: {r_mean:.1%} ± {r_std:.1%}  ({len(accs)} opponents)\n")

        # Clean module to avoid cross-round contamination
        if "learner_main" in sys.modules:
            del sys.modules["learner_main"]

    # ──────────────────────────────────────────────────────────────────
    # Phase 4: Save + print summary
    # ──────────────────────────────────────────────────────────────────
    full_results = {
        "tournament_dir": str(tournament_dir),
        "target": target_source,
        "pool_dir": str(pool_dir),
        "sims_per_opponent": sims_per_opponent,
        "eval_rounds": eval_rounds,
        "n_opponents": len(opp_traces),
        "results": {str(r): rr for r, rr in results.items()},
    }

    out_file = output_dir / "pool_eval_results.json"
    out_file.write_text(json.dumps(full_results, indent=2))
    print(f"\nResults saved to {out_file}")

    _print_summary(results, eval_rounds, sorted(opp_traces.keys()))

    # Cleanup temp
    shutil.rmtree(tmpdir, ignore_errors=True)

    return full_results


def _print_summary(
    results: dict[int, dict[str, dict]],
    eval_rounds: list[int],
    opponent_names: list[str],
) -> None:
    print("\n" + "=" * 70)
    print("FULL-POOL EVALUATION SUMMARY")
    print("=" * 70)

    if not opponent_names:
        print("No results.")
        return

    max_name = 40
    header = f"{'Opponent':<{max_name}s}"
    for r in eval_rounds:
        header += f"  R{r:>2d}"
    header += "  Mean"
    print(header)
    print("-" * len(header))

    for opp in opponent_names:
        trunc = opp[:max_name]
        row = f"{trunc:<{max_name}s}"
        accs = []
        for r in eval_rounds:
            entry = results.get(r, {}).get(opp)
            if entry and entry.get("total_actions", 0) > 0:
                acc = entry["accuracy"] * 100
                accs.append(acc)
                row += f"  {acc:5.1f}"
            else:
                row += "     -"
        if accs:
            row += f"  {statistics.mean(accs):5.1f}"
        else:
            row += "     -"
        print(row)

    print("-" * len(header))
    row = f"{'MEAN':<{max_name}s}"
    all_means = []
    for r in eval_rounds:
        agg = results.get(r, {}).get("__aggregate__", {})
        m = agg.get("mean_accuracy", 0)
        n = agg.get("n_opponents", 0)
        if n > 0:
            row += f"  {m * 100:5.1f}"
            all_means.append(m * 100)
        else:
            row += "     -"
    if all_means:
        row += f"  {statistics.mean(all_means):5.1f}"
    print(row)
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Run full-pool evaluation: Docker sims + offline eval.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--tournament-dir",
        "-t",
        type=Path,
        required=True,
        help="Tournament player directory (e.g. .../000_claude_sonnet4).",
    )
    parser.add_argument(
        "--pool-dir",
        "-p",
        type=Path,
        required=True,
        help="Directory of opponent strategies (each subdir has main.py).",
    )
    parser.add_argument(
        "--sims",
        "-s",
        type=int,
        default=20,
        help="Number of simulations per opponent (default: 20).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Output directory.  Default: <tournament_dir>/pool_eval.",
    )
    parser.add_argument(
        "--rounds",
        type=str,
        default="last",
        help="Which rounds to evaluate: 'last' (default), 'all', or comma-separated (e.g. '1,3,5').",
    )
    args = parser.parse_args()

    round_list: str | list[int] = args.rounds
    if round_list not in ("last", "all"):
        round_list = [int(x.strip()) for x in args.rounds.split(",")]

    run(
        tournament_dir=args.tournament_dir,
        pool_dir=args.pool_dir,
        sims_per_opponent=args.sims,
        output_dir=args.output_dir,
        rounds=round_list,
    )


if __name__ == "__main__":
    main()
