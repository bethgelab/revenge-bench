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
        from revenge_bench.traces.offline_eval import (
            find_battlesnake_sim_files,
            score_battlesnake_simulations,
        )

        sim_files = find_battlesnake_sim_files(round_dir)
        if not sim_files:
            self.logger.warning(f"No sim_*.jsonl files in {round_dir}")
            return None

        learner_code_dir = self._setup_learner_for_eval(round_dir)
        if learner_code_dir is None or not self._load_learner_module(learner_code_dir):
            self.logger.warning("Failed to setup learner for BattleSnake evaluation")
            return {
                "error": "Failed to load learner module (check that main.py defines a valid move() function)"
            }

        target_name = self.target_agent.name

        total_actions, total_distance, per_simulation, all_nonzero = (
            score_battlesnake_simulations(
                sim_files,
                round_dir,
                target_name,
                self._learner_move_func,
                logger=self.logger,
            )
        )

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
        from revenge_bench.traces.offline_eval import (
            evaluate_robotrumble_submission_with_action_provider,
            find_robotrumble_sim_files,
            make_robotrumble_js_action_provider,
        )

        if not find_robotrumble_sim_files(round_dir):
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

        result = evaluate_robotrumble_submission_with_action_provider(
            round_dir=round_dir,
            round_num=round_num,
            learner_name=self.learner_agent.name,
            action_provider=make_robotrumble_js_action_provider(robot_js, timeout=120),
            fallback_target_team=getattr(self, "_rr_target_team", "Blue"),
            logger=self.logger,
            evaluation_type="offline",
        )
        if result.get("error") == "No state-action pairs extracted from sim files":
            self.logger.warning("No state-action pairs extracted from sim files")
            return None
        traces_file = round_dir / "traces.json"
        traces_file.write_text(json.dumps(result, indent=2))
        self.logger.info(f"Saved RobotRumble trace summary to {traces_file}")
        return result

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
        from revenge_bench.traces.offline_eval import (
            evaluate_halite_submission_with_action_provider,
            find_halite_sim_files,
        )
        from revenge_bench.traces.parsers.halite import query_compiled_bot

        if not find_halite_sim_files(round_dir):
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

        summary = evaluate_halite_submission_with_action_provider(
            round_dir=round_dir,
            round_num=round_num,
            target_hlt_name=target_hlt_name,
            learner_name=self.learner_agent.name,
            action_provider=lambda hlt_data, player_tag: query_compiled_bot(
                learner_executable,
                hlt_data,
                player_tag,
                timeout=10.0,
            ),
            logger=self.logger,
            evaluation_type="offline_subprocess",
        )

        traces_file = round_dir / "traces.json"
        traces_file.write_text(json.dumps(summary, indent=2))
        self.logger.info(f"Saved Halite trace summary to {traces_file}")
        return summary

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
        """Offline evaluation for RoboCode via the shared scorer."""
        from revenge_bench.traces.offline_eval import (
            evaluate_robocode_submission_with_move_provider,
            find_robocode_sim_files,
        )

        sim_files = find_robocode_sim_files(round_dir)
        if not sim_files:
            self.logger.warning(f"No record_*.xml files in {round_dir}")
            return None

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

        summary = evaluate_robocode_submission_with_move_provider(
            round_dir=round_dir,
            round_num=round_num,
            target_name=target_name,
            learner_name=self.learner_agent.name,
            move_provider=self._query_learner,
            parser_target_name=parser_target_name,
            evaluation_type="offline",
            logger=self.logger,
        )
        traces_file = round_dir / "traces.json"
        traces_file.write_text(json.dumps(summary, indent=2))
        self.logger.info(f"Saved RoboCode trace summary to {traces_file}")
        return summary

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
        from revenge_bench.traces.offline_eval import build_trace_summary

        summary = build_trace_summary(
            round_num,
            game_name,
            self.learner_agent.name,
            target_name,
            evaluation_type,
            total_actions,
            total_distance,
            per_simulation,
            all_nonzero,
        )

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
        from revenge_bench.traces.offline_eval import compute_component_errors

        return compute_component_errors(all_nonzero, total_actions)

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
        from revenge_bench.traces.offline_eval import (
            load_move_function,
            resolve_submission_path,
        )

        # Use game's submission path (e.g. "main.py", "client/player.py")
        submission = self.game.submission

        submission_py, code_dir = resolve_submission_path(
            learner_code_dir, submission
        )

        if not submission_py.exists():
            self.logger.warning(f"Learner {submission} not found at {submission_py}")
            return False

        module, move_func, kind = load_move_function(submission_py, code_dir)

        if module is None:
            self.logger.warning("Failed to load learner module")
            return False

        if move_func is None:
            self.logger.warning(
                f"Learner {submission} has no move(), choose_move(), or robot() function"
            )
            return False

        if kind == "choose_move":
            self.logger.info("Using choose_move() instead of move()")
        elif kind == "robot":
            self.logger.info("Using robot() (RobotRumble API)")

        self._learner_move_func = move_func
        self._learner_module = module
        self.logger.info(f"Loaded learner module from {submission_py}")
        return True

    def _process_huskybench_traces(
        self, round_dir: Path, round_num: int
    ) -> dict[str, Any] | None:
        """Offline evaluation for HuskyBench (poker) via the shared scorer."""
        from revenge_bench.traces.offline_eval import (
            evaluate_huskybench_submission_with_action_provider,
            find_huskybench_sim_files,
            make_huskybench_bot_action_provider,
        )

        if not find_huskybench_sim_files(round_dir):
            self.logger.warning(f"No game_log files in {round_dir}")
            return None

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

        provider, error = make_huskybench_bot_action_provider(submission_py, code_dir)
        if error is not None or provider is None:
            self.logger.warning(error)
            return {"error": error}

        summary = evaluate_huskybench_submission_with_action_provider(
            round_dir=round_dir,
            round_num=round_num,
            target_name=self.target_agent.name,
            learner_name=self.learner_agent.name,
            action_provider=provider,
            logger=self.logger,
            evaluation_type="offline_bot_class",
        )
        traces_file = round_dir / "traces.json"
        traces_file.write_text(json.dumps(summary, indent=2))
        self.logger.info(f"Saved HuskyBench trace summary to {traces_file}")
        return summary

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
        from revenge_bench.traces.offline_eval import query_move

        move_func = getattr(self, "_learner_move_func", None)
        return query_move(move_func, state, logger=self.logger)

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
