import json
import re
import subprocess

from revenge_bench.agents.player import Player
from revenge_bench.arenas.arena import CodeArena, RoundStats
from revenge_bench.constants import DIR_WORK
from revenge_bench.utils.environment import create_file_in_container

HB_LOG_ENGINE = "engine.log"
HB_PORT = 8000
HB_REGEX_SCORE = re.compile(r"Player\s(\d+)\sdelta\supdated\:[\d\s\-\+\=]+,\smoney\:\s\d+\s\-\>\s(\d+)")
HB_SCRIPT = "run_game.sh"
HB_BOT_TIMEOUT = 10  # Max time (seconds) for a bot to run a single round
HB_OUTPUT_DIRS = ["/app/output", "output", "/workspace/output"]


class HuskyBenchArena(CodeArena):
    name: str = "HuskyBench"
    description: str = f"""In this game, you will write code to control a poker-playing bot, aiming to outsmart your opponents and win chips.
Victory comes from crafting clever strategies—bluffing, reading opponents, and managing your chip stack effectively.
Be mindful of your bot's efficiency - your code should complete a simulation within 10 seconds to avoid forfeiting the round.
You can use {HB_SCRIPT} to check if your bot runs in time."""
    submission: str = "client/player.py"

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.num_players: int = len(config["players"])
        self.run_engine: str = (
            f"python engine/main.py --port {HB_PORT} --players {self.num_players} "
            f"--sim --sim-rounds {self.game_config['sims_per_round']}"
        )
        # Game timeout is number of sims * bot timeout
        self.timeout = self.game_config["sims_per_round"] * HB_BOT_TIMEOUT
        for arg, val in self.game_config.get("args", self.default_args).items():
            if isinstance(val, bool):
                if val:
                    self.run_engine += f" --{arg}"
            else:
                self.run_engine += f" --{arg} {val}"

    def _construct_game_script(
        self,
        agents: list[Player],
        run_client: str,
        run_engine: str,
        verbose: bool = False,
        log_outputs: bool = False,
    ) -> None:
        if verbose:
            self.logger.debug(f"Starting game engine with command: {run_engine}")
        script = [
            "#!/bin/bash",
            # HuskyBench writes to /app/output in Docker and output/ in local-like runtimes.
            # Clean both locations so each round starts with fresh traces.
            f"for out_dir in {' '.join(HB_OUTPUT_DIRS)}; do",
            "  if [ -d \"$out_dir\" ]; then",
            "    find \"$out_dir\" -mindepth 1 -maxdepth 1 -type f -delete",
            "  fi",
            "done",
            f"kill -9 $(lsof -ti :{HB_PORT})",  # Kill previous game if any
            run_engine,  # Start engine
            "sleep 0.5",  # Give engine a moment to start
        ]
        for agent in agents:
            # Start each agent in background, redirecting output to log file
            _run_client = run_client.format(agent=agent, port=HB_PORT, log_dir=self.log_env)
            if verbose:
                self.logger.debug(f"Starting agent {agent.name} with command: {_run_client}")
            script.append(_run_client)
        script.append("wait")
        if log_outputs:
            # Move any generated traces/logs from all known HuskyBench output roots.
            script.extend(
                [
                    f"for out_dir in {' '.join(HB_OUTPUT_DIRS)}; do",
                    "  if [ -d \"$out_dir\" ]; then",
                    f"    find \"$out_dir\" -mindepth 1 -maxdepth 1 -type f -exec mv -f {{}} {self.log_env}/ \\;",
                    "  fi",
                    "done",
                ]
            )
        return "\n".join(script)

    def execute_round(self, agents: list[Player]):
        # Use placeholders compatible with str.format; compute log dir separately
        run_client = "cd /{agent.name} && python client/main.py --port {port} > {log_dir}/{agent.name}.log 2>&1 &"
        # Patch sim-rounds to match current sims_per_round (may differ from
        # the value baked into self.run_engine during multi-opponent mode).
        cur_sims = self.game_config["sims_per_round"]
        engine_cmd = re.sub(r"--sim-rounds \d+", f"--sim-rounds {cur_sims}", self.run_engine)
        # Patch --players to match actual agent count (config may list more
        # players than participate in the game, e.g. inverse-strategy learner).
        engine_cmd = re.sub(r"--players \d+", f"--players {len(agents)}", engine_cmd)
        run_engine = f"{engine_cmd} > {self.log_env / HB_LOG_ENGINE} 2>&1 &"
        script = self._construct_game_script(agents, run_client, run_engine, verbose=True, log_outputs=True)
        self.logger.info(f"Executing game script:\n{script}")
        create_file_in_container(container=self.environment, content=script, dest_path=DIR_WORK / HB_SCRIPT)
        self.logger.info(f"Running game script: ./{HB_SCRIPT}")
        self.environment.execute(f"chmod +x {HB_SCRIPT}; ./{HB_SCRIPT}", timeout=max(cur_sims * HB_BOT_TIMEOUT, self.timeout))

    def get_results(self, agents: list[Player], round_num: int, stats: RoundStats):
        map_id_to_agent: dict[str, str] = {}
        for agent in agents:
            log_path = self.log_round(round_num) / f"{agent.name}.log"
            if not log_path.exists():
                continue
            with open(log_path) as f:
                for line in f:
                    if "Connected with player ID: " in line:
                        agent_id = line.strip().split()[-1]
                        map_id_to_agent[agent_id] = agent.name
                        break
        self.logger.info("Agent IDs: " + str(map_id_to_agent))

        with open(self.log_round(round_num) / HB_LOG_ENGINE) as f:
            score_updates = [
                (match.group(1), int(match.group(2))) for l in f.readlines() if (match := HB_REGEX_SCORE.search(l))
            ]
            map_id_to_score = {k: v for k, v in score_updates[-len(agents) :]}
        self.logger.info("Final Scores: " + str(map_id_to_score))
        scores = {
            map_id_to_agent[agent_id]: score
            for agent_id, score in map_id_to_score.items()
            if agent_id in map_id_to_agent
        }

        # Empty-scores recovery: the engine produced no score updates, or none
        # of the connected agent IDs match. Attribute the loss to whichever
        # agent failed to connect; if attribution is impossible, call it a Tie.
        if not scores:
            connected = set(map_id_to_agent.values())
            all_names = {agent.name for agent in agents}
            not_connected = all_names - connected

            if connected and not_connected:
                # Some connected, some did not — the unconnected agents lost.
                for name in connected:
                    scores[name] = 1
                for name in not_connected:
                    scores[name] = 0
                # 2-agent attribution rule: if exactly one connected, that
                # agent wins. For 3+ agents we don't have a defined rule, so
                # fall back to deterministic alphabetical-first to avoid
                # silent non-determinism.
                if len(connected) == 1:
                    stats.winner = next(iter(connected))
                else:
                    stats.winner = sorted(connected)[0]
                self.logger.warning(
                    f"Round {round_num}: Game produced no engine scores; "
                    f"agents {sorted(not_connected)} failed to connect and "
                    f"are credited a loss; agents {sorted(connected)} are "
                    f"credited a win."
                )
            else:
                # Either nobody connected or everybody connected but no scores —
                # fault is unattributable.
                for agent in agents:
                    scores[agent.name] = 0
                stats.winner = "Tie"
                self.logger.warning(
                    f"Round {round_num}: Game produced no engine scores and "
                    f"fault is unattributable; counting as Tie with zero scores."
                )
        else:
            stats.winner = max(scores, key=scores.get)

        stats.scores = scores
        for player, score in scores.items():
            stats.player_stats[player].score = score

        # Post-process game logs: replace auto-generated player names with
        # actual agent names so offline evaluation can match by name.
        # Client logs report "Connected with player ID: X" where X matches the
        # auto-generated name "playerX" in game_log playerNames values.
        agent_id_to_name = {aid: name for aid, name in map_id_to_agent.items()}
        round_dir = self.log_round(round_num)
        for game_log_file in round_dir.glob("game_log_*.json"):
            with open(game_log_file) as f:
                data = json.load(f)
            player_names = data.get("playerNames", {})
            # Match by value: game_log has "playerX" where X is the agent_id
            value_to_agent = {f"player{aid}": name for aid, name in agent_id_to_name.items()}
            if all(v in value_to_agent for v in player_names.values()):
                data["playerNames"] = {k: value_to_agent[v] for k, v in player_names.items()}
                with open(game_log_file, "w") as f:
                    json.dump(data, f)

    def validate_code(self, agent: Player) -> tuple[bool, str | None]:
        assets = agent.environment.execute("ls client")["output"]
        if "main.py" not in assets:
            return False, "There should be a `client/main.py` file"
        if "player.py" not in assets:
            return False, "There should be a `client/player.py` file"

        # Make sure bot can run (check against itself)
        # Use regex so the replace works even when sims_per_round has been
        # temporarily overridden by _run_multi_opponent_sim.
        run_engine = re.sub(r"--sim-rounds \d+", "--sim-rounds 1", self.run_engine)
        # Override --players to 2 for validation (agent plays against itself).
        run_engine = re.sub(r"--players \d+", "--players 2", run_engine) + " &"
        run_client = "python client/main.py --port {port} &"
        script = self._construct_game_script([agent, agent], run_client, run_engine, verbose=False)
        self.logger.info(f"Validating agent {agent.name} with script:\n{script}")
        create_file_in_container(container=agent.environment, content=script, dest_path=DIR_WORK / HB_SCRIPT)
        try:
            agent.environment.execute(f"chmod +x {HB_SCRIPT}; ./{HB_SCRIPT}", timeout=HB_BOT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return (
                False,
                f"Your submission did not successfully complete a single round of poker within "
                f"the {HB_BOT_TIMEOUT} second time limit.\n\n"
                "Please reduce your bot's computation time. "
                "It might also be possible that your code has compilation errors.\n\n"
                f"Validation command run: `./{HB_SCRIPT}`",
            )
        return True, None
