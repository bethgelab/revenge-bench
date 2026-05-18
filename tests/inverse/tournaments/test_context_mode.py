"""Tests for context_mode flag wiring through the tournament."""

from unittest.mock import MagicMock, patch

import pytest


def _make_tournament(context_mode=None, tmp_path=None):
    """Construct an InverseStrategyTournament stub bypassing __init__'s heavy parts.

    We exercise the part of __init__ that reads tournament.context_mode.
    """
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

    tournament_cfg = {"rounds": 3}
    if context_mode is not None:
        tournament_cfg["context_mode"] = context_mode

    config = {
        "tournament": tournament_cfg,
        "game": {"name": "BattleSnake", "sims_per_round": 1},
        "players": [
            {"agent": "static", "name": "learner", "editable": True},
            {"agent": "static", "name": "target"},
        ],
        "prompts": {},
    }
    # Patch the heavy bits and exercise just the config-reading path.
    with patch("revenge_bench.tournaments.inverse_strategy.get_arena") as mock_arena, \
         patch("revenge_bench.tournaments.inverse_strategy.get_agent") as mock_agent:
        arena = MagicMock()
        arena.game_id = "g"
        arena.log_local = tmp_path or "/tmp"
        arena.log_env = "/logs"
        arena.name = "BattleSnake"
        arena.get_environment.return_value = MagicMock()
        mock_arena.return_value = arena
        mock_agent.return_value = MagicMock(
            name="player", game_context=MagicMock(),
        )
        t = InverseStrategyTournament(config, output_dir=tmp_path or "/tmp")
        return t


class TestContextModeReadFromConfig:
    def test_default_is_persistent(self, tmp_path):
        t = _make_tournament(tmp_path=tmp_path)
        assert t.context_mode == "persistent"

    def test_explicit_reset(self, tmp_path):
        t = _make_tournament(context_mode="reset", tmp_path=tmp_path)
        assert t.context_mode == "reset"

    def test_propagates_to_player_game_context(self, tmp_path):
        # When the tournament constructs each player, it passes a GameContext
        # whose context_mode matches the tournament config.
        from revenge_bench.agents.utils import GameContext

        # Capture the GameContext created during get_agent calls.
        captured = []
        original_get_agent = None

        with patch("revenge_bench.tournaments.inverse_strategy.get_arena") as mock_arena, \
             patch("revenge_bench.tournaments.inverse_strategy.get_agent") as mock_agent:
            arena = MagicMock()
            arena.game_id = "g"; arena.log_local = tmp_path; arena.log_env = "/logs"
            arena.name = "BattleSnake"; arena.get_environment.return_value = MagicMock()
            mock_arena.return_value = arena

            def capture_agent(agent_cfg, game_context, env):
                captured.append(game_context)
                return MagicMock(name=agent_cfg["name"], game_context=game_context)
            mock_agent.side_effect = capture_agent

            from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
            config = {
                "tournament": {"rounds": 3, "context_mode": "reset"},
                "game": {"name": "BattleSnake", "sims_per_round": 1},
                "players": [
                    {"agent": "static", "name": "learner", "editable": True},
                    {"agent": "static", "name": "target"},
                ],
                "prompts": {},
            }
            InverseStrategyTournament(config, output_dir=tmp_path)

        # Each captured GameContext should have context_mode = "reset"
        assert len(captured) >= 2
        for ctx in captured:
            assert isinstance(ctx, GameContext)
            assert ctx.context_mode == "reset"


# ---------------------------------------------------------------------------
# Helpers shared by TestRunEditPhaseDispatch
# ---------------------------------------------------------------------------

