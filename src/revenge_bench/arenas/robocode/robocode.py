import inspect
import json
import random
import re
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm.auto import tqdm

from revenge_bench.agents.player import Player
from revenge_bench.arenas.arena import CodeArena, RoundStats
from revenge_bench.constants import RESULT_TIE
from revenge_bench.utils.environment import create_file_in_container

RC_FILE = Path("MyTank.java")
SIMS_PER_RUN = 10


class RoboCodeArena(CodeArena):
    name: str = "RoboCode"
    description: str = f"""Robocode (Tank Royale) is a programming game where your code is the tank: each turn your bot sends intents—speed plus body/gun/radar turn rates and firepower—based on the game state it perceives via radar.
Your program decides how to move, aim, and fire in a deterministic, turn-based arena to outlast other bots.
Your bot logic must be written in Java and located in the `robots/custom/` directory.
Keep the main bot class named `{str(RC_FILE)}`, but you can include additional Java files if you'd like."""
    default_args: dict = {
        "nodisplay": True,
        "nosound": True,
    }
    submission: str = "robots/custom/"

    def _build_docker_image(self):
        # The RoboCode Dockerfile's `COPY main_seed.py ...` needs the arena
        # folder as build context, not the repo root (the base class default).
        result = subprocess.run(
            f"docker images -q {self.image_name}",
            shell=True, capture_output=True, text=True,
        )
        if result.stdout.strip():
            self.logger.debug(f"Container {self.image_name} exists")
            return

        self.logger.info(
            f"Building Docker image {self.image_name}. This may take 1-5 minutes."
        )
        arena_folder = Path(inspect.getfile(self.__class__)).parent
        result = subprocess.run(
            f"docker build --no-cache -t {self.image_name} "
            f"-f {arena_folder / self.name}.Dockerfile .",
            shell=True, capture_output=True, text=True,
            cwd=str(arena_folder),
        )
        if result.returncode == 0:
            self.logger.info(f"Built Docker image {self.image_name}")
        else:
            self.logger.error(
                f"Failed to build Docker image: {result.stderr}\n{result.stdout}{result.stderr}"
            )
            raise RuntimeError(f"Failed to build Docker image: {result.stderr}")

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.run_cmd_round: str = "./robocode.sh"
        for arg, val in self.game_config.get("args", self.default_args).items():
            if isinstance(val, bool):
                if val:
                    self.run_cmd_round += f" -{arg}"
            else:
                self.run_cmd_round += f" -{arg} {val}"

    def _get_battle_config(self, num_rounds: int | None = None) -> str:
        default_battle_config = {
            "battle": {
                "numRounds": num_rounds if num_rounds is not None else SIMS_PER_RUN,
                "gunCoolingRate": 0.1,
                "rules": {"inactivityTime": 450, "hideEnemyNames": True},
            },
            "battleField": {"width": 800, "height": 600},
        }
        user_battle_config = self.game_config.get("battle", {})

        def merge_dicts(default, user):
            for key, value in user.items():
                if isinstance(value, dict) and key in default:
                    merge_dicts(default[key], value)
                else:
                    default[key] = value

        merge_dicts(default_battle_config, user_battle_config)

        # Turn battle config dict into strings
        battle_lines = ["#Battle Properties"]

        def dict_to_lines(d, prefix=""):
            for key, value in d.items():
                if isinstance(value, dict):
                    dict_to_lines(value, prefix + key + ".")
                else:
                    battle_lines.append(f"robocode.{prefix}{key}={value}")

        dict_to_lines(default_battle_config)
        return "\n".join(battle_lines)

    def _run_single_simulation(self, agents: list[Player], idx: int, cmd: str) -> str:
        rc_results = self.log_env / f"results_{idx}.txt"
        rc_record = self.log_env / f"record_{idx}.xml"
        cmd = f"{cmd} -results {rc_results}"
        if random.random() < self.game_config.get("record_ratio", 1):
            # Only record a fraction of simulations to save space
            cmd = f"{cmd} -recordXML {rc_record}"
        try:
            output = self.environment.execute(cmd, timeout=120)
        except subprocess.TimeoutExpired:
            self.logger.warning(f"RoboCode simulation {idx} timed out: {cmd}")
            return ""
        if output["returncode"] != 0:
            self.logger.warning(
                f"RoboCode simulation {idx} failed with exit code {output['returncode']}:\n{output['output']}"
            )
        return output["output"]

    def execute_round(self, agents: list[Player]):
        # Use short package aliases (p0, p1, …) to stay within Robocode's
        # 32-character package-name limit.  Map them back in get_results().
        self._pkg_to_agent: dict[str, str] = {}
        for i, agent in enumerate(agents):
            pkg = f"p{i}"
            self._pkg_to_agent[pkg] = agent.name
            # Copy the agent codebase into the game codebase and compile it
            for cmd in [
                f"mkdir -p robots/{pkg}",
                f"cp -r /{agent.name}/robots/custom/* robots/{pkg}/",
                f"find robots/{pkg}/ -name '*.java' -exec sed -i 's/custom/{pkg}/g' {{}} +",
                f'javac -cp "libs/robocode.jar" robots/{pkg}/*.java',
            ]:
                self.environment.execute(cmd)

        # Create .battle file — 1 round per invocation (like other games)
        selected_robots = ",".join([f"{pkg}.{RC_FILE.stem}*" for pkg in self._pkg_to_agent])
        battle_file = f"{self.game_id}-battle{int(time.time())}.battle"
        num_sims = self.game_config.get("sims_per_round", 1)
        battle_content = f"""#Battle Properties
{self._get_battle_config(num_rounds=1)}
robocode.battle.selectedRobots={selected_robots}
"""
        create_file_in_container(self.environment, content=battle_content, dest_path=f"battles/{battle_file}")

        # Run one engine invocation per sim, each producing its own file
        cmd = f"{self.run_cmd_round} -battle {battle_file}"
        self.logger.info(f"Running game: {cmd}")
        with ThreadPoolExecutor(5) as executor:
            futures = [
                executor.submit(self._run_single_simulation, agents, idx, cmd)
                for idx in range(num_sims)
            ]

            # Collect results as they complete
            for future in tqdm(as_completed(futures), total=len(futures)):
                future.result()

        # Persist package-to-agent mapping so the trace processor can resolve
        # short aliases (p0, p1) back to real agent names (target, opponent).
        mapping_content = json.dumps(self._pkg_to_agent)
        create_file_in_container(
            self.environment, content=mapping_content,
            dest_path=str(self.log_env / "_pkg_to_agent.json"),
        )

    def get_results(self, agents: list[Player], round_num: int, stats: RoundStats):
        pkg_to_agent = getattr(self, "_pkg_to_agent", {})
        scores = defaultdict(int)
        for idx in range(self.game_config.get("sims_per_round", 1)):
            results_path = self.log_round(round_num) / f"results_{idx}.txt"
            if not results_path.exists():
                self.logger.warning(f"Results file missing: {results_path}")
                continue
            result_output = results_path.read_text()
            lines = result_output.strip().split("\n")

            for line in lines:
                line = line.strip()
                if not re.match(r"^\d", line):
                    continue
                match = re.search(r"(\d+)\S+\:\s(\S+)\s+(\d+)", line)
                if match:
                    pkg_name = match.group(2).rsplit(".", 1)[0]
                    # Map short alias back to the real agent name
                    player = pkg_to_agent.get(pkg_name, pkg_name)
                    scores[player] += int(match.group(3))

        if not scores:
            self.logger.warning("No scores parsed from results files — treating as tie")
            stats.winner = RESULT_TIE
        else:
            stats.winner = max(scores, key=scores.get)
        stats.scores = scores
        for player, score in scores.items():
            stats.player_stats[player].score = score

    def validate_code(self, agent: Player) -> tuple[bool, str | None]:
        if "robots" not in agent.environment.execute("ls")["output"]:
            return False, "There should be a `robots/` directory"
        if "custom" not in agent.environment.execute("ls robots")["output"]:
            return False, "There should be a `robots/custom/` directory"
        if str(RC_FILE) not in agent.environment.execute("ls robots/custom")["output"]:
            return False, (
                f"There should be a `robots/custom/{RC_FILE}` file. "
                f"You can include additional files, but the primary tank logic must be in `robots/custom/{RC_FILE}`"
            )
        response = agent.environment.execute('javac -cp "libs/robocode.jar" robots/custom/*.java')
        if response["returncode"] != 0:
            return False, f"Compilation error:\n{response['output']}"
        if f"{RC_FILE.stem}.class" not in agent.environment.execute("ls robots/custom")["output"]:
            return False, f"`{RC_FILE.stem}.class` not found after compilation"
        return True, None
