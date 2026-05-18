#!/usr/bin/env python3
"""Swiss-system Elo tournament for strategy pool ranking.

Runs head-to-head BattleSnake (or other game) simulations between static
strategies using the existing CodeClash PvP infrastructure, and computes
Elo ratings via Swiss-system pairing.

Swiss system: each round pairs strategies with similar Elo, so ratings
converge faster than full round-robin while requiring far fewer matches.

Usage:
    # Run Swiss Elo on the v2 pool (40 strategies, ~15 rounds)
    python scripts/inverse/revenge_bench/elo_tournament.py \
        --pool data/inverse/targets/battlesnake \
        --game BattleSnake \
        --rounds 15

    # Resume an interrupted tournament
    python scripts/inverse/revenge_bench/elo_tournament.py \
        --pool data/inverse/targets/battlesnake \
        --resume logs/elo/BattleSnake

    # Dry-run: show pairings without running simulations
    python scripts/inverse/revenge_bench/elo_tournament.py \
        --pool data/inverse/targets/battlesnake \
        --dry-run

Prerequisites:
    - Docker running (BattleSnake arena uses Docker containers)
    - BattleSnake Docker image built (revenge_bench/battlesnake)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from revenge_bench.paths import REPO_ROOT as _PROJECT_ROOT

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from revenge_bench.constants import LOCAL_LOG_DIR
from revenge_bench.tournaments.pvp import PvpTournament
from revenge_bench.utils.atomic_write import atomic_write

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Elo computation
# ---------------------------------------------------------------------------

INITIAL_ELO = 1500.0
K_FACTOR = 32.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Expected score for player A against player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    rating_a: float,
    rating_b: float,
    s_a: float,
    k: float = K_FACTOR,
) -> tuple[float, float]:
    """Update Elo ratings based on match result.

    s_a is player A's match score: 1.0 for a win, 0.0 for a loss, 0.5 for a draw.
    """
    e_a = expected_score(rating_a, rating_b)
    delta = k * (s_a - e_a)
    return rating_a + delta, rating_b - delta


# ---------------------------------------------------------------------------
# Swiss pairing
# ---------------------------------------------------------------------------


@dataclass
class StrategyInfo:
    """Tracks a strategy's Elo and match history."""

    name: str
    path: Path
    elo: float = INITIAL_ELO
    wins: int = 0
    losses: int = 0
    draws: int = 0
    matches_played: int = 0
    opponents_faced: set = field(default_factory=set)

    @property
    def win_rate(self) -> float:
        if self.matches_played == 0:
            return 0.0
        return self.wins / self.matches_played

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "elo": round(self.elo, 1),
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "matches_played": self.matches_played,
            "win_rate": round(self.win_rate, 3),
        }


def swiss_pair(
    strategies: list[StrategyInfo],
    rng: Random,
    *,
    avoid_rematches: bool = True,
) -> list[tuple[int, int]]:
    """Generate Swiss-system pairings for one round.

    Pairs strategies with similar Elo ratings. Each strategy plays at most
    once per round. If N is odd, the weakest unpaired strategy gets a bye.

    Args:
        strategies: All strategies with current Elo.
        rng: Random number generator for tie-breaking.
        avoid_rematches: Try to avoid pairing strategies that already played.

    Returns:
        List of (idx_a, idx_b) pairs into the strategies list.
    """
    n = len(strategies)
    # Sort by Elo descending, with random tie-breaking
    order = sorted(range(n), key=lambda i: (-strategies[i].elo, rng.random()))

    paired: set[int] = set()
    pairings: list[tuple[int, int]] = []

    for i in order:
        if i in paired:
            continue

        # Find the best unpaired opponent (closest Elo, preferring unplayed)
        best_j = -1
        best_score = float("inf")

        for j in order:
            if j == i or j in paired:
                continue

            elo_diff = abs(strategies[i].elo - strategies[j].elo)
            # Penalty for rematches
            rematch_penalty = 0
            if avoid_rematches and strategies[j].name in strategies[i].opponents_faced:
                rematch_penalty = 1000

            score = elo_diff + rematch_penalty
            if score < best_score:
                best_score = score
                best_j = j

        if best_j >= 0:
            pairings.append((i, best_j))
            paired.add(i)
            paired.add(best_j)

    return pairings


