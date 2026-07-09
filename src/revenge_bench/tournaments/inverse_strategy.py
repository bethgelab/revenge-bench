"""
Inverse Strategy Tournament.

A tournament where a Learner agent recovers a Target's strategy.

Design:
- Learner: Can edit code (LLM agent), does NOT play in simulation
- Target: Static code (strategy to be recovered), plays in simulation
- Opponent: Static code (plays against target), can be same as target for self-play

Flow:
1. Round 0: Run simulation (Target vs Opponent) → baseline traces
2. Round N (N >= 1):
   a. Edit Phase: Learner edits code based on traces from round N-1
   b. Simulation Phase: Run game (Target vs Opponent, NOT learner) → new traces
   c. Evaluation Phase: Query learner's code on target's states (offline)
   d. Compute mean action distance between learner and target (lower is better)

The learner receives:
- logs/rounds/N-1/sim_*.jsonl - Raw game traces (target's states and actions)
- logs/rounds/N-1/traces.json - Parsed summary with distance metrics
- logs/rounds/N-1/eval_results.json - Evaluation results (mismatches for debugging)

Key insight: Learner never plays in the game. Evaluation is offline - we feed
target's states to learner's code and compare actions.
"""

import gc
import json
from pathlib import Path
from typing import Any

from revenge_bench.agents import get_agent
from revenge_bench.agents.player import Player
from revenge_bench.agents.utils import GameContext
from revenge_bench.arenas import get_arena
from revenge_bench.arenas.arena import CodeArena
from revenge_bench.constants import DIR_LOGS, DIR_WORK, FILE_RESULTS
from revenge_bench.tournaments.tournament import AbstractTournament
from revenge_bench.utils.atomic_write import atomic_write
from revenge_bench.utils.aws import is_running_in_aws_batch, s3_log_sync
from revenge_bench.utils.environment import copy_to_container, create_file_in_container


def build_round_transition_summary(
    *,
    round_num: int,
    total_rounds: int,
    step_increment: int,
    distance_history: dict,
    mismatch_counts: dict,
    submission_status_per_round: dict,
) -> dict:
    """Build the summary dict for ClashAgent.append_round_transition.

    All inputs are keyed by round number. round_num is the *new* round about
    to start; the previous round (round_num - 1) is the one being summarized.
    """
    prev = round_num - 1
    return {
        "distance": distance_history.get(prev),
        "previous_distance": distance_history.get(prev - 1),
        "mismatches": mismatch_counts.get(prev),
        "submission_status": submission_status_per_round.get(prev, "?"),
        "total_rounds": total_rounds,
        "step_increment": step_increment,
    }


