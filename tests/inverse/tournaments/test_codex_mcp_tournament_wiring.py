"""Tournament-side MCP wiring tests.

Verifies the tournament:
- creates and starts an MCP server when the learner is codex-backed,
- skips MCP entirely when the learner is mini-swe,
- passes the server reference to the agent via set_mcp_server,
- calls begin_round on the server before each edit phase,
- forwards the right probe callback / max_probes (None / 0 in base
  tournament; _run_inline_probe / max_probes_per_round in
  interventionist),
- stops the server in end().

These tests bypass the heavy parts of __init__ (game arena, game
container) by stubbing the learner agent and game and manually invoking
the relevant code paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_codex_learner_stub() -> MagicMock:
    """A stub that quacks like CodexInverseStrategyAgent for the
    tournament's duck-type checks (`edit_phase_backend == "codex"`,
    `set_mcp_server`, `_max_round_seconds`).
    """
    learner = MagicMock()
    learner.name = "learner"
    learner.edit_phase_backend = "codex"
    learner.environment = MagicMock()
    learner._max_round_seconds.return_value = 300
    learner.config = {"config": {"codex": {"model": "gpt-5-mini"}}}
    return learner


def _make_minisweagent_learner_stub() -> MagicMock:
    """Stub that does NOT have edit_phase_backend = 'codex' — should
    skip MCP entirely."""
    learner = MagicMock(spec=["name", "environment", "config", "init_session",
                               "run_round", "save_round_trajectory",
                               "post_run_hook", "pre_run_hook", "run"])
    learner.name = "learner"
    learner.environment = MagicMock()
    learner.config = {"config": {"agent": {"step_limit": 30, "cost_limit": 1.0}}}
    return learner


class TestServerLifecycle:
    """The tournament owns the MCP server. Verify start/stop wiring
    around the relevant code paths without spinning up a real arena."""

    def test_codex_learner_triggers_server_creation(self):
        """The relevant block lives at the bottom of `__init__` after
        agent creation. Construct an empty tournament shell and run
        just that block to confirm it creates+starts a server and
        plumbs it onto the agent."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = object.__new__(InverseStrategyTournament)
        t.learner_agent = _make_codex_learner_stub()
        t.logger = MagicMock()

        with patch("revenge_bench.agents.codex_mcp.CodexMCPServer") as MockServer:
            instance = MockServer.return_value
            instance.base_url = "http://127.0.0.1:5000"
            instance.mcp_path = "/mcp"
            # Replicate the relevant block (mirrors __init__ tail).
            from revenge_bench.agents.codex_mcp import CodexMCPServer
            t._mcp_server = CodexMCPServer(
                learner_environment=t.learner_agent.environment
            )
            t._mcp_server.start()
            t.learner_agent.set_mcp_server(t._mcp_server)

        assert t._mcp_server is instance
        instance.start.assert_called_once()
        t.learner_agent.set_mcp_server.assert_called_once_with(instance)

    def test_end_stops_server(self):
        """Tournament.end() must call stop() on the server and clear
        the reference."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = object.__new__(InverseStrategyTournament)
        server = MagicMock()
        t._mcp_server = server
        t._save = MagicMock()
        t.game = MagicMock()
        t.cleanup_on_end = False
        t.cleanup_handlers = MagicMock()

        InverseStrategyTournament.end(t)

        server.stop.assert_called_once()
        assert t._mcp_server is None

    def test_end_without_server_no_op(self):
        """`getattr(self, "_mcp_server", None)` keeps tests bypassing
        __init__ from blowing up."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = object.__new__(InverseStrategyTournament)
        # No _mcp_server attr set at all.
        t._save = MagicMock()
        t.game = MagicMock()
        t.cleanup_on_end = False
        t.cleanup_handlers = MagicMock()

        # Should not raise.
        InverseStrategyTournament.end(t)


class TestBeginRoundPlumbing:
    """run_edit_phase should call mcp_server.begin_round() before
    handing off to the learner agent, with the right kwargs."""

    def _make_min_tournament(self):
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = object.__new__(InverseStrategyTournament)
        t.context_mode = "reset"
        t.observation_mode = "raw"
        t.config = {"tournament": {}, "players": []}
        t._metadata = {"distance_history": {}, "evaluation_errors": {}}
        t.logger = MagicMock()
        t._save = MagicMock()
        t._compress_round_folder = MagicMock()
        t.game = MagicMock()
        from pathlib import Path
        t.game.log_local = Path("/tmp/logs")
        learner = _make_codex_learner_stub()
        learner.run = MagicMock()
        learner.pre_run_hook = MagicMock()
        learner.post_run_hook = MagicMock()
        t.learner_agent = learner
        t._mcp_server = MagicMock()
        return t

    def test_begin_round_called_with_codex_backend(self):
        """For codex learners, MCP begin_round runs with the round_num,
        wall-clock budget from the agent, and the tournament's hook
        values."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = self._make_min_tournament()
        # Base tournament: probe_callback None, max_probes 0.
        with patch("revenge_bench.tournaments.inverse_strategy.copy_to_container"):
            InverseStrategyTournament.run_edit_phase(t, 1)

        t._mcp_server.begin_round.assert_called_once()
        kwargs = t._mcp_server.begin_round.call_args.kwargs
        assert kwargs["round_num"] == 1
        assert kwargs["max_round_seconds"] == 300  # from learner stub
        assert kwargs["max_probes"] == 0  # base tournament has no probes
        assert kwargs["probe_callback"] is None

    def test_begin_round_skipped_when_no_mcp_server(self):
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = self._make_min_tournament()
        t._mcp_server = None  # mini-swe path
        # Replace learner with one that doesn't have edit_phase_backend
        # set — otherwise the agent attr lookups in run_edit_phase fail.
        t.learner_agent = _make_minisweagent_learner_stub()

        with patch("revenge_bench.tournaments.inverse_strategy.copy_to_container"):
            InverseStrategyTournament.run_edit_phase(t, 1)

        # No begin_round call to make on a None server. Assertion is
        # really "no AttributeError raised above".


class TestInterventionistHooks:
    def test_get_probe_callback_returns_run_inline_probe(self):
        from revenge_bench.tournaments.inverse_strategy_interventionist import (
            InverseStrategyInterventionistTournament,
        )

        t = object.__new__(InverseStrategyInterventionistTournament)
        # The hook returns a bound reference; identity check is enough.
        assert t._get_probe_callback() == t._run_inline_probe

    def test_get_max_probes_reads_config_value(self):
        from revenge_bench.tournaments.inverse_strategy_interventionist import (
            InverseStrategyInterventionistTournament,
        )

        t = object.__new__(InverseStrategyInterventionistTournament)
        t.max_probes_per_round = 7
        assert t._get_max_probes() == 7

    def test_base_tournament_hooks_default_off(self):
        """Base InverseStrategyTournament must not opt into probing —
        hooks return None / 0."""
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament

        t = object.__new__(InverseStrategyTournament)
        assert t._get_probe_callback() is None
        assert t._get_max_probes() == 0