def _build_dispatch_stub(tmp_path, learner_agent, rounds=3):
    """Build the minimal InverseStrategyTournament stub needed for dispatch tests.

    Bypasses __init__ entirely (which calls Docker) and attaches the attributes
    that run_edit_phase() reads.
    """
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
    import logging

    t = object.__new__(InverseStrategyTournament)

    t.name = "InverseStrategyTournament"
    t.config = {
        "tournament": {"rounds": rounds},
        "game": {"name": "BattleSnake", "sims_per_round": 1},
        "players": [
            {
                "agent": "inverse",
                "name": "learner",
                "editable": True,
                "config": {
                    "agent": {"step_limit": 2, "cost_limit": 10.0},
                    "model": {"model_name": "det", "model_class": "...", "outputs": []},
                },
            },
            {"agent": "static", "name": "target", "editable": False},
        ],
        "prompts": {"game_description": "Test"},
    }
    t._output_dir = tmp_path / "output"
    t._output_dir.mkdir(parents=True, exist_ok=True)

    t.logger = logging.getLogger("test_dispatch")
    t._metadata = {}
    t.cleanup_on_end = False
    t.observation_mode = "raw"

    game = MagicMock()
    game.name = "BattleSnake"
    game.log_local = tmp_path / "logs"
    game.log_local.mkdir(parents=True, exist_ok=True)
    game.log_env = "/logs"
    game.game_id = "test-game-id"
    t.game = game

    target_mock = MagicMock()
    target_mock.name = "target"
    t.learner_agent = learner_agent
    t.target_agent = target_mock
    t.opponent_agent = target_mock
    t.game_agents = [target_mock, target_mock]
    t.agents = [learner_agent, target_mock]

    return t


def _make_mock_learner():
    """Return a MagicMock that looks like an InverseStrategyAgent for dispatch tests."""
    learner = MagicMock()
    learner.name = "learner"
    learner.environment = MagicMock()
    learner.config = {
        "config": {
            "agent": {"step_limit": 2, "cost_limit": 10.0},
        }
    }
    return learner


class TestRunEditPhaseDispatch:
    """Verify run_edit_phase calls the right path based on context_mode.

    We check via spy: persistent mode calls init_session+run_round; reset
    mode calls the one-shot agent.run().
    """

    def test_persistent_mode_calls_lifecycle_methods(self, tmp_path):
        """Round 1: init_session called; round 2+: run_round called. run() never called."""
        learner = _make_mock_learner()
        # run_round returns a string exit status (the persistent path captures it)
        learner.run_round.return_value = "limits_exceeded"

        t = _build_dispatch_stub(tmp_path, learner, rounds=3)
        t.context_mode = "persistent"

        with (
            patch("revenge_bench.tournaments.inverse_strategy.copy_to_container"),
            patch.object(t, "_compress_round_folder", return_value=None),
            patch.object(t, "_save", return_value=None),
        ):
            # Round 1: init_session should be called (not run)
            t.run_edit_phase(1)
            assert learner.init_session.call_count == 1, (
                f"init_session should be called once after round 1, "
                f"got {learner.init_session.call_count}"
            )
            assert learner.run_round.call_count == 1, (
                f"run_round should be called once after round 1, "
                f"got {learner.run_round.call_count}"
            )
            assert learner.run.call_count == 0, (
                f"run() must NOT be called in persistent mode, "
                f"got {learner.run.call_count}"
            )

            # Round 2: run_round called again, init_session not called again
            t.run_edit_phase(2)
            assert learner.init_session.call_count == 1, (
                f"init_session should still be 1 after round 2, "
                f"got {learner.init_session.call_count}"
            )
            assert learner.run_round.call_count == 2, (
                f"run_round should be called twice after round 2, "
                f"got {learner.run_round.call_count}"
            )
            assert learner.run.call_count == 0, (
                f"run() must NOT be called in persistent mode, "
                f"got {learner.run.call_count}"
            )

    def test_reset_mode_calls_one_shot_run(self, tmp_path):
        """Each round: agent.run() is called; init_session/run_round are NOT."""
        learner = _make_mock_learner()

        t = _build_dispatch_stub(tmp_path, learner, rounds=3)
        t.context_mode = "reset"

        with (
            patch("revenge_bench.tournaments.inverse_strategy.copy_to_container"),
            patch.object(t, "_compress_round_folder", return_value=None),
            patch.object(t, "_save", return_value=None),
        ):
            # Round 1
            t.run_edit_phase(1)
            assert learner.run.call_count == 1, (
                f"run() should be called once after round 1, "
                f"got {learner.run.call_count}"
            )
            assert learner.init_session.call_count == 0, (
                f"init_session must NOT be called in reset mode, "
                f"got {learner.init_session.call_count}"
            )
            assert learner.run_round.call_count == 0, (
                f"run_round must NOT be called in reset mode, "
                f"got {learner.run_round.call_count}"
            )

            # Round 2: run() called again
            t.run_edit_phase(2)
            assert learner.run.call_count == 2, (
                f"run() should be called twice after round 2, "
                f"got {learner.run.call_count}"
            )
            assert learner.init_session.call_count == 0, (
                f"init_session must NOT be called in reset mode, "
                f"got {learner.init_session.call_count}"
            )
            assert learner.run_round.call_count == 0, (
                f"run_round must NOT be called in reset mode, "
                f"got {learner.run_round.call_count}"
            )


