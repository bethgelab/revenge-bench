from revenge_bench.agents.minisweagent import MiniSWEAgent, InverseStrategyAgent
from revenge_bench.agents.player import Player
from revenge_bench.agents.static_agent import Static
from revenge_bench.agents.utils import GameContext
from revenge_bench.utils.environment import ContainerEnvironment


def get_agent(config: dict, game_context: GameContext, environment: ContainerEnvironment) -> Player:
    agent_type = config["agent"]
    # Lazy-import the Codex backend so installs without the Codex CLI / MCP
    # extras still load the other agents.
    if agent_type == "inverse_codex":
        from revenge_bench.agents.codex_agent import CodexInverseStrategyAgent

        return CodexInverseStrategyAgent(config, environment, game_context)
    agents = {
        "mini": MiniSWEAgent,
        "static": Static,
        "inverse": InverseStrategyAgent,
    }.get(agent_type)
    if agents is None:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return agents(config, environment, game_context)

