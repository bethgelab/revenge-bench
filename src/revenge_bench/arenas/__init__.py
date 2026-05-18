from revenge_bench.arenas.arena import CodeArena
from revenge_bench.arenas.battlesnake.battlesnake import BattleSnakeArena
from revenge_bench.arenas.halite.halite import HaliteArena
from revenge_bench.arenas.huskybench.huskybench import HuskyBenchArena
from revenge_bench.arenas.robocode.robocode import RoboCodeArena
from revenge_bench.arenas.robotrumble.robotrumble import RobotRumbleArena

ARENAS = [
    BattleSnakeArena,
    HaliteArena,
    HuskyBenchArena,
    RoboCodeArena,
    RobotRumbleArena,
]


# might consider postponing imports to avoid loading things we don't need
def get_arena(config: dict, **kwargs) -> CodeArena:
    game = {x.name: x for x in ARENAS}.get(config["game"]["name"])
    if game is None:
        raise ValueError(f"Unknown game: {config['game']['name']}")
    return game(config, **kwargs)