# ---------------------------------------------------------------------------
# Helpers shared by TestResetModeIntegration
# (mirrors the helpers in test_persistent_context_integration.py, but we
#  duplicate them here to keep the two test modules fully independent)
# ---------------------------------------------------------------------------

def _make_reset_learner_config(outputs: list[str]) -> dict:
    """Player config for InverseStrategyAgent with a custom instance_template
    that includes {{ distance_progress }} so we can assert its rendered content."""
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
                "step_limit": 2,
                "cost_limit": 10.0,
                # Custom templates that exercise distance_progress rendering.
                "system_template": "You are a test learner. context_mode={{ context_mode }}",
                "instance_template": "## Distance Progress\n{{ distance_progress }}",
            },
        },
    }


def _build_reset_mock_environment() -> "MagicMock":
    env = MagicMock()
    env.execute.return_value = {"output": "ok", "returncode": 0}
    return env


def _build_reset_game_context(tmp_path, rounds: int = 3):
    from revenge_bench.agents.utils import GameContext
    from pathlib import Path

    return GameContext(
        id="test-reset-id",
        log_env=Path("/logs"),
        log_local=tmp_path / "logs",
        name="BattleSnake",
        player_id="learner",
        prompts={"game_description": "Test game"},
        round=1,
        rounds=rounds,
        working_dir="/workspace",
        context_mode="reset",
    )


def _build_reset_inverse_agent(tmp_path, outputs: list[str], rounds: int = 3):
    from revenge_bench.agents.minisweagent import InverseStrategyAgent

    env = _build_reset_mock_environment()
    gc = _build_reset_game_context(tmp_path, rounds=rounds)
    cfg = _make_reset_learner_config(outputs)
    return InverseStrategyAgent(cfg, env, gc)


def _write_reset_round_dir(base, round_num: int):
    import json as _json

    round_dir = base / "rounds" / str(round_num)
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "traces.json").write_text(
        _json.dumps(
            {
                "mean_distance": 0.5,
                "total_actions": 10,
                "nonzero_distances": [],
                "per_simulation": [],
            }
        )
    )
    return round_dir


def _build_reset_tournament_stub(tmp_path, learner_agent, rounds: int = 3):
    from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
    import logging

    t = object.__new__(InverseStrategyTournament)

    t.name = "InverseStrategyTournament"
    t.config = {
        "tournament": {"rounds": rounds, "context_mode": "reset"},
        "game": {"name": "BattleSnake", "sims_per_round": 1},
        "players": [
            {
                "agent": "inverse",
                "name": "learner",
                "editable": True,
                "config": {
                    "agent": {"step_limit": 2, "cost_limit": 10.0},
                    "model": {"model_name": "det", "model_class": "...", "outputs": []},
                },
            },
            {"agent": "static", "name": "target", "editable": False},
        ],
        "prompts": {"game_description": "Test"},
    }
    t._output_dir = tmp_path / "output"
    t._output_dir.mkdir(parents=True, exist_ok=True)

    t.logger = logging.getLogger("test_reset_tournament")
    t._metadata = {}
    t.cleanup_on_end = False
    t.context_mode = "reset"
    t.observation_mode = "raw"

    game = MagicMock()
    game.name = "BattleSnake"
    game.log_local = tmp_path / "logs"
    game.log_local.mkdir(parents=True, exist_ok=True)
    game.log_env = "/logs"
    game.game_id = "test-reset-game-id"
    t.game = game

    target_mock = MagicMock()
    target_mock.name = "target"
    t.learner_agent = learner_agent
    t.target_agent = target_mock
    t.opponent_agent = target_mock
    t.game_agents = [target_mock, target_mock]
    t.agents = [learner_agent, target_mock]

    return t


