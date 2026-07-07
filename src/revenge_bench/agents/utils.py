from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from jinja2 import StrictUndefined, Template
from pydantic import BaseModel

load_dotenv()


def render_prompt_sections(agent_cfg: dict, template_vars: dict) -> list[str]:
    """Render the ``system_template`` / ``instance_template`` prompt sections.

    Single source of truth for the round-prompt body shared by the native
    Codex learner (:meth:`CodexInverseStrategyAgent._render_round_prompt`) and
    the Harbor instruction generator (:mod:`revenge_bench.harbor.prompt`), so
    the two routes cannot drift.

    ``agent_cfg`` is the ``config.agent`` slot (holding the templates);
    ``template_vars`` are the GameContext-derived render variables. Both are
    merged into the Jinja render context so templates can reference either.
    Missing/empty templates are skipped; each rendered section is
    right-stripped. Rendering uses ``StrictUndefined`` so an unknown template
    variable raises instead of silently emitting an empty string.
    """
    ctx = {**agent_cfg, **template_vars}
    sections: list[str] = []
    for key in ("system_template", "instance_template"):
        raw = agent_cfg.get(key)
        if raw:
            rendered = Template(str(raw), undefined=StrictUndefined).render(**ctx)
            sections.append(rendered.rstrip())
    return sections


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
    # Solving route: the native multi-round Codex learner ("codex") vs the
    # single-session Harbor container ("harbor"). Prompt templates branch on this
    # so the shared problem/scorer core stays one source and only the
    # loop/tool/path sentences differ. Defaults to "codex" so the native path is
    # byte-for-byte unchanged.
    route: Literal["codex", "harbor"] = "codex"

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
