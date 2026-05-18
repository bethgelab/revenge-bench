"""Game context and player interfaces."""
from pathlib import Path
from typing import Any

from jinja2 import Template
from pydantic import BaseModel


class GameContext(BaseModel):
    """A class that gives agent access to a partial view of the game state."""

    id: str
    log_env: Path
    log_local: Path
    name: str
    player_id: str
    prompts: dict
    round: int
    rounds: int
    working_dir: str

    def _render_prompt_templates(self) -> dict:
        context = self.model_dump()
        return {
            key: Template(template_str).render(**context)
            for key, template_str in self.prompts.items()
        }

    def to_template_vars(self) -> dict[str, str]:
        """Convert the GameContext to a dictionary for rendering prompts."""
        out = self.model_dump() | self._render_prompt_templates()
        out.pop("prompts")
        return out


class PlayerStats:
    """Statistics for a single player in a round."""

    def __init__(self, name: str):
        self.name = name
        self.invalid_reason: str = ""
        self.score: float = 0.0
        self.valid_submit = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "invalid_reason": self.invalid_reason,
            "score": self.score,
            "valid_submit": self.valid_submit,
        }


class RoundStats:
    """Statistics for a single round of a game."""

    def __init__(self, round_num: int, player_names: list[str]):
        self.winner = None
        self.round_num = round_num
        self.scores: dict[str, float] = {name: 0.0 for name in player_names}
        self.player_stats: dict[str, PlayerStats] = {
            name: PlayerStats(name=name) for name in player_names
        }
        self.details: list[str] = []

    def __str__(self) -> str:
        rv = [
            f"In round {self.round_num}, the winner is {self.winner}.",
            "\nSummary of player performance:",
        ]
        for player, stats in self.player_stats.items():
            if stats.valid_submit:
                rv.append(
                    f"- {player}: submission compiled successfully, score={stats.score}"
                )
            else:
                rv.append(
                    f"- {player}: submission failed with error: {stats.invalid_reason}"
                )
        if self.details:
            rv.extend(["Details:"] + [f"- {line}" for line in self.details])
        return "\n".join(rv)

    def to_dict(self) -> dict[str, Any]:
        player_names = set(self.player_stats.keys()) | set(self.scores.keys())
        return {
            "round_num": self.round_num,
            "winner": self.winner,
            "details": self.details,
            "scores": {name: self.scores.get(name, 0.0) for name in player_names},
            "player_stats": {
                name: stats.to_dict() for name, stats in self.player_stats.items()
            },
        }
