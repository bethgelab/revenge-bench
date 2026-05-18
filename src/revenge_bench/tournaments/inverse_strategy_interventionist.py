"""
Inverse Strategy Interventionist Tournament.

Extension of InverseStrategyTournament with INLINE PROBING capability.

Design:
- During edit phase, agent can run `echo "PROBE_SUBMIT"` at any time
- This triggers a probe simulation: learner's probe code vs target
- Agent receives probe_traces immediately as observation
- Agent continues editing with new information
- End-of-round simulation is ALWAYS target vs opponent (like base class)
- Distance is always measured on the learner's submission (lower = better)

Game-specific execution is dispatched via _execute_probe() and
_parse_probe_traces_from_arena() — adding a new game requires
implementing those two methods.

This allows the agent to strategically probe the target's behavior
in specific situations they create, getting immediate feedback.
"""

import copy
import json
import shlex
import time
from pathlib import Path
from typing import Any

from revenge_bench.arenas import get_arena
from revenge_bench.arenas.arena import CodeArena
from revenge_bench.constants import DIR_WORK
from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
from revenge_bench.utils.environment import (
    copy_from_container,
    copy_to_container,
    create_file_in_container,
)


class InverseStrategyInterventionistTournament(InverseStrategyTournament):
    """
    Tournament for inverse strategy learning with inline probing.

    Extends InverseStrategyTournament to allow inline probing during edit phase.
    Agent can call PROBE_SUBMIT to run its probe code vs target and get
    immediate feedback.

    Game-specific behaviour is dispatched in three places:
    - ``_seed_probe``: copies submission → probe (file or dir)
    - ``_execute_probe``: reads code, sets up arena, runs simulation
    - ``_parse_probe_traces_from_arena``: parses game-specific replay files

    To add a new game, implement ``_execute_<game>_probe`` and
    ``_parse_<game>_probe_traces``, then add dispatch entries.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Inline probe settings (read from config)
        tournament_config = self.config.get("tournament", {})
        self.probe_arena: CodeArena | None = None
        self.probe_count: int = 0  # Total probes across tournament
        self.round_probe_count: int = 0  # Probes in current round
        self.round_probe_traces: list[dict[str, Any]] = []  # Probe traces for current round
        self.max_probes_per_round: int = tournament_config.get("max_probes_per_round", 5)
        self.sims_per_probe: int = tournament_config.get("sims_per_probe", 3)

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata["tournament_type"] = "interventionist"
        metadata["total_probe_count"] = self.probe_count
        metadata["max_probes_per_round"] = self.max_probes_per_round
        metadata["sims_per_probe"] = self.sims_per_probe
        return metadata

    # Hooks consumed by the base class's MCP `begin_round` plumbing.
    # The Codex backend reads these instead of `set_probe_callback` (which
    # is a no-op stub on CodexInverseStrategyAgent — Codex calls probes
    # via the MCP `run_probe` tool, not via in-prompt PROBE_SUBMIT).
    def _get_probe_callback(self):
        return self._run_inline_probe

    def _get_max_probes(self) -> int:
        return self.max_probes_per_round

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
                self.round_probe_count = 0
                self._run_edit_phase_with_probing(round_num)

                if opponents:
                    self._run_multi_opponent_sim(round_num, opponents)
                else:
                    self.run_simulation_phase(round_num)

                self._save_round_probe_traces(round_num)
                self.run_evaluation_phase(round_num)

            self._compress_round_folder(self.rounds)
        finally:
            self._cleanup_probe_arena()
            self.end()

    def _run_edit_phase_with_probing(self, round_num: int) -> None:
        """
        Run edit phase with inline probing callback enabled.

        Auto-seeds probe from the learner's current submission so the agent
        can immediately modify it for exploration without boilerplate setup.
        The agent can then call PROBE_SUBMIT during editing to trigger a probe.
        """
        # Reset round-specific tracking
        self.round_probe_traces = []
        self.current_round = round_num  # Track for probe file naming

        # Seed probe from current submission so agent starts with their latest policy
        self._seed_probe()

        if hasattr(self.learner_agent, "set_probe_callback"):
            self.learner_agent.set_probe_callback(
                callback=self._run_inline_probe,
                max_probes=self.max_probes_per_round,
            )
            self.logger.info(
                f"Inline probing enabled: {self.max_probes_per_round} probes/round, {self.sims_per_probe} sims/probe"
            )

        # Run the normal edit phase
        self.run_edit_phase(round_num)

        # Note: probe traces are saved after simulation phase when round folder exists

    def _seed_probe(self) -> None:
        """Copy the learner's submission to the probe location.

        Handles both file-based submissions (e.g., main.py -> probe.py) and
        directory-based submissions (e.g., submission/ -> probe/).

        For RobotRumble we seed ``probe.js`` from ``robot.js``.
        """
        submission = self.game.submission
        sub_path = Path(submission)

        # RobotRumble: seed probe.js from robot.js
        if self.game.name == "RobotRumble":
            src = DIR_WORK / "robot.js"
            dst = DIR_WORK / "probe.js"
            self.learner_agent.environment.execute(f"cp {src} {dst}")
            self.logger.info("Seeded probe.js from robot.js (RobotRumble)")
            return

        # RoboCode: seed probe/ from robots/custom/ (Java directory)
        if self.game.name == "RoboCode":
            probe_dir = DIR_WORK / "probe"
            src_dir = DIR_WORK / "robots" / "custom"
            self.learner_agent.environment.execute(f"rm -rf {probe_dir} && cp -r {src_dir} {probe_dir}")
            self.logger.info("Seeded probe/ from robots/custom/ (RoboCode)")
            return

        if sub_path.suffix and len(sub_path.parts) > 1:
            # Nested file (e.g. client/player.py -> probe/client/player.py)
            probe_path = DIR_WORK / "probe" / submission
            self.learner_agent.environment.execute(
                f"mkdir -p {probe_path.parent} && cp {DIR_WORK / submission} {probe_path}"
            )
            self.logger.info(f"Seeded probe/{submission} from {submission}")
        elif sub_path.suffix:
            # File-based: main.py -> probe.py (same extension)
            probe_name = f"probe{sub_path.suffix}"
            self.learner_agent.environment.execute(f"cp {DIR_WORK / submission} {DIR_WORK / probe_name}")
            self.logger.info(f"Seeded {probe_name} from {submission}")
        else:
            # Dir-based: submission/ -> probe/ (full copy)
            probe_dir = DIR_WORK / "probe"
            self.learner_agent.environment.execute(f"rm -rf {probe_dir} && cp -r {DIR_WORK / submission} {probe_dir}")
            self.logger.info(f"Seeded probe/ from {submission}/")

    # =========================================================================
    # Probe Arena Management
    # =========================================================================

    def _get_probe_arena(self) -> CodeArena:
        """
        Get or create the probe arena container.

        Separate from main game arena, used for running probe simulations.
        """
        if self.probe_arena is None:
            # Create config with fewer sims for quick probing
            probe_config = copy.deepcopy(self.config)
            probe_config["game"]["sims_per_round"] = self.sims_per_probe

            # Create probe-specific output directory
            probe_output_dir = self.local_output_dir / "probes"
            probe_output_dir.mkdir(parents=True, exist_ok=True)

            self.probe_arena = get_arena(
                probe_config,
                tournament_id=self.tournament_id + "_probe",
                local_output_dir=probe_output_dir,
                keep_containers=True,  # Reuse across probes
            )
            self.logger.info(f"Created probe arena ({self.sims_per_probe} sims/probe)")

        return self.probe_arena

    def _cleanup_probe_arena(self) -> None:
        """Clean up probe arena resources."""
        if self.probe_arena is not None:
            try:
                self.probe_arena.end(cleanup=True)
            except Exception as e:
                self.logger.warning(f"Error cleaning up probe arena: {e}")

    def _save_round_probe_traces(self, round_num: int) -> None:
        """
        Save probe traces metadata for the current round to the round folder.

        Saves to rounds/{round_num}/probe_traces.json which gets compressed
        along with other round data (traces.json, sim_*.jsonl, etc.).

        Note: Full pairs data is saved in individual files in learner container:
        /workspace/probe_trace_{probe_id}.json
        These are archived under learner_code/workspace/probe_trace_*.json

        This file only stores metadata + probe_code (no pairs) to avoid duplication.
        """
        if not self.round_probe_traces:
            self.logger.debug(f"No probes in round {round_num}, skipping probe_traces.json")
            return

        # Use game.log_local to match where simulation files are saved
        round_dir = self.game.log_local / "rounds" / str(round_num)
        if not round_dir.exists():
            self.logger.warning(f"Round directory {round_dir} does not exist, cannot save probe traces")
            return

        probe_traces_file = round_dir / "probe_traces.json"

        # Create metadata-only version (remove pairs to avoid duplication)
        # Pairs are available in learner_code/workspace/probe_trace_{probe_id}.json
        probes_metadata = []
        for trace in self.round_probe_traces:
            metadata = {
                "probe_id": trace.get("probe_id"),
                "round_probe_number": trace.get("round_probe_number"),
                "total_turns": trace.get("total_turns", 0),
                "num_simulations": trace.get("num_simulations", 0),
                "per_simulation": trace.get("per_simulation", []),
                "probe_code": trace.get("probe_code", ""),
                # Reference to where full pairs data can be found
                "pairs_file": f"learner_code/workspace/probe_trace_r{round_num}_p{trace.get('round_probe_number')}.json",
            }
            if "error" in trace:
                metadata["error"] = trace["error"]
            probes_metadata.append(metadata)

        summary = {
            "round": round_num,
            "num_probes": len(self.round_probe_traces),
            "probes": probes_metadata,
        }

        with open(probe_traces_file, "w") as f:
            json.dump(summary, f, indent=2)

        self.logger.info(f"Saved {len(self.round_probe_traces)} probe traces to {probe_traces_file.name}")

    # =========================================================================
    # Inline Probe Execution
    # =========================================================================

    def _run_inline_probe(self) -> str:
        """
        Run an inline probe simulation and return results as JSON string.

        Called by agent's probe callback when it runs ``echo "PROBE_SUBMIT"``.
        The probe is auto-seeded from the learner's submission at the start of
        each edit phase so the agent only needs to modify it before submitting.

        The actual execution (reading code, setting up arena, running the game)
        is delegated to a game-specific method via ``_execute_probe``.

        Returns:
            JSON string with probe traces
        """
        self.probe_count += 1
        self.round_probe_count += 1
        probe_id = self.probe_count

        self.logger.info(
            f"Running inline probe #{probe_id} (round probe {self.round_probe_count}/{self.max_probes_per_round})"
        )

        try:
            arena = self._get_probe_arena()

            # Game-specific: read code, setup arena, run simulation
            probe_code = self._execute_probe(arena)

            # Game-agnostic: parse traces, store, write to learner container
            traces = self._parse_probe_traces_from_arena(arena, probe_id)

            traces["round_probe_number"] = self.round_probe_count
            traces["probe_code"] = probe_code
            self.round_probe_traces.append(traces)

            self.logger.info(
                f"Probe #{probe_id}: {traces.get('total_turns', 0)} turns, {traces.get('num_simulations', 0)} sims"
            )

            return self._write_probe_to_learner_container(traces, probe_id)

        except Exception as e:
            self.logger.error(f"Inline probe failed: {e}")
            import traceback

            traceback.print_exc()
            error_trace = {
                "error": str(e),
                "probe_id": probe_id,
                "round_probe_number": self.round_probe_count,
            }
            self.round_probe_traces.append(error_trace)
            return json.dumps({"error": str(e)}, indent=2)

    def _execute_probe(self, arena: CodeArena) -> str:
        """Dispatch probe execution to the appropriate game-specific method.

        Returns:
            The probe's main source code (for metadata / debugging).
        """
        game_name = self.game.name
        if game_name == "BattleSnake":
            return self._execute_battlesnake_probe(arena)
        elif game_name == "Halite":
            return self._execute_halite_probe(arena)
        elif game_name == "HuskyBench":
            return self._execute_huskybench_probe(arena)
        elif game_name == "RobotRumble":
            return self._execute_robotrumble_probe(arena)
        elif game_name == "RoboCode":
            return self._execute_robocode_probe(arena)
        else:
            raise ValueError(f"Probe execution not supported for game: {game_name}")

    # -- BattleSnake ----------------------------------------------------------

    def _execute_battlesnake_probe(self, arena: CodeArena) -> str:
        """Run a BattleSnake probe simulation in *arena*.

        BattleSnake bots are single-file Python HTTP servers.  We copy the
        learner's ``probe.py`` and the target's ``main.py`` into the arena,
        start them on separate ports, and run the ``battlesnake play`` CLI.

        Returns:
            The probe source code (``probe.py`` content).
        """
        # Read probe code from learner container
        probe_result = self.learner_agent.environment.execute("cat /workspace/probe.py")
        if probe_result.get("returncode", 0) != 0:
            raise RuntimeError("Failed to read probe.py from learner container")
        probe_code = probe_result["output"]

        # Read target code from target container
        target_result = self.target_agent.environment.execute("cat /workspace/main.py")
        if target_result.get("returncode", 0) != 0:
            raise RuntimeError("Failed to read target main.py from target container")
        target_code = target_result["output"]

        # Set up probe arena container
        arena.environment.execute("mkdir -p /probe /target /logs")
        arena.environment.execute("rm -f /logs/*.jsonl")

        self._write_code_to_container(arena, "/probe/main.py", probe_code)
        self._write_code_to_container(arena, "/target/main.py", target_code)

        # Copy server.py (BattleSnake-specific helper)
        server_result = self.learner_agent.environment.execute("cat /workspace/server.py")
        if server_result.get("returncode", 0) == 0:
            self._write_code_to_container(arena, "/probe/server.py", server_result["output"])
            self._write_code_to_container(arena, "/target/server.py", server_result["output"])

        # Start servers
        arena.environment.execute("cd /probe && PORT=8001 python main.py &")
        arena.environment.execute("cd /target && PORT=8002 python main.py &")
        self._wait_for_probe_servers(arena)

        # Run simulations
        for i in range(self.sims_per_probe):
            arena.environment.execute(
                f"./battlesnake play "
                f"--url http://localhost:8001 -n probe "
                f"--url http://localhost:8002 -n target "
                f"--width 11 --height 11 "
                f"-o /logs/sim_{i}.jsonl",
                cwd="/workspace/game",
                timeout=60,
            )

        # Cleanup
        arena.environment.execute("pkill -f 'python main.py' || true")
        return probe_code

    def _wait_for_probe_servers(self, arena: CodeArena, timeout: float = 10.0) -> bool:
        """Wait for BattleSnake probe HTTP servers to be ready."""
        start = time.time()
        while time.time() - start < timeout:
            check1 = arena.environment.execute("wget -q --spider --timeout=1 http://localhost:8001/ 2>&1; echo $?")
            check2 = arena.environment.execute("wget -q --spider --timeout=1 http://localhost:8002/ 2>&1; echo $?")
            if "0" in check1.get("output", "").strip()[-2:] and "0" in check2.get("output", "").strip()[-2:]:
                return True
            time.sleep(0.5)
        self.logger.warning("Probe servers did not start in time")
        return False

    # -- Halite ---------------------------------------------------------------

    def _execute_halite_probe(self, arena: CodeArena) -> str:
        """Run a Halite probe simulation in *arena*.

        Halite bots live in a ``submission/`` directory containing a compiled
        ``main.<ext>``.  We copy the learner's ``probe/`` dir and the target's
        ``submission/`` dir into the arena, detect the language, compile if
        needed, and run the ``halite`` engine binary.

        Returns:
            The probe's main source code (for metadata / debugging).
        """
        from revenge_bench.arenas.halite.halite import (
            MAP_FILE_TYPE_TO_COMPILE,
            MAP_FILE_TYPE_TO_RUN,
        )

        # Copy directories into the probe arena
        arena.environment.execute("rm -rf /probe /target /logs && mkdir -p /probe/submission /target/submission /logs")
        self._copy_dir_to_arena(
            self.learner_agent.environment,
            "/workspace/probe",
            arena,
            "/probe/submission",
        )
        self._copy_dir_to_arena(
            self.target_agent.environment,
            f"/workspace/{self.game.submission}",
            arena,
            "/target/submission",
        )

        # Read probe main file for metadata
        probe_code = self._read_main_source(arena, "/probe/submission")

        # Compile & build run commands
        probe_exec = self._compile_and_get_executable(
            arena, "/probe/submission", MAP_FILE_TYPE_TO_COMPILE, MAP_FILE_TYPE_TO_RUN
        )
        target_exec = self._compile_and_get_executable(
            arena, "/target/submission", MAP_FILE_TYPE_TO_COMPILE, MAP_FILE_TYPE_TO_RUN
        )

        if probe_exec is None or target_exec is None:
            raise RuntimeError(f"Compilation failed — probe: {probe_exec}, target: {target_exec}")

        # Run Halite simulations
        halite_bin = "./environment/halite"
        for _i in range(self.sims_per_probe):
            cmd = f"{halite_bin} --replaydirectory /logs {shlex.quote(probe_exec)} {shlex.quote(target_exec)}"
            arena.environment.execute(cmd, timeout=120)

        # Rename replays so players are labelled "probe" / "target"
        # (Halite names players from argv order: player 1 = probe, player 2 = target)
        return probe_code

    # -- HuskyBench -----------------------------------------------------------

    def _execute_huskybench_probe(self, arena: CodeArena) -> str:
        """Run a HuskyBench (poker) probe simulation in *arena*.

        HuskyBench bots are ``client/player.py`` files that connect to the
        poker engine via ``client/main.py``.  We copy the learner's
        ``probe/client/player.py`` as the probe player and the target's
        ``client/player.py`` as the target, then run the engine with both
        clients.

        Returns:
            The probe source code (``probe/client/player.py`` content).
        """
        from revenge_bench.arenas.huskybench.huskybench import HB_PORT

        # Read probe code from learner container
        probe_file = "/workspace/probe/client/player.py"
        probe_result = self.learner_agent.environment.execute(f"cat {probe_file}")
        if probe_result.get("returncode", 0) != 0:
            raise RuntimeError(f"Failed to read {probe_file} from learner container")
        probe_code = probe_result["output"]

        # Set up player directories in probe arena
        arena.environment.execute("rm -rf /probe /target /app/output/*")
        arena.environment.execute("mkdir -p /probe/client /target/client /app/output")

        # Copy full client directory from target for both players
        self._copy_dir_to_arena(self.target_agent.environment, "/workspace/client", arena, "/probe/client")
        self._copy_dir_to_arena(self.target_agent.environment, "/workspace/client", arena, "/target/client")

        # Replace probe's player.py with the learner's probe code
        self._write_code_to_container(arena, "/probe/client/player.py", probe_code)

        # Build engine command (2 players, sims_per_probe rounds)
        engine_cmd = f"python engine/main.py --port {HB_PORT} --players 2 --sim --sim-rounds {self.sims_per_probe}"
        for arg, val in self.game.game_config.get("args", {}).items():
            if isinstance(val, bool):
                if val:
                    engine_cmd += f" --{arg}"
            else:
                engine_cmd += f" --{arg} {val}"

        script_lines = [
            "#!/bin/bash",
            "rm -rf /app/output/*",
            f"kill -9 $(lsof -ti :{HB_PORT}) 2>/dev/null || true",
            f"{engine_cmd} > /tmp/engine.log 2>&1 &",
            "sleep 0.5",
            f"cd /probe && python client/main.py --port {HB_PORT} > /tmp/probe.log 2>&1 &",
            f"cd /target && python client/main.py --port {HB_PORT} > /tmp/target.log 2>&1 &",
            "wait",
        ]
        self._write_code_to_container(arena, "/workspace/probe_game.sh", "\n".join(script_lines))
        arena.environment.execute(
            "chmod +x /workspace/probe_game.sh; /workspace/probe_game.sh",
            timeout=self.sims_per_probe * 10 + 10,
        )

        # Rewrite playerNames in game logs so parser can find "probe"/"target"
        self._fix_huskybench_probe_player_names(arena)

        return probe_code

    def _fix_huskybench_probe_player_names(self, arena: CodeArena) -> None:
        """Rewrite ``playerNames`` in game_log files for the probe arena.

        Client logs report ``Connected with player ID: X``, and the engine
        auto-names them ``playerX``.  This rewrites the names to ``probe`` /
        ``target`` so the trace parser can identify them.
        """
        map_id_to_name: dict[str, str] = {}
        for name, log_file in [
            ("probe", "/tmp/probe.log"),
            ("target", "/tmp/target.log"),
        ]:
            log_result = arena.environment.execute(f"cat {log_file} 2>/dev/null || true")
            for line in log_result.get("output", "").splitlines():
                if "Connected with player ID: " in line:
                    agent_id = line.strip().split()[-1]
                    map_id_to_name[agent_id] = name
                    break

        if not map_id_to_name:
            self.logger.warning("Could not determine player IDs from probe logs")
            return

        ls_result = arena.environment.execute("ls /app/output/game_log_*.json 2>/dev/null || echo 'NONE'")
        if "NONE" in ls_result.get("output", ""):
            return

        value_to_name = {f"player{aid}": name for aid, name in map_id_to_name.items()}

        for game_log_file in ls_result["output"].strip().split("\n"):
            game_log_file = game_log_file.strip()
            if not game_log_file:
                continue
            cat_result = arena.environment.execute(f"cat {game_log_file}")
            if cat_result.get("returncode", 0) != 0:
                continue
            try:
                data = json.loads(cat_result["output"])
                player_names = data.get("playerNames", {})
                if all(v in value_to_name for v in player_names.values()):
                    data["playerNames"] = {k: value_to_name[v] for k, v in player_names.items()}
                    self._write_code_to_container(arena, game_log_file, json.dumps(data))
            except json.JSONDecodeError:
                continue

    # -- RobotRumble ---------------------------------------------------------

    def _execute_robotrumble_probe(self, arena: CodeArena) -> str:
        """Run a RobotRumble probe simulation in *arena*.

        RobotRumble bots are single-file ``robot.js`` that export a
        ``robot(state, unit)`` function.  We copy the learner's ``probe.js``
        and the target's ``robot.js`` into the arena and run the engine.

        Player order: probe = Blue (arg 1), target = Red (arg 2).

        Returns:
            The probe source code (``probe.js`` content).
        """
        # Read probe code from learner container
        probe_result = self.learner_agent.environment.execute("cat /workspace/probe.js")
        if probe_result.get("returncode", 0) != 0:
            raise RuntimeError("Failed to read probe.js from learner container")
        probe_code = probe_result["output"]

        # Read target code from target container
        submission = self.game.submission  # "robot.js"
        target_result = self.target_agent.environment.execute(f"cat /workspace/{submission}")
        if target_result.get("returncode", 0) != 0:
            raise RuntimeError(f"Failed to read {submission} from target container")
        target_code = target_result["output"]

        # Set up arena container
        arena.environment.execute("rm -rf /probe /target /logs && mkdir -p /probe /target /logs")
        self._write_code_to_container(arena, "/probe/robot.js", probe_code)
        self._write_code_to_container(arena, f"/target/{submission}", target_code)

        # Run simulations: probe (Blue) vs target (Red)
        run_cmd = "./rumblebot run term --raw"
        for arg, val in self.game.game_config.get("args", {}).items():
            if arg == "raw":
                continue  # already added
            if isinstance(val, bool):
                if val:
                    run_cmd += f" --{arg}"
            else:
                run_cmd += f" --{arg} {val}"

        for i in range(self.sims_per_probe):
            cmd = f"{run_cmd} /probe/robot.js /target/{submission} > /logs/sim_{i}.json"
            arena.environment.execute(cmd, timeout=120)

        return probe_code

    def _parse_robotrumble_probe_traces(self, arena: CodeArena, probe_id: int) -> dict[str, Any]:
        """Parse probe traces from RobotRumble ``sim_*.json`` files.

        RobotRumble is multi-unit: each turn has per-unit actions for both
        teams.  Player order in ``_execute_robotrumble_probe``: probe = Blue,
        target = Red.
        """
        try:
            from revenge_bench.traces.parsers.robotrumble import (
                actions_distance,
                extract_player_action,
                extract_player_state,
            )
        except ImportError as e:
            return {
                "error": f"RobotRumble parser not available: {e}",
                "probe_id": probe_id,
            }

        all_pairs: list[dict[str, Any]] = []
        per_simulation: list[dict[str, Any]] = []

        ls_result = arena.environment.execute("ls /logs/sim_*.json 2>/dev/null || echo 'NONE'")
        if "NONE" in ls_result.get("output", ""):
            return {"error": "No simulation files found", "probe_id": probe_id}

        sim_files = [f.strip() for f in ls_result["output"].strip().split("\n") if f.strip()]

        for sim_file in sim_files:
            cat_result = arena.environment.execute(f"cat {sim_file}")
            if cat_result.get("returncode", 0) != 0:
                continue

            try:
                data = json.loads(cat_result["output"])
            except json.JSONDecodeError:
                continue

            turns = data.get("turns", [])
            sim_pairs = []

            for turn_data in turns:
                turn_num = turn_data.get("turn", 0)

                # Extract states and actions for both teams
                target_state = extract_player_state(turn_data, "Red")
                probe_state = extract_player_state(turn_data, "Blue")
                if target_state is None or probe_state is None:
                    continue

                target_action = extract_player_action(turn_data, "Red")
                probe_action = extract_player_action(turn_data, "Blue")
                if target_action is None or probe_action is None:
                    continue

                distance = actions_distance(probe_action, target_action)
                pair = {
                    "turn": turn_num,
                    "probe_action": probe_action,
                    "target_action": target_action,
                    "distance": distance,
                    "target_state": target_state,
                }
                sim_pairs.append(pair)
                all_pairs.append(pair)

            per_simulation.append(
                {
                    "file": sim_file.split("/")[-1],
                    "num_turns": len(sim_pairs),
                }
            )

        return {
            "probe_id": probe_id,
            "description": "probe (Blue) vs target (Red) - showing what each did in same state",
            "total_turns": len(all_pairs),
            "num_simulations": len(per_simulation),
            "per_simulation": per_simulation,
            "pairs": all_pairs,
        }

    # -- RoboCode -------------------------------------------------------------

    def _execute_robocode_probe(self, arena: CodeArena) -> str:
        """Run a RoboCode probe simulation in *arena*.

        RoboCode bots are Java files in ``robots/custom/``.  We copy the
        learner's ``probe/`` directory and the target's ``robots/custom/``
        into the arena under separate package aliases, compile both, and
        run the RoboCode engine.

        Player order: probe = p0, target = p1.

        Returns:
            The probe source code (``probe/MyTank.java`` content).
        """
        from revenge_bench.arenas.robocode.robocode import RC_FILE

        # Read probe code for metadata
        probe_main = f"/workspace/probe/{RC_FILE}"
        probe_result = self.learner_agent.environment.execute(f"cat {probe_main}")
        if probe_result.get("returncode", 0) != 0:
            raise RuntimeError(f"Failed to read {probe_main} from learner container")
        probe_code = probe_result["output"]

        # Set up arena: copy probe and target Java into separate packages
        arena.environment.execute("rm -rf robots/p0 robots/p1 /logs && mkdir -p robots/p0 robots/p1 /logs")

        # Copy probe Java files from learner container
        self._copy_dir_to_arena(
            self.learner_agent.environment,
            "/workspace/probe",
            arena,
            "robots/p0",
        )
        # Copy target Java files from target container
        self._copy_dir_to_arena(
            self.target_agent.environment,
            "/workspace/robots/custom",
            arena,
            "robots/p1",
        )

        # Rewrite package names and compile
        for pkg in ("p0", "p1"):
            arena.environment.execute(f"find robots/{pkg}/ -name '*.java' -exec sed -i 's/custom/{pkg}/g' {{}} +")
            result = arena.environment.execute(f'javac -cp "libs/robocode.jar" robots/{pkg}/*.java')
            if result.get("returncode", 0) != 0:
                raise RuntimeError(f"Compilation failed for {pkg}: {result.get('output', '')}")

        # Run sims_per_probe separate games (1 round each), like other games
        selected = f"p0.{RC_FILE.stem}*,p1.{RC_FILE.stem}*"
        battle_content = (
            "#Battle Properties\n"
            "robocode.battle.numRounds=1\n"
            "robocode.battle.gunCoolingRate=0.1\n"
            "robocode.battle.rules.inactivityTime=450\n"
            "robocode.battle.rules.hideEnemyNames=True\n"
            "robocode.battleField.width=800\n"
            "robocode.battleField.height=600\n"
            f"robocode.battle.selectedRobots={selected}\n"
        )
        create_file_in_container(arena.environment, content=battle_content, dest_path="battles/probe.battle")

        for i in range(self.sims_per_probe):
            cmd = (
                "./robocode.sh -nodisplay -nosound -battle battles/probe.battle"
                f" -results /logs/results_{i}.txt -recordXML /logs/record_{i}.xml"
            )
            result = arena.environment.execute(cmd, timeout=60)
            if result.get("returncode", 0) != 0:
                self.logger.warning(f"RoboCode probe sim {i} returned non-zero: {result.get('output', '')[:300]}")

            check = arena.environment.execute(f"ls -la /logs/record_{i}.xml 2>/dev/null || echo MISSING")
            if "MISSING" in check.get("output", ""):
                self.logger.warning(f"RoboCode probe sim {i} did not produce record_{i}.xml")

        return probe_code

    def _parse_robocode_probe_traces(self, arena: CodeArena, probe_id: int) -> dict[str, Any]:
        """Parse probe traces from RoboCode ``record_*.xml`` files.

        Uses the robocode trace parser to extract state-action pairs.
        Player order: probe = p0, target = p1.
        """
        try:
            from revenge_bench.traces.parsers.robocode import (
                actions_distance,
                extract_state_action_pairs,
            )
        except ImportError as e:
            return {
                "error": f"RoboCode parser not available: {e}",
                "probe_id": probe_id,
            }

        import tempfile

        all_pairs: list[dict[str, Any]] = []
        per_simulation: list[dict[str, Any]] = []

        # List XML recording files
        ls_result = arena.environment.execute("ls /logs/record_*.xml 2>/dev/null || echo 'NONE'")
        if "NONE" in ls_result.get("output", ""):
            self.logger.warning(f"Probe {probe_id}: no record_*.xml in /logs/")
            return {
                "probe_id": probe_id,
                "description": "probe (p0) vs target (p1) — action comparison per tick",
                "total_turns": 0,
                "num_simulations": 0,
                "per_simulation": [],
                "pairs": [],
            }

        sim_files = [f.strip() for f in ls_result["output"].strip().split("\n") if f.strip()]

        for sim_file in sim_files:
            # Copy XML to host for parsing (too large for cat)
            with tempfile.TemporaryDirectory() as tmp:
                local_xml = Path(tmp) / "record.xml"
                copy_from_container(arena.environment, sim_file, str(local_xml))

                if not local_xml.exists():
                    self.logger.warning(f"Probe {probe_id}: copy_from_container failed for {sim_file}")
                    continue

                file_size = local_xml.stat().st_size
                if file_size == 0:
                    self.logger.warning(f"Probe {probe_id}: {sim_file} copied as empty file")
                    continue

                sim_pairs = []

                # Extract pairs for both probe (p0) and target (p1)
                try:
                    target_pairs = extract_state_action_pairs(local_xml, "p1")
                    probe_pairs = extract_state_action_pairs(local_xml, "p0")
                except Exception as e:
                    self.logger.warning(f"Error parsing {sim_file}: {e}")
                    continue

                if not target_pairs and not probe_pairs:
                    self.logger.warning(
                        f"Probe {probe_id}: {sim_file} parsed but 0 pairs for both p0 and p1 ({file_size} bytes)"
                    )

                # Align by turn — both lists should have pairs for the same turns
                target_by_tick = {s.get("tick", i): (s, a) for i, (s, a) in enumerate(target_pairs)}
                probe_by_tick = {s.get("tick", i): (s, a) for i, (s, a) in enumerate(probe_pairs)}

                for tick in sorted(set(target_by_tick) & set(probe_by_tick)):
                    target_state, target_action = target_by_tick[tick]
                    _, probe_action = probe_by_tick[tick]

                    distance = actions_distance(probe_action, target_action)
                    pair = {
                        "turn": tick,
                        "probe_action": probe_action,
                        "target_action": target_action,
                        "distance": round(distance, 4),
                        "target_state": target_state,
                    }
                    sim_pairs.append(pair)
                    all_pairs.append(pair)

                per_simulation.append(
                    {
                        "file": sim_file.split("/")[-1],
                        "num_turns": len(sim_pairs),
                    }
                )

        return {
            "probe_id": probe_id,
            "description": "probe (p0) vs target (p1) — action comparison per tick",
            "total_turns": len(all_pairs),
            "num_simulations": len(per_simulation),
            "per_simulation": per_simulation,
            "pairs": all_pairs,
        }

    # -- Helpers for compiled-language arenas ----------------------------------

    def _copy_dir_to_arena(self, src_env, src_dir: str, arena: CodeArena, dest_dir: str) -> None:
        """Copy contents of *src_dir* from *src_env* container into *dest_dir* in the probe *arena*.

        Uses the host filesystem as an intermediary via copy_from/to_container.
        The ``/.`` suffix copies directory *contents* (not the dir itself),
        avoiding the nesting issue that copy_between_containers causes.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            local_dir = Path(tmp) / "transfer"
            copy_from_container(src_env, f"{src_dir}/.", str(local_dir))
            copy_to_container(arena.environment, str(local_dir) + "/.", dest_dir)

    def _read_main_source(self, arena: CodeArena, sub_dir: str) -> str:
        """Read the main source file from a submission directory in the arena."""
        # Find main.* file
        ls_result = arena.environment.execute(f"ls {sub_dir}")
        files = ls_result["output"].strip().splitlines()
        main_files = [f for f in files if f.startswith("main.")]
        if not main_files:
            # Check Rust layout: src/main.rs
            src_ls = arena.environment.execute(f"ls {sub_dir}/src 2>/dev/null")
            if "main.rs" in src_ls.get("output", ""):
                main_files = ["src/main.rs"]
        if not main_files:
            return "(main file not found)"
        cat_result = arena.environment.execute(f"cat {sub_dir}/{main_files[0]}")
        return cat_result.get("output", "")

    def _compile_and_get_executable(
        self,
        arena: CodeArena,
        sub_dir: str,
        compile_map: dict[str, str],
        run_map: dict[str, str],
    ) -> str | None:
        """Compile a submission in *sub_dir* and return the executable command.

        Returns ``None`` if compilation fails or no supported main file is found.
        """
        ls_result = arena.environment.execute(f"ls {sub_dir}")
        files = ls_result["output"].strip().splitlines()
        main_files = [f for f in files if f.startswith("main.") and Path(f).suffix in run_map]

        if not main_files:
            # Rust: src/main.rs
            src_ls = arena.environment.execute(f"ls {sub_dir}/src 2>/dev/null")
            if "main.rs" in src_ls.get("output", ""):
                main_files = ["src/main.rs"]

        if not main_files:
            self.logger.error(f"No supported main file in {sub_dir}: {files}")
            return None

        ext = Path(main_files[0]).suffix

        # Compile if needed
        if ext in compile_map:
            compile_cmd = compile_map[ext].format(name="main")
            result = arena.environment.execute(compile_cmd, timeout=30, cwd=sub_dir)
            if result.get("returncode", 0) != 0:
                self.logger.error(f"Compilation failed in {sub_dir}: {result.get('output', '')}")
                return None

        return run_map[ext].format(path=sub_dir, name="main")

    # -- Common helpers -------------------------------------------------------

    def _write_probe_to_learner_container(self, traces: dict[str, Any], probe_id: int) -> str:
        """Write probe results to a file in the learner container and return a notification."""
        json_content = json.dumps(traces, indent=2)
        json_bytes = len(json_content.encode("utf-8"))
        num_pairs = len(traces.get("pairs", []))
        num_sims = traces.get("num_simulations", 0)

        round_num = getattr(self, "current_round", 0)
        round_probe_num = traces.get("round_probe_number", probe_id)
        filename = f"probe_trace_r{round_num}_p{round_probe_num}.json"
        filepath = str(DIR_WORK / filename)

        try:
            create_file_in_container(
                self.learner_agent.environment,
                content=json_content,
                dest_path=filepath,
            )
        except Exception as e:
            self.logger.error(f"Failed to write probe results to {filepath}: {e}")
            return json.dumps(traces, indent=2)

        self.logger.info(f"Wrote probe results to {filepath} ({json_bytes:,} bytes)")

        return f"""Probe results written to: {filepath}
Size: {json_bytes:,} bytes | {num_pairs} pairs captured | {num_sims} simulations

IMPORTANT: This file may exceed your context window. Use commands to explore:
  head -n 100 {filepath}                    # First 100 lines
  cat {filepath} | jq '.pairs | length'     # Count pairs
  cat {filepath} | jq '.pairs[:5]'          # First 5 pairs (sample)
  cat {filepath} | jq '.pairs[-5:]'         # Last 5 pairs
  cat {filepath} | jq '.pairs[] | select(.distance > 0)'  # Nonzero distances only"""

    def _write_code_to_container(self, arena: CodeArena, path: str, code: str) -> None:
        """Write a single source file to the arena container."""
        create_file_in_container(arena.environment, content=code, dest_path=path)

    # =========================================================================
    # Probe Trace Parsing
    # =========================================================================

    def _parse_probe_traces_from_arena(self, arena: CodeArena, probe_id: int) -> dict[str, Any]:
        """
        Parse probe traces from the probe arena container.

        Dispatches to game-specific parsing methods based on self.game.name.

        Returns dict with:
        - probe_id: ID of this probe
        - total_turns: Total state-action pairs captured
        - pairs: List of {turn, probe_action, target_action, distance, target_state}
        """
        game_name = self.game.name
        if game_name == "BattleSnake":
            return self._parse_battlesnake_probe_traces(arena, probe_id)
        elif game_name == "Halite":
            return self._parse_halite_probe_traces(arena, probe_id)
        elif game_name == "HuskyBench":
            return self._parse_huskybench_probe_traces(arena, probe_id)
        elif game_name == "RobotRumble":
            return self._parse_robotrumble_probe_traces(arena, probe_id)
        elif game_name == "RoboCode":
            return self._parse_robocode_probe_traces(arena, probe_id)
        else:
            return {
                "error": f"Probe trace parsing not supported for {game_name}",
                "probe_id": probe_id,
            }

    def _parse_battlesnake_probe_traces(self, arena: CodeArena, probe_id: int) -> dict[str, Any]:
        """Parse probe traces from BattleSnake sim_*.jsonl files."""
        try:
            from revenge_bench.traces.parsers.battlesnake import (
                actions_distance,
                extract_player_action,
                extract_player_state,
            )
        except ImportError as e:
            return {"error": f"Parser not available: {e}", "probe_id": probe_id}

        all_pairs: list[dict[str, Any]] = []
        per_simulation: list[dict[str, Any]] = []

        # List simulation files in arena
        ls_result = arena.environment.execute("ls /logs/*.jsonl 2>/dev/null || echo 'NONE'")
        if "NONE" in ls_result.get("output", ""):
            return {"error": "No simulation files found", "probe_id": probe_id}

        sim_files = [f.strip() for f in ls_result["output"].strip().split("\n") if f.strip()]

        for sim_file in sim_files:
            # Read file content from container
            cat_result = arena.environment.execute(f"cat {sim_file}")
            if cat_result.get("returncode", 0) != 0:
                continue

            content = cat_result["output"]
            lines = content.strip().split("\n")

            # Parse turns
            turns = []
            for line in lines:
                try:
                    turn_data = json.loads(line)
                    if "board" in turn_data:
                        turns.append(turn_data)
                except json.JSONDecodeError:
                    continue

            sim_pairs = []
            for i in range(len(turns) - 1):
                turn_data = turns[i]
                next_turn_data = turns[i + 1]
                turn_num = turn_data.get("turn", i)

                target_state = extract_player_state(turn_data, "target")
                probe_state = extract_player_state(turn_data, "probe")

                if target_state is None or probe_state is None:
                    continue

                target_action = extract_player_action(turn_data, next_turn_data, "target")
                probe_action = extract_player_action(turn_data, next_turn_data, "probe")

                if target_action is None or probe_action is None:
                    continue

                distance = actions_distance(probe_action, target_action)
                pair = {
                    "turn": turn_num,
                    "probe_action": probe_action,
                    "target_action": target_action,
                    "distance": distance,
                    "target_state": target_state,
                }
                sim_pairs.append(pair)
                all_pairs.append(pair)

            per_simulation.append(
                {
                    "file": sim_file.split("/")[-1],
                    "num_turns": len(sim_pairs),
                }
            )

        return {
            "probe_id": probe_id,
            "description": "probe vs target - showing what each did in same state",
            "total_turns": len(all_pairs),
            "num_simulations": len(per_simulation),
            "per_simulation": per_simulation,
            "pairs": all_pairs,
        }

    def _parse_halite_probe_traces(self, arena: CodeArena, probe_id: int) -> dict[str, Any]:
        """Parse probe traces from Halite .hlt replay files."""
        try:
            from revenge_bench.traces.parsers.halite import (
                actions_distance,
                extract_player_state,
            )
        except ImportError as e:
            return {"error": f"Halite parser not available: {e}", "probe_id": probe_id}

        all_pairs: list[dict[str, Any]] = []
        per_simulation: list[dict[str, Any]] = []

        # List .hlt replay files
        ls_result = arena.environment.execute("ls /logs/*.hlt 2>/dev/null || echo 'NONE'")
        if "NONE" in ls_result.get("output", ""):
            return {"error": "No replay files found", "probe_id": probe_id}

        sim_files = [f.strip() for f in ls_result["output"].strip().split("\n") if f.strip()]

        for sim_file in sim_files:
            cat_result = arena.environment.execute(f"cat {sim_file}")
            if cat_result.get("returncode", 0) != 0:
                continue

            try:
                data = json.loads(cat_result["output"])
            except json.JSONDecodeError:
                continue

            player_names = data.get("player_names", [])
            if len(player_names) < 2:
                continue

            # Halite bots self-identify (e.g. "MyCBot", "ImprovedBotV2"),
            # not as "probe"/"target".  The probe is always player 1 (argv
            # order in _execute_halite_probe) and the target is player 2.
            probe_tag = 1  # 1-based
            target_tag = 2

            frames = data.get("frames", [])
            moves = data.get("moves", [])
            height = data.get("height", 0)
            width = data.get("width", 0)

            sim_pairs = []
            for turn_idx in range(len(moves)):
                frame = frames[turn_idx]
                move_grid = moves[turn_idx]

                # Extract per-cell actions for each player
                probe_action = []
                target_action = []
                for r in range(height):
                    for c in range(width):
                        owner = frame[r][c][0]
                        move = move_grid[r][c]
                        if owner == probe_tag:
                            probe_action.append([r, c, move])
                        elif owner == target_tag:
                            target_action.append([r, c, move])

                probe_action.sort()
                target_action.sort()

                state = extract_player_state(frame, turn_idx, target_tag, data)
                distance = actions_distance(probe_action, target_action)

                pair = {
                    "turn": turn_idx,
                    "probe_action": probe_action,
                    "target_action": target_action,
                    "distance": distance,
                    "target_state": state,
                }
                sim_pairs.append(pair)
                all_pairs.append(pair)

            per_simulation.append(
                {
                    "file": sim_file.split("/")[-1],
                    "num_turns": len(sim_pairs),
                }
            )

        return {
            "probe_id": probe_id,
            "description": "probe vs target - showing what each did in same state",
            "total_turns": len(all_pairs),
            "num_simulations": len(per_simulation),
            "per_simulation": per_simulation,
            "pairs": all_pairs,
        }

    def _parse_huskybench_probe_traces(self, arena: CodeArena, probe_id: int) -> dict[str, Any]:
        """Parse probe traces from HuskyBench ``game_log_*.json`` files.

        Poker is sequential — players alternate instead of acting simultaneously.
        Each pair represents a single player's decision with the full reconstructed
        game state at that point.  Use ``jq '.pairs[] | select(.player=="target")'``
        to view only the target's behaviour.
        """
        try:
            from revenge_bench.traces.parsers.huskybench import (
                ROUND_NAMES,
                _reconstruct_state_at_action,
                normalize_action,
            )
        except ImportError as e:
            return {
                "error": f"HuskyBench parser not available: {e}",
                "probe_id": probe_id,
            }

        all_pairs: list[dict[str, Any]] = []
        per_simulation: list[dict[str, Any]] = []

        ls_result = arena.environment.execute("ls /app/output/game_log_*.json 2>/dev/null || echo 'NONE'")
        if "NONE" in ls_result.get("output", ""):
            return {"error": "No game log files found", "probe_id": probe_id}

        sim_files = [f.strip() for f in ls_result["output"].strip().split("\n") if f.strip()]

        for hand_idx, sim_file in enumerate(sim_files):
            cat_result = arena.environment.execute(f"cat {sim_file}")
            if cat_result.get("returncode", 0) != 0:
                continue

            try:
                hand_data = json.loads(cat_result["output"])
            except json.JSONDecodeError:
                continue

            player_names = hand_data.get("playerNames", {})
            rounds_data = hand_data.get("rounds", {})
            hand_pairs: list[dict[str, Any]] = []

            for round_key in sorted(rounds_data.keys(), key=int):
                round_idx = int(round_key)
                round_data = rounds_data[round_key]
                action_sequence = round_data.get("action_sequence", [])

                for action_idx, seq_action in enumerate(action_sequence):
                    acting_pid = str(seq_action.get("player", ""))
                    acting_name = player_names.get(acting_pid, f"player{acting_pid}")

                    state = _reconstruct_state_at_action(
                        hand_data=hand_data,
                        action_idx=action_idx,
                        round_idx=round_idx,
                        player_id=acting_pid,
                        player_name=acting_name,
                        hand_number=hand_idx,
                    )

                    raw_action = seq_action.get("action", "")
                    amount = seq_action.get("amount", 0)
                    my_stack = state["my_stack"]

                    if raw_action.upper() == "RAISE":
                        action = normalize_action(
                            {"action": raw_action, "amount": amount},
                            player_stack=my_stack,
                        )
                    else:
                        action = normalize_action(raw_action)

                    hand_pairs.append(
                        {
                            "hand": hand_idx,
                            "round": ROUND_NAMES.get(round_idx, f"round_{round_idx}"),
                            "player": acting_name,
                            "action": action,
                            "state": state,
                        }
                    )

            all_pairs.extend(hand_pairs)
            per_simulation.append(
                {
                    "file": sim_file.split("/")[-1],
                    "num_actions": len(hand_pairs),
                }
            )

        return {
            "probe_id": probe_id,
            "description": "probe vs target poker hands — each entry is one player's decision with full game state",
            "total_turns": len(all_pairs),
            "num_simulations": len(per_simulation),
            "per_simulation": per_simulation,
            "pairs": all_pairs,
        }


# Register the tournament type
def get_tournament_class(tournament_type: str):
    """Get tournament class by type name."""
    if tournament_type == "interventionist":
        return InverseStrategyInterventionistTournament
    elif tournament_type == "observational" or tournament_type == "inverse" or tournament_type == "offline":
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        return InverseStrategyTournament
    else:
        raise ValueError(f"Unknown tournament type: {tournament_type}")
