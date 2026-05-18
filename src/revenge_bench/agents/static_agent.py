"""Static agent that uses pre-existing code from extracted strategies."""

from pathlib import Path

from minisweagent.environments.docker import DockerEnvironment

from revenge_bench.agents.player import Player
from revenge_bench.game_context import GameContext
from revenge_bench.utils.environment import create_file_in_container

# Map game types to their file extension and destination in Docker container
GAME_FILE_CONFIG = {
    "BattleSnake": {"ext": ".py", "dest": "/workspace/main.py"},
    "CoreWar": {"ext": ".red", "dest": "/workspace/warrior.red"},
    "Halite": {"ext": ".c", "dest": "/workspace/submission/main.c"},
    "HuskyBench": {"ext": ".py", "dest": "/workspace/client/player.py"},
    "RoboCode": {
        "ext": ".java",
        "dest": "/workspace/robots/custom/",
    },  # Special: copy all .java files
    "RobotRumble": {"ext": ".js", "dest": "/workspace/robot.js"},
}


class Static(Player):
    """A player that uses pre-written code instead of generating it.

    Copies the pre-written code during initialization so it's ready for round 0.
    """

    def __init__(
        self,
        config: dict,
        environment: DockerEnvironment,
        game_context: GameContext,
    ) -> None:
        super().__init__(config, environment, game_context)

        # Copy code immediately during init so it's ready for round 0
        self._copy_strategy_code()

    def _copy_strategy_code(self):
        """Copy the pre-written code to the container."""
        agent_args = self.config.get("args", {})
        source_path = agent_args.get("source_path")

        if not source_path:
            raise ValueError(f"static agent {self.name!r}: `args.source_path` is required")

        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(
                f"static agent {self.name!r}: source_path does not exist: {source} "
                f"(resolved from {source_path!r}, cwd {Path.cwd()})"
            )

        # Determine game type from game_context
        game_name = self.game_context.name
        file_config = GAME_FILE_CONFIG.get(game_name, GAME_FILE_CONFIG["BattleSnake"])

        # Handle special case for RoboCode (copy all .java files)
        if game_name == "RoboCode":
            self._copy_robocode_files(source)
            return

        # Expected submission filename
        expected_name = Path(file_config["dest"]).name
        ext = file_config["ext"]

        # If source is a file, use it directly (single-file strategy)
        if source.is_file():
            src_file = source
            dest = file_config["dest"]
            parent_dir = str(Path(dest).parent)
            if parent_dir and parent_dir != "/workspace":
                self.environment.execute(f"mkdir -p {parent_dir}")
            code = src_file.read_text()
            self.environment.execute(f"cat > {dest} << 'STATICEOF'\n{code}\nSTATICEOF")
            self.logger.info(f"Copied {src_file.name} to container {dest}")
            return

        # Source is a directory
        src_file = source / expected_name
        if not src_file.exists():
            self.logger.error(f"Expected file {expected_name} not found in {source}")
            return

        dest_dir = str(Path(file_config["dest"]).parent)
        if not dest_dir or dest_dir == "/":
            dest_dir = "/workspace"

        # Ensure parent directory exists
        if dest_dir != "/workspace":
            self.environment.execute(f"mkdir -p {dest_dir}")

        # Copy the main submission file
        dest = file_config["dest"]
        code = src_file.read_text()
        self.environment.execute(f"cat > {dest} << 'STATICEOF'\n{code}\nSTATICEOF")
        self.logger.info(f"Copied {src_file.name} to container {dest}")

        # Copy auxiliary source files (same extension, skip test/debug scripts)
        skip_prefixes = ("test_", "test.", "analyze", "debug", "temp")
        for aux_file in sorted(source.glob(f"*{ext}")):
            if aux_file.name == expected_name:
                continue
            if aux_file.stem.lower().startswith(skip_prefixes):
                continue
            aux_dest = f"{dest_dir}/{aux_file.name}"
            aux_code = aux_file.read_text()
            self.environment.execute(f"cat > {aux_dest} << 'STATICEOF'\n{aux_code}\nSTATICEOF")
            self.logger.info(f"Copied aux {aux_file.name} to container {aux_dest}")

    def _copy_robocode_files(self, source: Path):
        """Copy all .java files for RoboCode."""
        self.environment.execute("mkdir -p /workspace/robots/custom")

        for java_file in source.glob("*.java"):
            code = java_file.read_text()
            dest = f"/workspace/robots/custom/{java_file.name}"
            self.environment.execute(f"cat > {dest} << 'STATICEOF'\n{code}\nSTATICEOF")
            self.logger.info(f"Copied {java_file.name} to container {dest}")

        self._copy_eval_main(source)

    def _copy_eval_main(self, source: Path):
        """Copy main.py to /workspace/main.py for offline evaluation if present.

        InverseStrategyTournament evaluates the learner offline by importing
        /workspace/main.py and calling its move() function.  This is separate
        from the in-game submission file (e.g. client/player.py for HuskyBench
        or robots/custom/*.java for RoboCode).
        """
        eval_main = source / "main.py"
        if eval_main.exists():
            create_file_in_container(
                self.environment,
                content=eval_main.read_text(),
                dest_path="/workspace/main.py",
            )
            self.logger.info("Copied main.py to /workspace/main.py for offline evaluation")

    def update_strategy(self, source_path: str | Path) -> None:
        """Re-copy strategy code from a new source path into the container."""
        self.config.setdefault("args", {})["source_path"] = str(source_path)
        self._copy_strategy_code()

    def run(self):
        """No-op since code was already copied during init."""
        pass
