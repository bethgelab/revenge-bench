from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from jinja2 import Template
from pydantic import BaseModel

load_dotenv()


class GameContext(BaseModel):
    """
    A class that gives agent access to a partial view of the game state.

    NOTE: Instead of passing `game` directly as a reference to the agent,
    we create this interface instead to make the communication of game state
    more explicit and controlled. We go with this loose coupling to avoid
    making the agent too dependent on the entire game object.
    """

    id: str
    log_env: Path
    log_local: Path
    name: str
    player_id: str
    prompts: dict
    round: int
    rounds: int
    working_dir: str
    distance_history: dict[int, float] = {}  # round -> mean action distance (lower is better)
    evaluation_errors: dict[int, str] = {}  # round -> error reason when evaluation failed
    context_mode: Literal["persistent", "reset"] = "persistent"

    def _render_prompt_templates(self) -> dict:
        context = self.model_dump()
        return {key: Template(template_str).render(**context) for key, template_str in self.prompts.items()}

    def _format_distance_progress(self) -> str:
        """Format distance history as a readable progress string with deltas."""
        if not self.distance_history:
            return "No distance data yet (this is round 0 or 1)."

        lines = []
        sorted_rounds = sorted(self.distance_history.keys())

        for i, r in enumerate(sorted_rounds):
            dist = self.distance_history[r]
            if dist is None:
                reason = self.evaluation_errors.get(r, "")
                if reason:
                    lines.append(f"Round {r}: evaluation failed — {reason}")
                else:
                    lines.append(f"Round {r}: evaluation failed")
                continue
            if i == 0:
                lines.append(f"Round {r}: {dist:.4f}")
            else:
                prev_r = sorted_rounds[i - 1]
                prev_dist = self.distance_history[prev_r]
                if prev_dist is None:
                    lines.append(f"Round {r}: {dist:.4f}")
                    continue
                delta = dist - prev_dist
                if delta < -0.01:
                    symbol = "IMPROVED (lower)"
                elif delta > 0.01:
                    symbol = "DEGRADED (higher)"
                else:
                    symbol = "unchanged"
                lines.append(f"Round {r}: {dist:.4f} ({delta:+.4f} from Round {prev_r}) {symbol}")

        return "\n".join(lines)

    def to_template_vars(self) -> dict[str, str]:
        """Convert the GameContext to a dictionary for rendering prompts in the agent"""
        out = self.model_dump() | self._render_prompt_templates()
        out.pop("prompts")
        out["distance_progress"] = self._format_distance_progress()
        return out