# ---------------------------------------------------------------------------
# Per-game defaults
# ---------------------------------------------------------------------------

_GAME_ARGS: dict[str, dict] = {
    "BattleSnake": {"width": 11, "height": 11, "browser": False},
    "CoreWar": {},
    "Halite": {},
    "HuskyBench": {},
    "RoboCode": {"nodisplay": True, "nosound": True},
    "RobotRumble": {"raw": True},
}


def _default_game_args(game_name: str) -> dict:
    """Return default game_args for the given game."""
    return dict(_GAME_ARGS.get(game_name, {}))


# ---------------------------------------------------------------------------
# Match execution
# ---------------------------------------------------------------------------


def make_pvp_config(
    game_name: str,
    sims_per_round: int,
    player1_name: str,
    player1_path: str,
    player2_name: str,
    player2_path: str,
    game_args: dict | None = None,
) -> dict:
    """Build a PvP config dict for two static agents."""
    if game_args is None:
        game_args = _default_game_args(game_name)

    return {
        "tournament": {"rounds": 0},  # No edit rounds — just run sims
        "game": {
            "name": game_name,
            "sims_per_round": sims_per_round,
            "args": game_args,
        },
        "players": [
            {
                "agent": "static",
                "name": player1_name,
                "editable": False,
                "args": {"source_path": player1_path},
            },
            {
                "agent": "static",
                "name": player2_name,
                "editable": False,
                "args": {"source_path": player2_path},
            },
        ],
        "prompts": {},
    }


def run_match(
    config: dict,
    output_dir: Path,
) -> dict | None:
    """Run a single PvP match and return the result.

    Returns dict with keys: winner, scores, player1, player2.
    Returns None if the match was already completed (resume mode).
    """
    metadata_file = output_dir / "metadata.json"

    # Check if already completed
    if metadata_file.exists():
        try:
            meta = json.loads(metadata_file.read_text())
            round_stats = meta.get("round_stats", {}).get("0", {})
            return {
                "winner": round_stats.get("winner"),
                "scores": round_stats.get("scores", {}),
                "resumed": True,
            }
        except (json.JSONDecodeError, KeyError):
            pass  # Corrupted — re-run

    try:
        tournament = PvpTournament(config, output_dir=output_dir)
        tournament.run()
    except FileExistsError:
        # Already exists — read results
        if metadata_file.exists():
            meta = json.loads(metadata_file.read_text())
            round_stats = meta.get("round_stats", {}).get("0", {})
            return {
                "winner": round_stats.get("winner"),
                "scores": round_stats.get("scores", {}),
                "resumed": True,
            }
        return None
    except Exception as e:
        logger.error(f"Match failed: {e}")
        return None

    # Read results
    if metadata_file.exists():
        meta = json.loads(metadata_file.read_text())
        round_stats = meta.get("round_stats", {}).get("0", {})
        return {
            "winner": round_stats.get("winner"),
            "scores": round_stats.get("scores", {}),
            "resumed": False,
        }

    return None


# ---------------------------------------------------------------------------
# Tournament runner
# ---------------------------------------------------------------------------


def discover_strategies(pool_dir: Path) -> list[StrategyInfo]:
    """Discover all strategies in the pool directory."""
    strategies = []
    for d in sorted(pool_dir.iterdir()):
        if not d.is_dir():
            continue
        # Must have main.py (BattleSnake) or equivalent
        if not any(d.iterdir()):
            continue
        strategies.append(StrategyInfo(name=d.name, path=d))
    return strategies