# ---------------------------------------------------------------------------
# Integration test: 3 rounds in reset mode
# ---------------------------------------------------------------------------

class TestResetModeIntegration:
    def test_three_rounds_each_resets_messages(self, tmp_path):
        """Reset mode: a fresh ClashAgent is built per round, so the learner's
        inner agent.messages is wiped between rounds.

        Asserts:
          - The learner's inner agent at end of round 3 has only the messages
            from round 3 (not the cumulative trajectory).
          - No pinned round-transition messages exist (those only appear under
            persistent mode).
          - Round 3's instance prompt contains the distance_history from prior
            rounds (proving distance_progress is rendered fresh per round in
            reset mode).
        """
        # 6 outputs total: 2 steps per round × 3 rounds.
        # Each round's DeterministicModel is freshly constructed from the same
        # list, consumes the first 2, then LimitsExceeded triggers.
        outputs = [
            f"step {s} round {r}\n```bash\necho r{r}s{s}\n```"
            for r in (1, 2, 3)
            for s in (1, 2)
        ]

        # Write round dirs so copy_to_container has valid source paths
        log_base = tmp_path / "logs"
        for rn in range(0, 3):
            _write_reset_round_dir(log_base, rn)

        learner = _build_reset_inverse_agent(tmp_path, outputs, rounds=3)
        t = _build_reset_tournament_stub(tmp_path, learner, rounds=3)

        with (
            patch("revenge_bench.tournaments.inverse_strategy.copy_to_container"),
            patch("revenge_bench.agents.minisweagent.copy_to_container"),
            patch("revenge_bench.agents.minisweagent.save_traj"),
            patch.object(t, "_compress_round_folder", return_value=None),
            patch.object(t, "_save", return_value=None),
        ):
            # Seed distance_history before round 1 (round 0 baseline already in)
            t._metadata["distance_history"] = {0: 0.8}

            # --- Round 1 ---
            t.run_edit_phase(1)
            # Simulate evaluation after round 1
            t._metadata["distance_history"][1] = 0.6

            # --- Round 2 ---
            t.run_edit_phase(2)
            # Simulate evaluation after round 2
            t._metadata["distance_history"][2] = 0.4

            # --- Round 3 ---
            t.run_edit_phase(3)

        # The most recent ClashAgent (round 3's fresh instance)
        inner = learner.agent

        # ---- No pinned round-transition messages (reset mode never injects them) ----
        pinned = [m for m in inner.messages if m.get("pinned")]
        assert len(pinned) == 0, (
            f"Reset mode must not create any pinned messages, "
            f"got {len(pinned)}: {[m['content'][:80] for m in pinned]}"
        )

        # ---- Structural: system + instance prompt from round 3 only ----
        assert inner.messages[0]["role"] == "system", (
            "First message must be the system prompt"
        )
        assert inner.messages[1]["role"] == "user", (
            "Second message must be the instance (user) prompt"
        )

        # Only one system message — proves the agent is fresh (not cumulative)
        system_msgs = [m for m in inner.messages if m["role"] == "system"]
        assert len(system_msgs) == 1, (
            f"Reset mode should have exactly 1 system message (fresh agent per round), "
            f"got {len(system_msgs)}"
        )

        # ---- distance_progress is rendered fresh: round 3 instance contains ----
        # ---- the full history from rounds 0, 1, 2 (i.e. "Round 1:", "Round 2:") ----
        instance_msg = inner.messages[1]
        assert "Round 1:" in instance_msg["content"], (
            f"Instance prompt should contain 'Round 1:' in distance history; "
            f"got: {instance_msg['content'][:300]}"
        )
        assert "Round 2:" in instance_msg["content"], (
            f"Instance prompt should mention 'Round 2:' in the distance history; "
            f"got: {instance_msg['content'][:300]}"
        )
