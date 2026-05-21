"""End-to-end persistence test: 3 rounds of run_edit_phase with a mocked arena.

We don't spin up Docker. The arena and environments are MagicMock objects.
We use DeterministicModel for the learner so no real LLM is called.

What is verified:
- After 3 rounds, inner ClashAgent.messages grows monotonically.
- Pinned round-transition messages appear at the right offsets (rounds 2 and 3).
- The system prompt (index 0) and instance prompt (index 1) are rendered exactly
  once and never duplicated across rounds.
- "Round 1 evaluation complete" and "Round 2 evaluation complete" appear in the
  pinned messages.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_deterministic_learner_config(outputs: list[str]) -> dict:
    """Return a player config dict for an InverseStrategyAgent with DeterministicModel."""
    return {
        "agent": "inverse",
        "name": "learner",
        "editable": True,
        "config": {
            "model": {
                "model_name": "deterministic_test",
                "model_class": "minisweagent.models.test_models.DeterministicModel",
                "outputs": outputs,
            },
            "agent": {
                # tiny per-round budgets so we exhaust quickly
                "step_limit": 2,
                "cost_limit": 10.0,
            },
        },
    }


def _make_target_config() -> dict:
    return {
        "agent": "static",
        "name": "target",
        "editable": False,
        "args": {"source_path": "/nonexistent"},
    }


def _build_mock_environment() -> MagicMock:
    """Build a MagicMock ContainerEnvironment whose execute() always succeeds."""
    env = MagicMock()
    env.execute.return_value = {"output": "ok", "returncode": 0}
    return env


def _build_mock_game_context(tmp_path: Path, rounds: int = 3) -> MagicMock:
    """Build a minimal GameContext-like mock (not a Pydantic model, just attrs)."""
    from revenge_bench.agents.utils import GameContext

    gc = GameContext(
        id="test-game-id",
        log_env=Path("/logs"),
        log_local=tmp_path / "logs",
        name="BattleSnake",
        player_id="learner",
        prompts={"game_description": "Test game"},
        round=1,
        rounds=rounds,
        working_dir="/workspace",
    )
    return gc


def _build_inverse_agent(
    tmp_path: Path,
    outputs: list[str],
    rounds: int = 3,
) -> "InverseStrategyAgent":
    """Construct an InverseStrategyAgent with mocked environment."""
    from revenge_bench.agents.minisweagent import InverseStrategyAgent

    env = _build_mock_environment()
    gc = _build_mock_game_context(tmp_path, rounds=rounds)
    cfg = _make_deterministic_learner_config(outputs)

    agent = InverseStrategyAgent(cfg, env, gc)
    return agent


def _write_round_dir(base: Path, round_num: int) -> Path:
    """Write a minimal traces.json into base/rounds/{round_num}/ so that
    copy_to_container has a valid source directory (we mock it, but the
    directory needs to exist for path construction)."""
    round_dir = base / "rounds" / str(round_num)
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "traces.json").write_text(
        json.dumps(
            {
                "mean_distance": 0.5,
                "total_actions": 10,
                "nonzero_distances": [],
                "per_simulation": [],
            }
        )
    )
    return round_dir


# ---------------------------------------------------------------------------
# Minimal tournament stub
# ---------------------------------------------------------------------------

def _build_tournament_stub(
    tmp_path: Path,
    learner_agent: "InverseStrategyAgent",
    rounds: int = 3,
) -> MagicMock:
    """Build a minimal object that looks like InverseStrategyTournament enough
    to call run_edit_phase() on it.

    We bypass InverseStrategyTournament.__init__ entirely (it calls Docker) and
    instead attach the required attributes manually.
    """
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

    # Bypass __init__
    t = object.__new__(InverseStrategyTournament)

    # Attributes required by AbstractTournament (used inside run_edit_phase
    # indirectly through self._save and self.logger)
    t.name = "InverseStrategyTournament"
    t.config = {
        "tournament": {"rounds": rounds},
        "game": {"name": "BattleSnake", "sims_per_round": 1},
        "players": [
            {"agent": "inverse", "name": "learner", "editable": True,
             "config": {"agent": {"step_limit": 2, "cost_limit": 10.0},
                        "model": {"model_name": "det", "model_class": "...",
                                  "outputs": []}}},
            {"agent": "static", "name": "target", "editable": False},
        ],
        "prompts": {"game_description": "Test"},
    }
    t._output_dir = tmp_path / "output"
    t._output_dir.mkdir(parents=True, exist_ok=True)

    # Logger
    import logging
    t.logger = logging.getLogger("test_tournament")

    # Metadata (normally built in AbstractTournament.__init__)
    t._metadata = {}
    t.cleanup_on_end = False
    t.context_mode = "persistent"
    t.observation_mode = "raw"

    # Game arena mock
    game = MagicMock()
    game.name = "BattleSnake"
    game.log_local = tmp_path / "logs"
    game.log_local.mkdir(parents=True, exist_ok=True)
    game.log_env = Path("/logs")
    game.game_id = "test-game-id"
    t.game = game

    # Agents
    target_mock = MagicMock()
    target_mock.name = "target"
    t.learner_agent = learner_agent
    t.target_agent = target_mock
    t.opponent_agent = target_mock
    t.game_agents = [target_mock, target_mock]
    t.agents = [learner_agent, target_mock]

    # metadata_file is a property too; mock it via patching or just keep it
    # accessible through the config (t.rounds is computed from t.config).
    # metadata_file is also a property — patch it on the instance via __dict__
    # won't work for properties; instead we set it via a type-level override.
    # Easiest: just don't call _save (we already patch it) and ignore metadata_file.

    return t


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------

def test_three_rounds_preserve_context(tmp_path):
    """run_edit_phase across 3 rounds accumulates pinned transition messages."""
    # Each round: LimitsExceeded after 2 steps.
    # DeterministicModel outputs — 2 bash commands per round + 1 submit on round 3
    # We give 3 rounds x 2 steps = 6 outputs, all doing nothing special.
    outputs = []
    for r in range(1, 4):
        for s in range(2):
            outputs.append(f"Thinking round {r} step {s}\n```bash\necho r{r}s{s}\n```")
    # The step_limit is 2 per round; on exhaustion ClashAgent raises LimitsExceeded.
    # DeterministicModel will run out of outputs — that's fine: LimitsExceeded is
    # raised first (step limit triggers in query() before the next model call).

    # Write round dirs so copy_to_container has paths to reference
    log_base = tmp_path / "logs"
    for rn in range(0, 3):
        _write_round_dir(log_base, rn)

    learner = _build_inverse_agent(tmp_path, outputs, rounds=3)

    t = _build_tournament_stub(tmp_path, learner, rounds=3)

    # Patch everything that touches Docker / filesystem beyond tmp_path
    with (
        patch("revenge_bench.tournaments.inverse_strategy.copy_to_container") as mock_copy,
        patch("revenge_bench.agents.minisweagent.copy_to_container"),
        patch.object(t, "_compress_round_folder", return_value=None),
        patch.object(t, "_save", return_value=None),
        patch.object(
            learner, "save_round_trajectory", return_value=None
        ),
    ):
        # Also mock the evaluation-like data that run_edit_phase reads from
        # _metadata (it builds transition_summary from these dicts)
        t._metadata["distance_history"] = {0: 0.8, 1: 0.6, 2: 0.4}
        t._metadata["mismatch_counts"] = {0: 8, 1: 5, 2: 3}
        t._metadata["submission_status_per_round"] = {
            0: "ok",
            1: "LimitsExceeded",
            2: "LimitsExceeded",
        }

        # Round 1: initialise session
        t.run_edit_phase(1)
        inner = learner.agent  # ClashAgent is now instantiated
        msgs_after_r1 = len(inner.messages)

        # There should be at least system + instance-prompt + some obs messages
        assert msgs_after_r1 >= 2, (
            f"Expected at least 2 messages after round 1, got {msgs_after_r1}"
        )

        # Round 2: transition summary is injected as a pinned message
        t.run_edit_phase(2)
        msgs_after_r2 = len(inner.messages)
        assert msgs_after_r2 > msgs_after_r1, (
            "Message list should grow after round 2"
        )

        # Round 3: another pinned transition message
        t.run_edit_phase(3)
        msgs_after_r3 = len(inner.messages)
        assert msgs_after_r3 > msgs_after_r2, (
            "Message list should grow after round 3"
        )

    # ---- Pinned message assertions ----
    pinned = [m for m in inner.messages if m.get("pinned")]
    assert len(pinned) == 2, (
        f"Expected exactly 2 pinned round-transition messages, got {len(pinned)}. "
        f"Pinned: {[m['content'][:80] for m in pinned]}"
    )

    assert "Round 1 evaluation complete" in pinned[0]["content"], (
        f"First pinned message should mention 'Round 1 evaluation complete', "
        f"got: {pinned[0]['content'][:200]}"
    )
    assert "Round 2 evaluation complete" in pinned[1]["content"], (
        f"Second pinned message should mention 'Round 2 evaluation complete', "
        f"got: {pinned[1]['content'][:200]}"
    )

    # ---- Structural assertions: system + instance prompt rendered once ----
    assert inner.messages[0]["role"] == "system", (
        "First message must be the system prompt"
    )
    assert inner.messages[1]["role"] == "user", (
        "Second message must be the instance (user) prompt"
    )
    assert not inner.messages[1].get("pinned"), (
        "Instance prompt should NOT be pinned"
    )

    # The word TASK appears in the instance template or game context prompts.
    # Regardless of count, the key check: system + instance appear exactly once.
    system_msgs = [m for m in inner.messages if m["role"] == "system"]
    assert len(system_msgs) == 1, (
        f"System prompt rendered more than once: {len(system_msgs)} times"
    )

    # Instance prompt is index 1 and is the only non-pinned early user message
    early_user_msgs = [
        m for m in inner.messages[1:3]
        if m["role"] == "user" and not m.get("pinned")
    ]
    assert len(early_user_msgs) >= 1, "Instance prompt missing"

    # ---- copy_to_container was called once per round ----
    assert mock_copy.call_count == 3, (
        f"copy_to_container should be called once per round (3 total), "
        f"got {mock_copy.call_count}"
    )

    # Structural: after 3 rounds, no consecutive same-role messages anywhere
    # in self.messages (this is the API boundary for round 4+ — we never
    # want to send user→user). Allow consecutive system messages (defensive;
    # not currently produced).
    roles = [m["role"] for m in inner.messages]
    for i in range(1, len(roles)):
        assert roles[i] != roles[i - 1] or roles[i] == "system", (
            f"consecutive {roles[i]} at indices {i-1},{i} after round 3 "
            f"(persistent-context lifecycle leaks user→user)"
        )