def run_swiss_tournament(
    pool_dir: Path,
    game_name: str = "BattleSnake",
    num_rounds: int = 15,
    sims_per_match: int = 10,
    seed: int = 42,
    game_args: dict | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> list[StrategyInfo]:
    """Run a full Swiss-system Elo tournament.

    Returns strategies sorted by final Elo (descending).
    """
    rng = Random(seed)

    # Discover strategies
    strategies = discover_strategies(pool_dir)
    n = len(strategies)
    logger.info(f"Found {n} strategies in {pool_dir}")

    if n < 2:
        logger.error("Need at least 2 strategies for a tournament")
        return strategies

    # Output directory
    if output_dir is None:
        output_dir = LOCAL_LOG_DIR / "elo" / game_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load existing state if resuming
    state_file = output_dir / "elo_state.json"
    start_round = 0
    if state_file.exists():
        state = json.loads(state_file.read_text())
        start_round = state.get("completed_rounds", 0)
        for s in strategies:
            if s.name in state.get("ratings", {}):
                info = state["ratings"][s.name]
                s.elo = info["elo"]
                s.wins = info["wins"]
                s.losses = info["losses"]
                s.draws = info["draws"]
                s.matches_played = info["matches_played"]
                s.opponents_faced = set(info.get("opponents_faced", []))
        logger.info(f"Resumed from round {start_round}")

    total_matches = 0
    start_time = time.time()

    for swiss_round in range(start_round, num_rounds):
        logger.info(f"\n{'='*60}")
        logger.info(f"Swiss Round {swiss_round + 1}/{num_rounds}")
        logger.info(f"{'='*60}")

        # Generate pairings
        pairings = swiss_pair(strategies, rng, avoid_rematches=True)
        logger.info(f"  Pairings: {len(pairings)} matches")

        if dry_run:
            for idx_a, idx_b in pairings:
                sa, sb = strategies[idx_a], strategies[idx_b]
                logger.info(
                    f"    {sa.name} (Elo {sa.elo:.0f}) vs "
                    f"{sb.name} (Elo {sb.elo:.0f})"
                )
            continue

        round_results = []

        for match_idx, (idx_a, idx_b) in enumerate(pairings):
            sa, sb = strategies[idx_a], strategies[idx_b]

            logger.info(
                f"  Match {match_idx+1}/{len(pairings)}: "
                f"{sa.name} ({sa.elo:.0f}) vs {sb.name} ({sb.elo:.0f})"
            )

            config = make_pvp_config(
                game_name=game_name,
                sims_per_round=sims_per_match,
                player1_name=sa.name,
                player1_path=str(sa.path),
                player2_name=sb.name,
                player2_path=str(sb.path),
                game_args=game_args,
            )

            match_dir = (
                output_dir
                / "matches"
                / f"round_{swiss_round:02d}"
                / f"{sa.name}_vs_{sb.name}"
            )
            result = run_match(config, match_dir)

            if result is None:
                logger.warning("  Match failed, skipping")
                continue

            # Extract winner from match result. Arena 'scores' are game-specific
            # (HuskyBench stores cumulative chip totals, not win counts), so we
            # key Elo off the 'winner' field only.
            winner = result.get("winner")
            scores = result.get("scores", {})  # kept for logging only
            score_a = scores.get(sa.name, 0)
            score_b = scores.get(sb.name, 0)

            # Update records
            sa.opponents_faced.add(sb.name)
            sb.opponents_faced.add(sa.name)
            sa.matches_played += 1
            sb.matches_played += 1

            if winner == sa.name:
                s_a = 1.0
                sa.wins += 1
                sb.losses += 1
            elif winner == sb.name:
                s_a = 0.0
                sb.wins += 1
                sa.losses += 1
            else:
                s_a = 0.5
                sa.draws += 1
                sb.draws += 1

            # Update Elo from match outcome (winner-based).
            new_elo_a, new_elo_b = update_elo(sa.elo, sb.elo, s_a)

            resumed_tag = " [cached]" if result.get("resumed") else ""
            logger.info(
                f"    Score: {sa.name}={score_a} {sb.name}={score_b} "
                f"→ Winner: {winner} | "
                f"Elo: {sa.elo:.0f}→{new_elo_a:.0f}, {sb.elo:.0f}→{new_elo_b:.0f}"
                f"{resumed_tag}"
            )

            sa.elo = new_elo_a
            sb.elo = new_elo_b
            total_matches += 1

            round_results.append(
                {
                    "player_a": sa.name,
                    "player_b": sb.name,
                    "score_a": score_a,
                    "score_b": score_b,
                    "winner": winner,
                    "elo_a": round(new_elo_a, 1),
                    "elo_b": round(new_elo_b, 1),
                }
            )

        if not dry_run:
            # Save state after each round
            _save_state(strategies, swiss_round + 1, output_dir, state_file)

            # Show standings
            ranked = sorted(strategies, key=lambda s: -s.elo)
            logger.info(f"\n  Standings after round {swiss_round + 1}:")
            for rank, s in enumerate(ranked[:10], 1):
                logger.info(
                    f"    {rank:2d}. {s.name:40s} Elo={s.elo:7.1f}  "
                    f"W={s.wins} L={s.losses} D={s.draws}"
                )
            if n > 10:
                logger.info(f"    ... ({n - 10} more)")

    elapsed = time.time() - start_time

    if not dry_run:
        # Final report
        ranked = sorted(strategies, key=lambda s: -s.elo)
        logger.info(f"\n{'='*60}")
        logger.info(f"FINAL ELO RANKINGS ({total_matches} matches in {elapsed:.0f}s)")
        logger.info(f"{'='*60}")
        for rank, s in enumerate(ranked, 1):
            logger.info(
                f"  {rank:2d}. {s.name:40s} Elo={s.elo:7.1f}  "
                f"W={s.wins:2d} L={s.losses:2d} D={s.draws:2d}  "
                f"WR={s.win_rate:.1%}"
            )

        # Save final report
        report = {
            "game": game_name,
            "pool": str(pool_dir),
            "num_strategies": n,
            "num_rounds": num_rounds,
            "sims_per_match": sims_per_match,
            "total_matches": total_matches,
            "elapsed_seconds": round(elapsed, 1),
            "rankings": [s.to_dict() for s in ranked],
        }
        report_file = output_dir / "elo_rankings.json"
        atomic_write(report_file, json.dumps(report, indent=2))
        logger.info(f"\nRankings saved to {report_file}")

        # Also update provenance.json files in the pool with Elo ratings
        _update_provenance_with_elo(ranked)

    return sorted(strategies, key=lambda s: -s.elo)


def _save_state(
    strategies: list[StrategyInfo],
    completed_rounds: int,
    output_dir: Path,
    state_file: Path,
) -> None:
    """Save tournament state for resumability."""
    state = {
        "completed_rounds": completed_rounds,
        "timestamp": int(time.time()),
        "ratings": {
            s.name: {
                "elo": round(s.elo, 1),
                "wins": s.wins,
                "losses": s.losses,
                "draws": s.draws,
                "matches_played": s.matches_played,
                "opponents_faced": list(s.opponents_faced),
            }
            for s in strategies
        },
    }
    atomic_write(state_file, json.dumps(state, indent=2))


def _update_provenance_with_elo(ranked: list[StrategyInfo]) -> None:
    """Update each strategy's provenance.json with Elo rating and rank."""
    for rank, s in enumerate(ranked, 1):
        prov_file = s.path / "provenance.json"
        if not prov_file.exists():
            continue

        try:
            prov = json.loads(prov_file.read_text())
        except json.JSONDecodeError:
            continue

        prov["elo"] = round(s.elo, 1)
        prov["elo_rank"] = rank
        prov["elo_total"] = len(ranked)
        prov["elo_win_rate"] = round(s.win_rate, 3)
        prov["elo_matches"] = s.matches_played

        # Assign difficulty tier based on Elo tercile
        n = len(ranked)
        if rank <= n // 3:
            prov["elo_tier"] = "hard"  # high Elo = harder to beat = harder to recover
        elif rank <= 2 * n // 3:
            prov["elo_tier"] = "medium"
        else:
            prov["elo_tier"] = "easy"

        atomic_write(prov_file, json.dumps(prov, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Swiss-system Elo tournament for strategy ranking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pool",
        type=Path,
        required=True,
        help="Pool directory containing strategy subdirectories",
    )
    parser.add_argument(
        "--game",
        type=str,
        default="BattleSnake",
        help="Game name (default: BattleSnake)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=15,
        help="Number of Swiss rounds (default: 15)",
    )
    parser.add_argument(
        "--sims",
        type=int,
        default=100,
        help=(
            "Hands per match for HuskyBench (poker) or sims per match for other "
            "games (default: 100). Poker-skill resolution needs ~100 hands; "
            "10 is pure blind-rotation noise."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory for match logs and rankings",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Resume from an existing tournament output directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pairings without running simulations",
    )

    args = parser.parse_args()

    output_dir = args.output or args.resume
    if args.resume and args.output:
        parser.error("Cannot specify both --output and --resume")

    run_swiss_tournament(
        pool_dir=args.pool,
        game_name=args.game,
        num_rounds=args.rounds,
        sims_per_match=args.sims,
        seed=args.seed,
        output_dir=output_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