class InverseStrategyTournament(AbstractTournament):
    """
    Tournament for inverse strategy learning.

    Learner tries to recover Target's strategy by:
    1. Observing traces from Target vs Opponent simulations
    2. Writing/editing code to reproduce Target's behavior

    Key design: Learner does NOT play in simulations. Evaluation is offline -
    we query learner's code with target's states and compare actions.
    """

    def __init__(
        self,
        config: dict,
        *,
        output_dir: Path,
        cleanup: bool = False,
        keep_containers: bool = False,
    ):
        metadata_file = output_dir / "metadata.json"
        if metadata_file.exists():
            raise FileExistsError(f"Metadata file already exists: {metadata_file}")

        super().__init__(
            config, name="InverseStrategyTournament", output_dir=output_dir
        )
        self.cleanup_on_end = cleanup

        self.context_mode = self.config.get("tournament", {}).get(
            "context_mode", "persistent"
        )
        if self.context_mode not in ("persistent", "reset"):
            raise ValueError(
                f"tournament.context_mode must be 'persistent' or 'reset', "
                f"got {self.context_mode!r}"
            )

        # Observation mode: 'raw' (default) copies sim files, 'nl_summary'
        # sends only an LLM-generated natural language behavioural summary.
        self.observation_mode = self.config.get("tournament", {}).get(
            "observation_mode", "raw"
        )
        if self.observation_mode not in ("raw", "nl_summary"):
            raise ValueError(
                f"tournament.observation_mode must be 'raw' or 'nl_summary', "
                f"got {self.observation_mode!r}"
            )
        # Summarizer model config (only used when observation_mode='nl_summary')
        self.summarizer_model_config = self.config.get("tournament", {}).get(
            "summarizer_model", {}
        )

        # Initialize game arena
        self.game: CodeArena = get_arena(
            self.config,
            tournament_id=self.tournament_id,
            local_output_dir=self.local_output_dir,
            keep_containers=keep_containers,
        )

        # Initialize all agents from config
        self.agents: list[Player] = []
        player_configs = self.config["players"]

        if len(player_configs) < 2:
            raise ValueError(
                "InverseStrategyTournament requires at least 2 players (learner + target)"
            )
        if len(player_configs) > 3:
            raise ValueError(
                "InverseStrategyTournament supports at most 3 players (learner + target + opponent)"
            )

        for agent_conf in player_configs:
            self.agents.append(self.get_agent(agent_conf, self.config["prompts"]))

        # Identify agent roles
        self.learner_agent: Player = self._get_learner_agent()
        self.target_agent: Player = self._get_target_agent()
        self.opponent_agent: Player = self._get_opponent_agent()
        # Agents that participate in the simulation (NOT learner)
        self.game_agents: list[Player] = [self.target_agent, self.opponent_agent]

        self.logger.info(
            f"Learner agent: {self.learner_agent.name} (edits code, does NOT play)"
        )
        self.logger.info(
            f"Target agent: {self.target_agent.name} (strategy to recover)"
        )
        self.logger.info(
            f"Opponent agent: {self.opponent_agent.name} (plays against target)"
        )

        # MCP control plane — only when the learner is Codex-backed.
        # Lazy import keeps the mcp SDK off the import path for mini-swe
        # configs / installations without that extra.
        self._mcp_server = None  # type: ignore[var-annotated]
        if getattr(self.learner_agent, "edit_phase_backend", None) == "codex":
            from revenge_bench.agents.codex_mcp import CodexMCPServer

            self._mcp_server = CodexMCPServer(
                learner_environment=self.learner_agent.environment,
            )
            self._mcp_server.start()
            # Hand the agent a reference so it can register the URL/token
            # with the Codex CLI under its CODEX_HOME and propagate them
            # via env vars when invoking the helper.
            self.learner_agent.set_mcp_server(self._mcp_server)
            self.logger.info(
                f"Started tournament-scoped MCP server for codex learner: "
                f"{self._mcp_server.base_url}{self._mcp_server.mcp_path}"
            )

    # Hook methods overridden by interventionist subclass.
    def _get_probe_callback(self):
        """Probe callback to register with the MCP server each round.

        Base tournament has no probing; the interventionist subclass
        returns its `_run_inline_probe` here.
        """
        return None

    def _get_max_probes(self) -> int:
        """Probe budget for the MCP server's begin_round call.

        Base tournament has no probing → 0; interventionist returns
        `self.max_probes_per_round`.
        """
        return 0

    def _get_learner_agent(self) -> Player:
        """Get the agent that can edit (learner). Does not play in simulation."""
        for i, agent_conf in enumerate(self.config["players"]):
            if agent_conf.get("editable", False):
                return self.agents[i]
        # Default to first agent if none explicitly marked
        return self.agents[0]

    def _get_target_agent(self) -> Player:
        """Get the target agent (strategy to be recovered)."""
        for i, agent_conf in enumerate(self.config["players"]):
            if agent_conf.get("name") == "target":
                return self.agents[i]
        # If no explicit target, use first non-learner agent
        for agent in self.agents:
            if agent != self.learner_agent:
                return agent
        raise ValueError("Could not identify target agent")

    def _get_opponent_agent(self) -> Player:
        """Get the opponent agent (plays against target in simulation).

        If not explicitly specified, defaults to target (self-play).
        """
        for i, agent_conf in enumerate(self.config["players"]):
            if agent_conf.get("name") == "opponent":
                return self.agents[i]
        # Default: use target as opponent (self-play)
        self.logger.info("No explicit opponent specified, using target for self-play")
        return self.target_agent

    @property
    def metadata_file(self) -> Path:
        return self.local_output_dir / "metadata.json"

    @property
    def rounds(self) -> int:
        return self.config["tournament"]["rounds"]

    def get_metadata(self) -> dict:
        metadata = {
            **super().get_metadata(),
            "game": self.game.get_metadata(),
            "agents": [agent.get_metadata() for agent in self.agents],
            "learner": self.learner_agent.name,
            "game_agents": [a.name for a in self.game_agents],
        }
        metadata["target"] = self.target_agent.name
        metadata["opponent"] = self.opponent_agent.name
        return metadata

    def get_agent(self, agent_config: dict, prompts: dict) -> Player:
        """Create an agent with environment and game context."""
        environment = self.game.get_environment(
            f"{self.game.game_id}.{agent_config['name']}"
        )

        game_context = GameContext(
            id=self.game.game_id,
            log_env=self.game.log_env,
            log_local=self.game.log_local,
            name=self.game.name,
            player_id=agent_config["name"],
            prompts=prompts,
            round=1,
            rounds=self.rounds,
            working_dir=str(DIR_WORK),
            context_mode=self.context_mode,
        )

        return get_agent(agent_config, game_context, environment)

    def run(self, *, opponents: list[Path] | None = None) -> None:
        """Main execution function that runs all rounds.

        Args:
            opponents: Optional list of opponent paths, reused every round.
                None means the opponent stays as configured in the YAML.
        """
        try:
            # Round 0: Initial simulation (Target vs Opponent, no editing)
            if opponents:
                self._run_multi_opponent_sim(0, opponents)
            else:
                self.run_simulation_phase(0)
            self.run_evaluation_phase(0)

            for round_num in range(1, self.rounds + 1):
                self.run_edit_phase(round_num)
                if opponents:
                    self._run_multi_opponent_sim(round_num, opponents)
                else:
                    self.run_simulation_phase(round_num)
                self.run_evaluation_phase(round_num)

            # Compress the last round
            self._compress_round_folder(self.rounds)
        finally:
            self.end()

    def _run_multi_opponent_sim(self, round_num: int, opponents: list[Path]) -> None:
        """Run simulation phase against multiple opponents in one round.

        For each opponent:
        1. Swap opponent code
        2. Run sims (sims_per_round // num_opponents)
        3. Copy logs to rounds/{round_num}/opp_{idx}/

        With a single opponent this is equivalent to the old flow, except
        logs land in opp_0/ instead of directly in rounds/{round_num}/.
        """
        total_sims = self.config["game"]["sims_per_round"]
        num_opps = len(opponents)
        sims_per_opp = total_sims // num_opps
        remainder = total_sims % num_opps

        round_dir = self.game.log_local / "rounds" / str(round_num)
        round_dir.mkdir(parents=True, exist_ok=True)

        all_stats: list[dict] = []
        opp_names: list[str] = []

        for opp_idx, opp_path in enumerate(opponents):
            # Swap opponent code
            self.opponent_agent.update_strategy(opp_path)
            opp_name = opp_path.name
            opp_names.append(opp_name)
            self.logger.info(
                f"Round {round_num} opponent {opp_idx + 1}/{num_opps}: "
                f"{self.target_agent.name} vs {opp_name}"
            )

            extra = 1 if opp_idx < remainder else 0
            orig_sims = self.config["game"]["sims_per_round"]
            self.config["game"]["sims_per_round"] = sims_per_opp + extra

            # Outer try/except covers only the simulation call itself so that
            # file-I/O errors in the post-sim block propagate with their real
            # traceback instead of being mislabelled as "simulation_failed".
            try:
                try:
                    # run_round copies logs to rounds/{round_num}/ AND reads them for get_results
                    stats = self.game.run_round(self.game_agents, round_num)
                finally:
                    self.config["game"]["sims_per_round"] = orig_sims
            except Exception as exc:
                err_msg = (
                    f"simulation failed at opponent {opp_idx + 1}/{num_opps} "
                    f"({opp_name}): {type(exc).__name__}: {exc}"
                )
                self.logger.error(err_msg, exc_info=True)
                self._metadata.setdefault("distance_history", {})[round_num] = None
                self._metadata.setdefault("evaluation_failed", {})[round_num] = True
                self._metadata.setdefault("evaluation_errors", {})[round_num] = err_msg
                self._metadata.setdefault("mismatch_counts", {})[round_num] = None
                self._metadata.setdefault("submission_status_per_round", {})[
                    round_num
                ] = "simulation_failed"
                self._metadata.setdefault("opponent_history", {})[round_num] = [
                    str(p) for p in opponents  # planned opponents (regardless of how many actually ran)
                ]
                self._metadata.setdefault("round_stats", {})[round_num] = all_stats  # partial
                self._save()
                raise

            # Post-sim work runs outside the try/except — file-I/O errors here
            # should propagate normally with their original traceback.

            # Record which team the target was assigned to AFTER shuffle.
            # run_round shuffles game_agents in-place: [0] = Blue, [1] = Red.
            target_team = "Blue" if self.game_agents[0] == self.target_agent else "Red"

            # Detect target's in-game bot name on the very first game
            if opp_idx == 0 and self.game.name == "Halite":
                self._detect_target_hlt_name(round_dir)

            # Move sim files from round dir to opponent-specific subdir
            opp_dir = round_dir / f"opp_{opp_idx}"
            opp_dir.mkdir(parents=True, exist_ok=True)
            self._move_sim_files_to_subdir(round_dir, opp_dir)

            # Persist the target team for this opponent so evaluation can
            # look it up later (the next run_round call will re-shuffle).
            (opp_dir / "_target_team.txt").write_text(target_team)

            all_stats.append(stats.to_dict())

        # Store metadata
        self._metadata.setdefault("round_stats", {})[round_num] = all_stats
        self._metadata.setdefault("opponent_history", {})[round_num] = [
            str(p) for p in opponents
        ]

        # Write combined results
        results_file = round_dir / FILE_RESULTS
        results_file.write_text(json.dumps(all_stats, indent=2))
        self._save()

    def _move_sim_files_to_subdir(self, round_dir: Path, opp_dir: Path) -> None:
        """Move per-simulation output files from round dir to opponent subdir."""
        import shutil

        patterns = [
            "sim_*.jsonl",
            "sim_*.json",
            "record_*.xml",
            "results_*.txt",
            "game_log_*.json",
            "*.hlt",
        ]
        for pattern in patterns:
            for sim_file in sorted(round_dir.glob(pattern)):
                shutil.move(str(sim_file), str(opp_dir / sim_file.name))

    def _detect_target_hlt_name(self, round_dir: Path) -> None:
        """Detect and cache the target bot's in-game name from a .hlt replay.

        Must be called right after ``run_round`` (which shuffles
        ``self.game_agents`` in-place) so the agent order matches the
        player order in the .hlt file.
        """
        if getattr(self, "_target_hlt_name", None) is not None:
            return  # Already detected
        try:
            from revenge_bench.traces.parsers.halite import load_hlt_file

            hlt_files = sorted(round_dir.glob("*.hlt"))
            if not hlt_files:
                hlt_files = sorted(round_dir.glob("opp_*/*.hlt"))
            if not hlt_files:
                return
            data = load_hlt_file(hlt_files[0])
            names = data.get("player_names", [])
            target_pos = next(
                (i for i, a in enumerate(self.game_agents) if a is self.target_agent),
                None,
            )
            if target_pos is not None and target_pos < len(names):
                self._target_hlt_name = names[target_pos]
                self.logger.info(f"Detected target bot name: {self._target_hlt_name}")
        except Exception as e:
            self.logger.debug(f"Could not detect target bot name: {e}")

    def _swap_opponent(self, opponent_path: Path, round_num: int) -> None:
        """Swap the opponent's strategy code before a simulation phase."""
        self.opponent_agent.update_strategy(opponent_path)
        self._metadata.setdefault("opponent_history", {})[round_num] = str(
            opponent_path
        )
        self.logger.info(f"Swapped opponent to: {opponent_path.name}")

    def run_simulation_phase(self, round_num: int) -> None:
        """
        Run game simulations (Target vs Opponent, NOT learner).

        Steps:
        1. Run game via Arena with game_agents (target + opponent)
        2. Produces sim_X.jsonl files with target's states and actions

        Note: Learner does NOT participate in simulation.

        """
        self.logger.info(
            f"Running simulation: {self.target_agent.name} vs {self.opponent_agent.name}"
        )

        # Run the game round with ONLY game agents (target + opponent)
        stats = self.game.run_round(self.game_agents, round_num)
        self.logger.info(stats)

        # Record which team the target was assigned to AFTER shuffle.
        # run_round shuffles game_agents in-place: [0] = Blue, [1] = Red.
        self._rr_target_team = (
            "Blue" if self.game_agents[0] == self.target_agent else "Red"
        )

        if self.game.name == "Halite":
            round_dir = self.game.log_local / "rounds" / str(round_num)
            self._detect_target_hlt_name(round_dir)

        # Store basic stats
        self._metadata.setdefault("round_stats", {})[round_num] = stats.to_dict()

        # Create directory for round logs
        round_dir = self.game.log_local / "rounds" / str(round_num)
        round_dir.mkdir(parents=True, exist_ok=True)

        # Write results
        results_file = round_dir / FILE_RESULTS
        results_file.write_text(json.dumps(stats.to_dict(), indent=2))

        self._save()

    def run_evaluation_phase(self, round_num: int) -> None:
        """
        Evaluate learner's code on target's states (offline).

        For each (target_state, target_action) in traces:
            learner_action = learner_code(target_state)
            distance = actions_distance(learner_action, target_action)

        Computes mean action distance (lower is better, 0 = perfect recovery).
        """
        round_dir = self.game.log_local / "rounds" / str(round_num)

        # Process traces and compute mean action distance
        trace_summary = self._process_traces(round_dir, round_num)

        # Store mean distance in metadata (lower is better)
        if isinstance(trace_summary, dict) and trace_summary.get("error"):
            # Evaluation failed with a specific reason
            self._metadata.setdefault("distance_history", {})[round_num] = None
            self._metadata.setdefault("evaluation_failed", {})[round_num] = True
            self._metadata.setdefault("evaluation_errors", {})[
                round_num
            ] = trace_summary["error"]
            self._metadata.setdefault("mismatch_counts", {})[round_num] = None
            self._metadata.setdefault("submission_status_per_round", {})[
                round_num
            ] = "evaluation_failed"
            self.logger.warning(
                f"Round {round_num} evaluation failed: {trace_summary['error']}"
            )
        elif trace_summary:
            self._metadata.setdefault("distance_history", {})[
                round_num
            ] = trace_summary.get("mean_distance")
            self._metadata.setdefault("evaluation_failed", {})[round_num] = False
            # Count mismatches as the number of actions with nonzero distance
            self._metadata.setdefault("mismatch_counts", {})[round_num] = len(
                trace_summary.get("nonzero_distances", [])
            )
            self._metadata.setdefault("submission_status_per_round", {})[
                round_num
            ] = "ok"
            self.logger.info(
                f"Round {round_num} mean action distance: {trace_summary.get('mean_distance', float('inf')):.4f}"
            )
        else:
            # Evaluation failed - record explicitly
            self._metadata.setdefault("distance_history", {})[round_num] = None
            self._metadata.setdefault("evaluation_failed", {})[round_num] = True
            self._metadata.setdefault("mismatch_counts", {})[round_num] = None
            self._metadata.setdefault("submission_status_per_round", {})[
                round_num
            ] = "evaluation_failed"
            self.logger.warning(
                f"Round {round_num} evaluation failed - no distance recorded"
            )

        # Free the large trace summary (nonzero_distances with full game states)
        del trace_summary
        gc.collect()

        self._save()

    def _process_traces(self, round_dir: Path, round_num: int) -> dict[str, Any] | None:
        """
        Offline evaluation: Query learner's code with target's states.

        For each turn in the simulation traces:
        1. Extract target's state (what target saw)
        2. Extract target's action (what target did)
        3. Query learner's code with target's state
        4. Compare learner's action vs target's action

        Returns a summary dict saved to traces.json:
        {
            "round": N,
            "total_actions": 1000,        # Total target actions evaluated
            "total_distance": 42.5,       # Sum of action distances
            "mean_distance": 0.0425,      # Mean action distance (pooled, lower is better)
            "learner": "learner",
            "target": "target",
            "per_simulation": [...],      # Per-sim breakdown
            "nonzero_distances": [...]    # Actions with distance > 0
        }
        """
        game_name = self.game.name

        # Dispatch to game-specific evaluation methods
        dispatch = {
            "HuskyBench": self._process_huskybench_traces,
            "Halite": self._process_halite_traces,
            "Halite3": self._process_halite3_traces,
            "BattleSnake": self._process_battlesnake_traces,
            "RobotRumble": self._process_robotrumble_traces,
            "RoboCode": self._process_robocode_traces,
        }
        handler = dispatch.get(game_name)
        if handler is None:
            self.logger.warning(f"No offline evaluation support for game {game_name}")
            return None
        return handler(round_dir, round_num)

    def _process_battlesnake_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for BattleSnake.

        BattleSnake bots export a move(state) function that returns a direction string.
        Sim files are JSONL with one JSON object per turn.
        """
        from revenge_bench.traces.parsers.battlesnake import (
            actions_distance,
            extract_state_action_pairs,
        )

        sim_files = sorted(round_dir.glob("sim_*.jsonl"))
        if not sim_files:
            # Multi-opponent layout: opp_*/sim_*.jsonl
            sim_files = sorted(round_dir.glob("opp_*/sim_*.jsonl"))
        if not sim_files:
            self.logger.warning(f"No sim_*.jsonl files in {round_dir}")
            return None

        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None or not self._load_learner_module(learner_code_dir):
            self.logger.warning("Failed to setup learner for BattleSnake evaluation")
            return {
                "error": "Failed to load learner module (check that main.py defines a valid move() function)"
            }

        total_actions = 0
        total_distance = 0.0
        per_simulation = []
        all_nonzero = []
        target_name = self.target_agent.name

        for sim_file in sim_files:
            try:
                sim_total = 0
                sim_distance = 0.0
                sim_nonzero = []

                state_action_pairs = extract_state_action_pairs(sim_file, target_name)

                for turn_idx, (target_state, target_action) in enumerate(
                    state_action_pairs
                ):
                    learner_action = self._query_learner(target_state)
                    if learner_action is None:
                        continue

                    sim_total += 1
                    distance = actions_distance(learner_action, target_action)
                    sim_distance += distance

                    if distance > 0.0:
                        entry = {
                            "sim_file": str(sim_file.relative_to(round_dir)),
                            "turn": target_state.get("turn", turn_idx),
                            "learner_action": learner_action,
                            "target_action": target_action,
                            "distance": distance,
                            "state": target_state,
                        }
                        sim_nonzero.append(entry)
                        all_nonzero.append(entry)

                total_actions += sim_total
                total_distance += sim_distance
                per_simulation.append(
                    {
                        "file": str(sim_file.relative_to(round_dir)),
                        "total": sim_total,
                        "distance_sum": sim_distance,
                        "mean_distance": sim_distance / sim_total
                        if sim_total > 0
                        else 0.0,
                        "num_nonzero": len(sim_nonzero),
                    }
                )
            except Exception as e:
                self.logger.warning(f"Error processing {sim_file}: {e}")
                import traceback

                traceback.print_exc()
                continue

        return self._build_trace_summary(
            round_num,
            "BattleSnake",
            target_name,
            "offline",
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
            round_dir,
        )

    def _process_robotrumble_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for RobotRumble via JS Docker subprocess.

        Runs the learner's robot.js inside ``node:18-alpine`` with the
        RobotRumble stdlib, feeding every game state through stdin/stdout
        (one JSON line per turn).  This mirrors how the real RobotRumble
        engine invokes the learner — fully in JavaScript.
        """
        from revenge_bench.traces.parsers.robotrumble import (
            actions_distance,
            extract_state_action_pairs,
        )

        sim_files = sorted(round_dir.glob("sim_*.json"))
        if not sim_files:
            # Multi-opponent layout: opp_*/sim_*.json
            sim_files = sorted(round_dir.glob("opp_*/sim_*.json"))
        if not sim_files:
            self.logger.warning(f"No sim_*.json files in {round_dir}")
            return None

        # ── locate learner robot.js ──────────────────────────────────
        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None:
            self.logger.warning(
                "Failed to copy learner code for RobotRumble evaluation"
            )
            return {"error": "Failed to copy learner code from container"}

        robot_js = learner_code_dir / "workspace" / "robot.js"
        if not robot_js.exists():
            robot_js = learner_code_dir / "robot.js"
        if not robot_js.exists():
            self.logger.warning(f"robot.js not found in {learner_code_dir}")
            return {"error": "robot.js not found in learner workspace"}

        # ── harness / stdlib paths (shipped with codeclash) ──────────
        parsers_dir = Path(__file__).resolve().parent.parent / "traces" / "parsers"
        harness_js = parsers_dir / "robotrumble_eval_harness.js"
        stdlib_js = parsers_dir / "robotrumble_stdlib.js"
        lodash_js = parsers_dir / "robotrumble_lodash.min.js"

        # ── team assignment ──────────────────────────────────────────
        # Determine per-sim-file which team the target was assigned to.
        # run_round shuffles game_agents in-place so [0]=Blue, [1]=Red.
        # For multi-opponent runs, each opp_X/ has a _target_team.txt
        # written right after its run_round call (before the next shuffle).
        # For single-opponent runs, self._rr_target_team is set in
        # run_simulation_phase right after run_round.
        def _target_team_for(sim_path: Path) -> str:
            # Check for per-opponent metadata first (multi-opponent layout)
            team_file = sim_path.parent / "_target_team.txt"
            if team_file.exists():
                return team_file.read_text().strip()
            # Fall back to single-opponent attribute
            return getattr(self, "_rr_target_team", "Blue")

        # ── collect all (sim_file, turn_idx, state, target_action) ───
        work_items: list[tuple[Path, int, dict, list[dict]]] = []
        for sim_file in sim_files:
            parser_target_name = _target_team_for(sim_file)
            self.logger.debug(
                f"RobotRumble target team for {sim_file.name}: {parser_target_name}"
            )
            try:
                for turn_idx, (target_state, target_action) in enumerate(
                    extract_state_action_pairs(sim_file, parser_target_name)
                ):
                    work_items.append((sim_file, turn_idx, target_state, target_action))
            except Exception as e:
                self.logger.warning(f"Error parsing {sim_file}: {e}")

        if not work_items:
            self.logger.warning("No state-action pairs extracted from sim files")
            return None

        # ── build JSONL payload for the harness ──────────────────────
        input_lines: list[str] = []
        for _, _, state, _ in work_items:
            harness_input = {
                "state": {"objs": state["all_objs"], "turn": state.get("turn", 0)},
                "team": state["team"],
            }
            input_lines.append(json.dumps(harness_input, separators=(",", ":")))
        payload = "\n".join(input_lines) + "\n"

        # ── run JS evaluation (docker or singularity, runtime-aware) ─
        from revenge_bench.utils.js_eval import run_js_eval

        result = run_js_eval(
            harness_js, stdlib_js, lodash_js, robot_js,
            payload=payload, timeout=120,
        )
        if result.returncode != 0:
            self.logger.warning(
                f"JS eval failed (rc={result.returncode}): "
                f"{(result.error or '')[:500]}"
            )
            return {"error": f"JS evaluation failed: {(result.error or '')[:200]}"}

        output_lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        if len(output_lines) != len(work_items):
            self.logger.warning(
                f"JS eval output mismatch: got {len(output_lines)} lines for {len(work_items)} states"
            )
            return {"error": "JS eval output line count mismatch"}

        # ── compare learner actions with target ──────────────────────
        total_actions = 0
        total_distance = 0.0
        per_simulation: list[dict] = []
        all_nonzero: list[dict] = []

        # Group by sim file to build per_simulation stats

        sim_groups: dict[str, list[tuple[int, dict, list[dict], list[dict]]]] = {}
        for idx, (sim_file, turn_idx, target_state, target_action) in enumerate(
            work_items
        ):
            learner_action = json.loads(output_lines[idx])
            sim_key = str(sim_file.relative_to(round_dir))
            sim_groups.setdefault(sim_key, []).append(
                (turn_idx, target_state, target_action, learner_action)
            )

        for sim_key, items in sim_groups.items():
            sim_total = 0
            sim_distance = 0.0
            sim_nonzero: list[dict] = []

            for turn_idx, target_state, target_action, learner_action in items:
                sim_total += 1
                distance = actions_distance(learner_action, target_action)
                sim_distance += distance

                if distance > 0.0:
                    entry = {
                        "sim_file": Path(sim_key).name,
                        "turn": target_state.get("turn", turn_idx),
                        "learner_action": learner_action,
                        "target_action": target_action,
                        "distance": distance,
                        "state": target_state,
                    }
                    sim_nonzero.append(entry)
                    all_nonzero.append(entry)

            total_actions += sim_total
            total_distance += sim_distance
            per_simulation.append(
                {
                    "file": sim_key,
                    "total": sim_total,
                    "distance_sum": sim_distance,
                    "mean_distance": sim_distance / sim_total if sim_total > 0 else 0.0,
                    "num_nonzero": len(sim_nonzero),
                }
            )

        return self._build_trace_summary(
            round_num,
            "RobotRumble",
            parser_target_name,
            "offline",
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
            round_dir,
        )

    def _process_halite_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for Halite I (compiled bots via subprocess).

        Halite bots are compiled binaries. This method:
        1. Copies the learner's code and compiles it on the host
        2. For each .hlt replay, feeds all frames to the compiled bot
           via subprocess and collects its moves
        3. Compares learner's moves against target's recorded moves
        """
        from revenge_bench.traces.parsers.halite import (
            actions_distance,
            extract_state_action_pairs,
            load_hlt_file,
            query_compiled_bot,
        )

        sim_files = sorted(round_dir.glob("*.hlt"))
        if not sim_files:
            sim_files = sorted(round_dir.glob("opp_*/*.hlt"))
        if not sim_files:
            self.logger.warning(f"No .hlt files in {round_dir}")
            return None

        # Compile learner bot on host
        try:
            learner_executable = self._setup_compiled_learner(round_dir)
        except RuntimeError as e:
            self.logger.warning(f"Halite trace eval setup failed: {e}")
            return {"error": str(e)}

        # Halite uses in-game bot names (detected during simulation)
        target_hlt_name = getattr(self, "_target_hlt_name", None)
        if target_hlt_name is None:
            self.logger.warning("Target bot name not detected during simulation")
            return {
                "error": "Target bot name not detected during simulation (no _target_hlt_name)"
            }
        self.logger.info(f"Using target bot name: {target_hlt_name}")

        total_actions = 0
        total_distance = 0.0
        per_simulation = []
        all_nonzero = []

        for sim_file in sim_files:
            try:
                sim_total = 0
                sim_distance = 0.0
                sim_nonzero = []

                state_action_pairs = extract_state_action_pairs(
                    sim_file, target_hlt_name
                )

                # Batch query: feed all frames via subprocess at once
                hlt_data = load_hlt_file(sim_file)
                player_tag = hlt_data["player_names"].index(target_hlt_name) + 1
                learner_actions = query_compiled_bot(
                    learner_executable,
                    hlt_data,
                    player_tag,
                    timeout=10.0,
                )

                for turn_idx, (target_state, target_action) in enumerate(
                    state_action_pairs
                ):
                    learner_action = (
                        learner_actions[turn_idx]
                        if turn_idx < len(learner_actions)
                        else []
                    )

                    sim_total += 1
                    distance = actions_distance(learner_action, target_action)
                    sim_distance += distance

                    if distance > 0.0:
                        entry = {
                            "sim_file": str(sim_file.relative_to(round_dir)),
                            "turn": target_state.get("turn", turn_idx),
                            "learner_action": learner_action,
                            "target_action": target_action,
                            "distance": distance,
                            "state": target_state,
                        }
                        sim_nonzero.append(entry)
                        all_nonzero.append(entry)

                total_actions += sim_total
                total_distance += sim_distance
                per_simulation.append(
                    {
                        "file": str(sim_file.relative_to(round_dir)),
                        "total": sim_total,
                        "distance_sum": sim_distance,
                        "mean_distance": sim_distance / sim_total
                        if sim_total > 0
                        else 0.0,
                        "num_nonzero": len(sim_nonzero),
                    }
                )
            except Exception as e:
                self.logger.warning(f"Error processing {sim_file}: {e}")
                import traceback

                traceback.print_exc()
                continue

        return self._build_trace_summary(
            round_num,
            "Halite",
            target_hlt_name,
            "offline_subprocess",
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
            round_dir,
        )

    def _process_halite3_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for Halite III.

        Halite III replays are zstd-compressed .hlt files.
        """
        from revenge_bench.traces.parsers.halite3 import (
            actions_distance,
            extract_state_action_pairs,
        )

        sim_files = sorted(round_dir.glob("replay-*.hlt"))
        if not sim_files:
            sim_files = sorted(round_dir.glob("opp_*/replay-*.hlt"))
        if not sim_files:
            self.logger.warning(f"No replay-*.hlt files in {round_dir}")
            return None

        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None or not self._load_learner_module(learner_code_dir):
            self.logger.warning("Failed to setup learner for Halite3 evaluation")
            return None

        total_actions = 0
        total_distance = 0.0
        per_simulation = []
        all_nonzero = []
        target_name = self.target_agent.name

        for sim_file in sim_files:
            try:
                sim_total = 0
                sim_distance = 0.0
                sim_nonzero = []

                state_action_pairs = extract_state_action_pairs(sim_file, target_name)

                for turn_idx, (target_state, target_action) in enumerate(
                    state_action_pairs
                ):
                    learner_action = self._query_learner(target_state)
                    if learner_action is None:
                        continue

                    sim_total += 1
                    distance = actions_distance(learner_action, target_action)
                    sim_distance += distance

                    if distance > 0.0:
                        entry = {
                            "sim_file": str(sim_file.relative_to(round_dir)),
                            "turn": target_state.get("turn", turn_idx),
                            "learner_action": learner_action,
                            "target_action": target_action,
                            "distance": distance,
                            "state": target_state,
                        }
                        sim_nonzero.append(entry)
                        all_nonzero.append(entry)

                total_actions += sim_total
                total_distance += sim_distance
                per_simulation.append(
                    {
                        "file": str(sim_file.relative_to(round_dir)),
                        "total": sim_total,
                        "distance_sum": sim_distance,
                        "mean_distance": sim_distance / sim_total
                        if sim_total > 0
                        else 0.0,
                        "num_nonzero": len(sim_nonzero),
                    }
                )
            except Exception as e:
                self.logger.warning(f"Error processing {sim_file}: {e}")
                import traceback

                traceback.print_exc()
                continue

        return self._build_trace_summary(
            round_num,
            "Halite3",
            target_name,
            "offline",
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
            round_dir,
        )

    def _process_robocode_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for RoboCode.

        The learner writes a Python ``move(state) → action`` function that
        receives the game state dict and returns a 5-component action dict
        (velocity, turn_body, turn_gun, turn_radar, fire_power).

        For each state the target saw, we call the learner's ``move()`` and
        compare the returned action with what the target actually did (inferred
        from consecutive XML frames).
        """
        from revenge_bench.traces.parsers.robocode import (
            actions_distance,
            extract_state_action_pairs,
        )

        sim_files = sorted(round_dir.glob("record_*.xml"))
        if not sim_files:
            # Multi-opponent layout: opp_*/record_*.xml
            sim_files = sorted(round_dir.glob("opp_*/record_*.xml"))
        if not sim_files:
            self.logger.warning(f"No record_*.xml files in {round_dir}")
            return None

        # Setup: Copy learner code to host and load module
        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None or not self._load_learner_module(learner_code_dir):
            self.logger.warning("Failed to setup learner for RoboCode evaluation")
            return {
                "error": "Failed to load learner module (check that main.py defines a valid move() function)"
            }

        # Resolve target package alias (e.g. "p0" in XML → "target" in config)
        target_name = self.target_agent.name
        pkg_map_file = round_dir / "_pkg_to_agent.json"
        if not pkg_map_file.exists():
            candidates = sorted(round_dir.glob("opp_*/_pkg_to_agent.json"))
            if candidates:
                pkg_map_file = candidates[0]
        if pkg_map_file.exists():
            pkg_to_agent = json.loads(pkg_map_file.read_text())
            agent_to_pkg = {v: k for k, v in pkg_to_agent.items()}
            parser_target_name = agent_to_pkg.get(target_name, target_name)
        else:
            parser_target_name = target_name

        total_actions = 0
        total_distance = 0.0
        per_simulation: list[dict] = []
        all_nonzero: list[dict] = []

        for sim_file in sim_files:
            try:
                sim_total = 0
                sim_distance = 0.0
                sim_nonzero: list[dict] = []

                state_action_pairs = extract_state_action_pairs(
                    sim_file, parser_target_name
                )

                for turn_idx, (target_state, target_action) in enumerate(
                    state_action_pairs
                ):
                    learner_action = self._query_learner(target_state)
                    if learner_action is None:
                        continue

                    sim_total += 1
                    distance = actions_distance(learner_action, target_action)
                    sim_distance += distance

                    if distance > 0.0:
                        entry = {
                            "sim_file": str(sim_file.relative_to(round_dir)),
                            "turn": target_state.get("turn", turn_idx),
                            "learner_action": learner_action,
                            "target_action": target_action,
                            "distance": distance,
                            "state": target_state,
                        }
                        sim_nonzero.append(entry)
                        all_nonzero.append(entry)

                total_actions += sim_total
                total_distance += sim_distance
                per_simulation.append(
                    {
                        "file": str(sim_file.relative_to(round_dir)),
                        "total": sim_total,
                        "distance_sum": sim_distance,
                        "mean_distance": sim_distance / sim_total
                        if sim_total > 0
                        else 0.0,
                        "num_nonzero": len(sim_nonzero),
                    }
                )
            except Exception as e:
                self.logger.warning(f"Error processing {sim_file}: {e}")
                import traceback

                traceback.print_exc()
                continue

        return self._build_trace_summary(
            round_num,
            "RoboCode",
            target_name,
            "offline",
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
            round_dir,
        )

    def _build_trace_summary(
        self,
        round_num: int,
        game_name: str,
        target_name: str,
        evaluation_type: str,
        total_actions: int,
        total_distance: float,
        per_simulation: list,
        all_nonzero: list,
        round_dir: Path,
    ) -> dict[str, Any]:
        """Compute statistics and save traces.json. Shared by all game-specific eval methods."""
        mean_distance = (
            total_distance / total_actions if total_actions > 0 else float("inf")
        )

        sim_mean_distances = [
            s["mean_distance"] for s in per_simulation if s["total"] > 0
        ]
        if sim_mean_distances:
            import statistics

            mean_distance_across_sims = statistics.mean(sim_mean_distances)
            distance_std = (
                statistics.stdev(sim_mean_distances)
                if len(sim_mean_distances) > 1
                else 0.0
            )
            distance_se = distance_std / (len(sim_mean_distances) ** 0.5)
        else:
            mean_distance_across_sims = float("inf")
            distance_std = 0.0
            distance_se = 0.0

        summary = {
            "round": round_num,
            "game": game_name,
            "learner": self.learner_agent.name,
            "target": target_name,
            "evaluation_type": evaluation_type,
            "total_actions": total_actions,
            "total_distance": total_distance,
            "mean_distance": mean_distance,
            "mean_distance_across_sims": mean_distance_across_sims,
            "distance_std": distance_std,
            "distance_se": distance_se,
            "num_simulations": len(per_simulation),
            "per_simulation": per_simulation,
        }

        # Per-component error breakdown (RoboCode: 5-component actions)
        if all_nonzero and isinstance(all_nonzero[0].get("learner_action"), dict):
            component_errors = self._compute_component_errors(
                all_nonzero, total_actions
            )
            if component_errors:
                summary["component_errors"] = component_errors

        summary["nonzero_distances"] = all_nonzero

        traces_file = round_dir / "traces.json"
        traces_file.write_text(json.dumps(summary, indent=2))
        self.logger.info(f"Saved {game_name} trace summary to {traces_file}")
        return summary

    @staticmethod
    def _compute_component_errors(
        all_nonzero: list[dict], total_actions: int
    ) -> dict[str, Any] | None:
        """Compute per-component error statistics from nonzero distance entries.

        Returns a dict mapping component name to error stats, plus which
        components contribute the most overall error.
        """
        try:
            from revenge_bench.traces.parsers.robocode import (
                ACTION_COMPONENTS,
                ACTION_RANGES,
            )
        except ImportError:
            return None

        # Accumulate per-component absolute errors
        comp_sums: dict[str, float] = {c: 0.0 for c in ACTION_COMPONENTS}
        comp_counts: dict[str, int] = {c: 0 for c in ACTION_COMPONENTS}
        comp_max: dict[str, float] = {c: 0.0 for c in ACTION_COMPONENTS}

        for entry in all_nonzero:
            la = entry.get("learner_action", {})
            ta = entry.get("target_action", {})
            for comp in ACTION_COMPONENTS:
                lv = la.get(comp, 0.0)
                tv = ta.get(comp, 0.0)
                rng = ACTION_RANGES[comp]
                max_diff = rng if comp == "fire_power" else 2.0 * rng
                normed = min(abs(lv - tv) / max_diff, 1.0)
                comp_sums[comp] += normed
                if normed > 0:
                    comp_counts[comp] += 1
                if normed > comp_max[comp]:
                    comp_max[comp] = normed

        result = {}
        for comp in ACTION_COMPONENTS:
            rng = ACTION_RANGES[comp]
            max_diff = rng if comp == "fire_power" else 2.0 * rng
            mean_err = comp_sums[comp] / total_actions if total_actions > 0 else 0.0
            result[comp] = {
                "mean_normalized_error": round(mean_err, 6),
                "nonzero_count": comp_counts[comp],
                "max_normalized_error": round(comp_max[comp], 6),
                "range": f"[{-rng if comp != 'fire_power' else 0}, {rng}]",
                "max_abs_diff": max_diff,
            }

        # Rank by contribution to overall error
        ranked = sorted(
            ACTION_COMPONENTS,
            key=lambda c: result[c]["mean_normalized_error"],
            reverse=True,
        )
        result["worst_to_best"] = ranked

        return result

    def _setup_learner_for_eval(self, round_dir: Path) -> Path | None:
        """Copy learner's code from container to host for direct import.

        Returns the path to the copied workspace, or None if failed.
        """
        try:
            from revenge_bench.utils.environment import copy_from_container

            # Copy learner's /workspace to local eval directory
            eval_dir = round_dir / "learner_code"
            eval_dir.mkdir(parents=True, exist_ok=True)

            copy_from_container(
                self.learner_agent.environment,
                Path("/workspace"),
                eval_dir,
            )

            self.logger.debug(f"Copied learner code to {eval_dir}")
            return eval_dir

        except Exception as e:
            self.logger.warning(f"Failed to copy learner code: {e}")
            return None

    def _load_learner_module(self, learner_code_dir: Path) -> bool:
        """Load the learner's submission file as a Python module.

        Returns True if successful, False otherwise.
        """
        import importlib.util
        import sys

        # Use game's submission path (e.g. "main.py", "client/player.py")
        submission = self.game.submission

        # copy_from_container copies /workspace as a subdirectory
        workspace_dir = learner_code_dir / "workspace"
        if workspace_dir.exists():
            submission_py = workspace_dir / submission
            code_dir = submission_py.parent
        else:
            # Fallback to direct path
            submission_py = learner_code_dir / submission
            code_dir = submission_py.parent

        # For directory-based submissions (e.g. RoboCode's "robots/custom/"),
        # fall back to main.py in the workspace root for offline evaluation.
        if submission_py.is_dir() or not submission_py.exists():
            fallback = (
                workspace_dir if workspace_dir.exists() else learner_code_dir
            ) / "main.py"
            if fallback.exists():
                submission_py = fallback
                code_dir = fallback.parent

        if not submission_py.exists():
            self.logger.warning(f"Learner {submission} not found at {submission_py}")
            return False

        try:
            # Add learner's code directory to path for any relative imports
            if str(code_dir) not in sys.path:
                sys.path.insert(0, str(code_dir))

            # Load the module
            spec = importlib.util.spec_from_file_location("learner_main", submission_py)
            if spec is None or spec.loader is None:
                self.logger.warning("Failed to create module spec")
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Verify it has a move function (accept move(), choose_move(), or robot())
            if hasattr(module, "move"):
                self._learner_move_func = module.move
            elif hasattr(module, "choose_move"):
                self._learner_move_func = module.choose_move
                self.logger.info("Using choose_move() instead of move()")
            elif hasattr(module, "robot"):
                self._learner_move_func = module.robot
                self.logger.info("Using robot() (RobotRumble API)")
            else:
                self.logger.warning(
                    f"Learner {submission} has no move(), choose_move(), or robot() function"
                )
                return False

            self._learner_module = module
            self.logger.info(f"Loaded learner module from {submission_py}")
            return True

        except Exception as e:
            self.logger.warning(f"Failed to load learner module: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _process_huskybench_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for HuskyBench (poker).

        HuskyBench bots use a class-based API: they subclass Bot and implement
        get_action(round_state: RoundStateClient, remaining_chips) -> (PokerAction, int).

        This method:
        1. Copies the learner's code from its container
        2. Loads the Bot subclass and instantiates it
        3. For each target action in the game logs, reconstructs the state,
           converts it to RoundStateClient, queries the bot, and compares
        """
        import importlib.util
        import inspect
        import sys

        from revenge_bench.traces.parsers.huskybench import (
            actions_distance,
            extract_state_action_pairs,
            normalize_action,
        )

        # --- Find simulation files ---
        # In multi-opponent mode, game_log files live inside opp_*/ subdirs.
        sim_files = sorted(round_dir.glob("game_log_*.json")) or sorted(
            round_dir.glob("opp_*/game_log_*.json")
        )
        if not sim_files:
            self.logger.warning(f"No game_log files in {round_dir}")
            return None

        # --- Load learner's Bot class ---
        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None:
            self.logger.warning("Failed to copy learner code for HuskyBench evaluation")
            return {"error": "Failed to copy learner code from container"}

        workspace_dir = learner_code_dir / "workspace"
        if workspace_dir.exists():
            submission_py = workspace_dir / self.game.submission
            code_dir = submission_py.parent
        else:
            submission_py = learner_code_dir / self.game.submission
            code_dir = submission_py.parent

        if not submission_py.exists():
            self.logger.warning(
                f"Learner {self.game.submission} not found at {submission_py}"
            )
            return {"error": f"Submission file {self.game.submission} not found"}

        if str(code_dir) not in sys.path:
            sys.path.insert(0, str(code_dir))

        try:
            spec = importlib.util.spec_from_file_location(
                "learner_huskybench", submission_py
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            self.logger.warning(f"Failed to load learner module: {e}")
            return {"error": f"Failed to load module: {e}"}

        # Find the Bot subclass with get_action()
        bot_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name, None)
            if (
                inspect.isclass(attr)
                and hasattr(attr, "get_action")
                and attr_name != "Bot"
            ):
                bot_class = attr
                break

        if bot_class is None:
            self.logger.warning(
                "No Bot subclass with get_action() found in learner module"
            )
            return {"error": "No Bot subclass with get_action() found in submission"}

        RoundStateClient = getattr(module, "RoundStateClient", None)
        if RoundStateClient is None:
            self.logger.warning("RoundStateClient not found in learner module")
            return {"error": "RoundStateClient not importable from submission"}

        try:
            bot = bot_class()
        except Exception as e:
            self.logger.warning(f"Failed to instantiate {bot_class.__name__}: {e}")
            return {"error": f"Failed to instantiate {bot_class.__name__}: {e}"}

        self.logger.info(
            f"Loaded HuskyBench bot {bot_class.__name__} from {submission_py}"
        )

        # --- Helper: query bot with a reconstructed state dict ---
        def query_bot(state: dict) -> str | None:
            player_bets = {"0": 0, "1": 0}
            player_actions = {}
            for ah in state.get("action_history", []):
                pid = "0" if ah["player"] == "you" else "1"
                player_bets[pid] = player_bets.get(pid, 0) + ah.get("amount", 0)
                player_actions[pid] = ah.get("action", "")

            remaining_chips = state.get("my_stack", 10000)
            blinds = state.get("blinds", {})

            # Set hole cards via on_start (bots store them as self.my_hand)
            try:
                bot.on_start(
                    remaining_chips,
                    state.get("hole_cards", []),
                    blinds.get("big", 10),
                    1,
                    0,
                    [0, 1],
                )
            except Exception:
                pass

            try:
                round_state = RoundStateClient(
                    round_num=state.get("hand_number", 0),
                    round=state.get("round", "preflop"),
                    community_cards=state.get("community_cards", []),
                    pot=state.get("pot", 0),
                    current_player=[0],
                    current_bet=state.get("current_bet", 0),
                    min_raise=blinds.get("big", 10),
                    max_raise=remaining_chips,
                    player_bets=player_bets,
                    player_actions=player_actions,
                    player_money={
                        "0": remaining_chips,
                        "1": state["opponent_stacks"][0]
                        if state.get("opponent_stacks")
                        else 10000,
                    },
                    side_pots=[],
                )
            except Exception:
                return None

            try:
                try:
                    bot.on_round_start(round_state, remaining_chips)
                except Exception:
                    pass
                result = bot.get_action(round_state, remaining_chips)
                if isinstance(result, tuple) and len(result) == 2:
                    poker_action, amount = result
                    action_name = poker_action.name
                    if action_name == "ALL_IN":
                        return "RAISE:1.0000"
                    elif action_name == "RAISE":
                        return normalize_action(
                            {"action": "RAISE", "amount": amount},
                            player_stack=remaining_chips,
                        )
                    else:
                        return action_name
            except Exception:
                pass
            return None

        # --- Evaluate across all simulation files ---
        target_name = self.target_agent.name
        # Game logs have playerNames rewritten to actual agent names by
        # HuskyBenchArena.get_results(), so we can match by role name directly.
        target_selector = target_name
        total_actions = 0
        total_distance = 0.0
        per_simulation = []
        all_nonzero = []

        for sim_file in sim_files:
            try:
                sim_total = 0
                sim_distance = 0.0
                sim_nonzero = []

                state_action_pairs = extract_state_action_pairs(
                    sim_file, target_selector
                )

                for turn_idx, (target_state, target_action) in enumerate(
                    state_action_pairs
                ):
                    learner_action = query_bot(target_state)
                    if learner_action is None:
                        continue

                    sim_total += 1
                    distance = actions_distance(
                        learner_action,
                        target_action,
                        player_stack=target_state.get("my_stack"),
                    )
                    sim_distance += distance

                    if distance > 0.0:
                        entry = {
                            "sim_file": str(sim_file.relative_to(round_dir)),
                            "turn": target_state.get("turn", turn_idx),
                            "learner_action": learner_action,
                            "target_action": target_action,
                            "distance": distance,
                            "state": target_state,
                        }
                        sim_nonzero.append(entry)
                        all_nonzero.append(entry)

                total_actions += sim_total
                total_distance += sim_distance
                per_simulation.append(
                    {
                        "file": str(sim_file.relative_to(round_dir)),
                        "total": sim_total,
                        "distance_sum": sim_distance,
                        "mean_distance": sim_distance / sim_total
                        if sim_total > 0
                        else 0.0,
                        "num_nonzero": len(sim_nonzero),
                    }
                )
            except Exception as e:
                self.logger.warning(f"Error processing {sim_file}: {e}")
                import traceback

                traceback.print_exc()
                continue

        return self._build_trace_summary(
            round_num,
            "HuskyBench",
            target_name,
            "offline_bot_class",
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
            round_dir,
        )

    def _setup_compiled_learner(self, round_dir: Path) -> str:
        """Compile the learner's bot for subprocess-based offline evaluation.

        Copies the learner workspace to the host, finds the main source file,
        compiles it, and returns the executable command string.

        Returns:
            Executable command string (for ``query_compiled_bot``);
            raises RuntimeError on failure.
        """
        from revenge_bench.arenas.halite.halite import (
            MAP_FILE_TYPE_TO_COMPILE,
            MAP_FILE_TYPE_TO_RUN,
        )

        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None:
            self.logger.warning("Failed to copy learner code for compiled evaluation")
            raise RuntimeError(
                "Failed to copy learner code from container "
                "(transient files may have vanished mid-copy)"
            )

        workspace_dir = learner_code_dir / "workspace"
        if not workspace_dir.exists():
            workspace_dir = learner_code_dir
        sub_dir = workspace_dir / "submission"
        if not sub_dir.exists():
            self.logger.warning(f"No submission/ directory in {workspace_dir}")
            raise RuntimeError(f"No submission/ directory in learner workspace ({workspace_dir})")

        # Find main file
        main_files = [
            f.name
            for f in sub_dir.iterdir()
            if f.name.startswith("main.") and f.suffix in MAP_FILE_TYPE_TO_RUN
        ]
        if not main_files:
            # Rust: src/main.rs
            if (sub_dir / "src" / "main.rs").exists():
                main_files = ["src/main.rs"]
        if not main_files:
            self.logger.warning(f"No supported main file in {sub_dir}")
            raise RuntimeError(f"No supported main.<ext> file in {sub_dir}")

        main_ext = Path(main_files[0]).suffix

        # Compile if needed
        if main_ext in MAP_FILE_TYPE_TO_COMPILE:
            import subprocess as sp

            compile_cmd = MAP_FILE_TYPE_TO_COMPILE[main_ext].format(name="main")
            try:
                result = sp.run(
                    compile_cmd,
                    shell=True,
                    cwd=sub_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except sp.TimeoutExpired:
                self.logger.warning("Learner compilation timed out")
                raise RuntimeError("Learner compilation timed out (>30s)")
            if result.returncode != 0:
                self.logger.warning(f"Learner compilation failed: {result.stderr}")
                raise RuntimeError(
                    f"Learner compilation failed: {result.stderr.strip()[:500]}"
                )

        return MAP_FILE_TYPE_TO_RUN[main_ext].format(path=str(sub_dir), name="main")

    def _query_learner(self, state: dict) -> Any:
        """Query learner's code with a game state (offline evaluation).
        Directly imports and calls the learner's move()/choose_move()/robot() function.
        Requires _load_learner_module() to have been called first.

        Returns the action in its native format (dict for RoboCode,
        string for BattleSnake, list of dicts for RobotRumble/Halite, etc.)
        so it can be compared correctly.
        """
        if not hasattr(self, "_learner_move_func") or self._learner_move_func is None:
            return None

        try:
            result = self._learner_move_func(state)
            # Unwrap BattleSnake-style {"move": "up"} responses;
            # other games (RoboCode, HuskyBench) return the action directly.
            if isinstance(result, dict) and "move" in result:
                return result["move"]
            return result

        except Exception as e:
            self.logger.debug(f"Error querying learner: {e}")
            return None

    def _query_learner_per_unit(self, state: dict) -> list[dict]:
        """Query learner's robot(state, unit) for each unit (RobotRumble).

        Returns sorted list of {"unit_id": str, "action": dict|None} matching
        the format from extract_player_action(), so actions_distance() can
        compare them directly.
        """
        from revenge_bench.traces.parsers.robotrumble import normalize_action

        actions = []
        for unit in state.get("my_units", []):
            unit_id = str(unit.get("id", ""))
            try:
                result = self._learner_move_func(state, unit)
                normalized = normalize_action(result)
            except Exception as e:
                self.logger.debug(f"Error querying learner for unit {unit_id}: {e}")
                normalized = None
            actions.append({"unit_id": unit_id, "action": normalized})

        return sorted(actions, key=lambda a: a["unit_id"])

    def run_edit_phase(self, round_num: int) -> None:
        """Drive one round of the learner's editing.

        On round 1, initializes the resumable session. On rounds 2+, appends
        a pinned round-transition message before resuming the step loop.
        """
        prev_round = round_num - 1

        if self.observation_mode == "nl_summary":
            self._deliver_nl_observation(round_num, prev_round)
        else:
            # Copy logs from previous round to learner's container (unchanged)
            self.logger.info(
                f"Copying round {prev_round} logs to "
                f"{self.learner_agent.name}'s container..."
            )
            copy_to_container(
                self.learner_agent.environment,
                self.game.log_local / "rounds" / str(prev_round),
                DIR_LOGS / "rounds" / str(prev_round),
            )
        self._compress_round_folder(prev_round)

        # ── MCP per-round state (Codex backend only) ────────────────
        # Tools registered on the tournament-scoped MCP server need to
        # know which round they're serving and what budget to enforce.
        # Probe callback is None for the base tournament (no probing);
        # interventionist subclass overrides _get_probe_callback.
        # `getattr` with default keeps tests that bypass __init__
        # (`object.__new__(...)`) from blowing up on the attribute.
        mcp_server = getattr(self, "_mcp_server", None)
        if mcp_server is not None:
            max_round_seconds = self.learner_agent._max_round_seconds()  # type: ignore[union-attr]
            mcp_server.begin_round(
                round_num=round_num,
                max_round_seconds=max_round_seconds,
                max_probes=self._get_max_probes(),
                probe_callback=self._get_probe_callback(),
            )

        # ── Branch on context_mode ──────────────────────────────────
        if self.context_mode == "reset":
            # Old behaviour: build a fresh ClashAgent each round and call
            # the one-shot DefaultAgent.run() loop. The agent's run() handles
            # trajectory persistence internally.
            self.learner_agent.pre_run_hook(
                new_round=round_num,
                distance_history=self._metadata.get("distance_history", {}),
                evaluation_errors=self._metadata.get("evaluation_errors", {}),
            )
            try:
                self.learner_agent.run()
            finally:
                self.learner_agent.post_run_hook(round=round_num)
            self._save()
            self.logger.info(f"Edit phase round {round_num} completed (reset mode)")
            return

        # ── Persistent path ─────────────────────────────────────────
        #
        # Per-round budgets are mini-swe-specific; the Codex backend
        # ignores them and enforces wall-clock + probe limits via its
        # own `config.codex` block.  Read them lazily so Codex configs
        # without a `config.agent` block don't blow up here.
        if getattr(self.learner_agent, "edit_phase_backend", None) == "codex":
            step_increment = 0
            cost_increment = 0.0
        else:
            agent_cfg = self.learner_agent.config["config"]["agent"]
            step_increment = agent_cfg.get("step_limit", 30)
            cost_increment = agent_cfg.get("cost_limit", 1.0)

        # Update player game-context for this round
        self.learner_agent.pre_run_hook(
            new_round=round_num,
            distance_history=self._metadata.get("distance_history", {}),
            evaluation_errors=self._metadata.get("evaluation_errors", {}),
        )

        # First round: init session
        if round_num == 1:
            self.learner_agent.init_session()
            transition_summary = None
        else:
            transition_summary = build_round_transition_summary(
                round_num=round_num,
                total_rounds=self.rounds,
                step_increment=step_increment,
                distance_history=self._metadata.get("distance_history", {}),
                mismatch_counts=self._metadata.get("mismatch_counts", {}),
                submission_status_per_round=(
                    self._metadata.get("submission_status_per_round", {})
                ),
            )

        # Drive the round
        exit_status = "error"  # Default if BaseException escapes
        try:
            exit_status = self.learner_agent.run_round(
                round_num=round_num,
                transition_summary=transition_summary,
                step_increment=step_increment,
                cost_increment=cost_increment,
            )
        except Exception:
            exit_status = "error"
            raise
        finally:
            # Per-round trajectory snapshot (cumulative through this round)
            self.learner_agent.save_round_trajectory(
                round_num=round_num, exit_status=exit_status
            )
            self.learner_agent.post_run_hook(round=round_num)

        self._save()
        self.logger.info(f"Edit phase round {round_num} completed: {exit_status}")

    def _save(self) -> None:
        """Save metadata to disk."""
        self.local_output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.metadata_file, json.dumps(self.get_metadata(), indent=2))
        self.logger.debug(f"Metadata saved to {self.metadata_file}")
        if is_running_in_aws_batch():
            s3_log_sync(self.local_output_dir, logger=self.logger)

    def _deliver_nl_observation(self, round_num: int, prev_round: int) -> None:
        """Generate NL observation summary and deliver to learner container.

        In raw mode, the entire round folder is copied (sim files, traces.json,
        learner_code/, etc.). In NL mode we only provide:
        - observations_round_N.txt — LLM-generated behavioral summary
        Raw sim files and traces.json are NOT provided to the learner.
        """
        from revenge_bench.tournaments.observation_summarizer import (
            generate_nl_observation,
        )

        round_dir = self.game.log_local / "rounds" / str(prev_round)
        traces_file = round_dir / "traces.json"

        if not traces_file.exists():
            self.logger.warning(
                f"No traces.json for round {prev_round}; "
                f"falling back to empty observation."
            )
            summary_text = (
                f"[No observations available for round {prev_round}]"
            )
        else:
            traces_json = json.loads(traces_file.read_text())
            game_name = self.config.get("game", {}).get("name", "Unknown")

            # Build model kwargs from summarizer_model config
            model_name = self.summarizer_model_config.get(
                "model_name", "openai/gpt-4o-mini"
            )
            model_kwargs = {}
            if "api_base" in self.summarizer_model_config:
                model_kwargs["api_base"] = self.summarizer_model_config["api_base"]
            if "api_key" in self.summarizer_model_config:
                model_kwargs["api_key"] = self.summarizer_model_config["api_key"]

            summary_text = generate_nl_observation(
                traces_json=traces_json,
                sim_dir=round_dir,
                game_name=game_name,
                round_num=prev_round,
                model_name=model_name,
                model_kwargs=model_kwargs if model_kwargs else None,
            )
            # Free the large traces dict (nonzero_distances with full states)
            del traces_json
            gc.collect()

        # Write NL summary to the learner's container
        container_round_dir = DIR_LOGS / "rounds" / str(prev_round)
        create_file_in_container(
            self.learner_agent.environment,
            content=summary_text,
            dest_path=container_round_dir / f"observations_round_{prev_round}.txt",
        )

        # Copy learner_code/ to container (same as raw mode — useful for post-analysis)
        learner_code_dir = round_dir / "learner_code"
        if learner_code_dir.exists():
            copy_to_container(
                self.learner_agent.environment,
                learner_code_dir,
                container_round_dir / "learner_code",
            )

        self.logger.info(
            f"Delivered NL observation ({len(summary_text)} chars) "
            f"for round {prev_round} to {self.learner_agent.name}'s container"
        )

    def _compress_round_folder(self, round_num: int) -> None:
        """Compress a round's logs to save space."""
        import shutil
        import subprocess

        round_dir = self.game.log_local / "rounds" / str(round_num)
        if not round_dir.exists():
            return

        archive = self.game.log_local / "rounds" / f"round_{round_num}.tar.gz"
        cmd = [
            "tar",
            "-zcf",
            str(archive),
            "-C",
            str(round_dir.parent),
            str(round_num),
        ]
        self.logger.info(f"Compressing round {round_num} logs...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.logger.warning(
                f"Failed to compress round {round_num}: {result.stderr}"
            )
            return

        shutil.rmtree(round_dir)
        self.logger.info(f"Round {round_num} logs compressed successfully")

    def end(self) -> None:
        """Save output files, clean up resources."""
        self._save()
        self.game.end(self.cleanup_on_end)
        self.cleanup_handlers()
        mcp_server = getattr(self, "_mcp_server", None)
        if mcp_server is not None:
            mcp_server.stop()
            self._mcp_server = None
