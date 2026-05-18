"""MCP wiring tests for CodexInverseStrategyAgent.

Covers the agent side of the MCP integration (the server itself has its
own end-to-end tests in test_codex_mcp_server.py):
- ``set_mcp_server`` stash + propagation,
- ``$CODEX_HOME/config.toml`` write with bearer token,
- helper-script invocation when MCP is configured (vs direct codex
  fallback when it isn't),
- container-side ``/healthz`` health check (success + failure modes),
- INVERSE_CODEX_* env vars exported on the codex command line.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revenge_bench.agents.codex_agent import (
    CODEX_HOME_PATH,
    HELPER_SCRIPT_PATH,
    SUBMIT_MARKER_PATH,
    CodexInverseStrategyAgent,
)
from revenge_bench.agents.utils import GameContext


def _make_agent(tmp_path: Path) -> CodexInverseStrategyAgent:
    env = MagicMock()
    env.execute.return_value = {"output": "deadbeef\n", "returncode": 0}
    log_local = tmp_path / "logs"
    log_local.mkdir()
    config = {
        "name": "learner",
        "agent": "inverse_codex",
        "config": {
            "codex": {
                "command": "codex",
                "model": "gpt-5-mini",
                "auth_file": None,
                "max_round_seconds": 240,
            },
            "agent": {
                "system_template": "SYS",
                "instance_template": "INST",
            },
        },
    }
    gc = GameContext(
        id="g",
        log_env=Path("/logs"),
        log_local=log_local,
        name="Test",
        player_id="learner",
        prompts={},
        round=1,
        rounds=2,
        working_dir="/workspace",
        context_mode="reset",
    )
    return CodexInverseStrategyAgent(config, environment=env, game_context=gc)


def _fake_server(*, host_url="http://127.0.0.1:5555", container_url="http://host.docker.internal:5555",
                 mcp_path="/mcp", token="test-token-XYZ"):
    s = MagicMock()
    s.base_url = host_url
    s.container_base_url = container_url
    s.mcp_path = mcp_path
    s.token = token
    return s


def _executions(env: MagicMock) -> list[str]:
    return [c.args[0] for c in env.execute.call_args_list if c.args]


class TestSetMcpServer:
    def test_set_mcp_server_stashes_reference(self, tmp_path):
        agent = _make_agent(tmp_path)
        assert agent._mcp_server is None
        server = _fake_server()
        agent.set_mcp_server(server)
        assert agent._mcp_server is server


class TestConfigTomlWrite:
    def test_prepare_session_writes_config_toml_when_mcp_set(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.set_mcp_server(_fake_server(token="my-secret-token"))
        # Pretend the in-container health check passes.
        agent.environment.execute.return_value = {"output": "OK", "returncode": 0}

        with patch("revenge_bench.agents.codex_agent.create_file_in_container") as mock_create:
            agent._prepare_session()

        # find the create_file_in_container call for config.toml
        toml_calls = [
            c for c in mock_create.call_args_list
            if c.kwargs.get("dest_path") == f"{CODEX_HOME_PATH}/config.toml"
        ]
        assert len(toml_calls) == 1
        body = toml_calls[0].kwargs["content"]
        assert "[mcp_servers.inverse-codex]" in body
        assert 'url = "http://host.docker.internal:5555/mcp"' in body
        # Codex 0.128.0 reads the bearer token from an env var, not
        # from the TOML file — the actual secret never lands on disk.
        assert 'bearer_token_env_var = "INVERSE_CODEX_MCP_TOKEN"' in body
        assert "my-secret-token" not in body

    def test_prepare_session_no_config_toml_without_mcp(self, tmp_path):
        agent = _make_agent(tmp_path)
        # No set_mcp_server call — _mcp_server stays None.
        with patch("revenge_bench.agents.codex_agent.create_file_in_container") as mock_create:
            agent._prepare_session()

        toml_calls = [
            c for c in mock_create.call_args_list
            if c.kwargs.get("dest_path", "").endswith("config.toml")
        ]
        assert len(toml_calls) == 0


class TestHealthCheck:
    def test_health_check_runs_when_mcp_set(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.set_mcp_server(_fake_server(container_url="http://host.docker.internal:9000"))
        agent.environment.execute.return_value = {"output": "OK", "returncode": 0}

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"):
            agent._prepare_session()

        # The health check shell contains the container URL + /healthz.
        health_calls = [
            c for c in _executions(agent.environment)
            if "/healthz" in c
        ]
        assert len(health_calls) == 1
        assert "http://host.docker.internal:9000/healthz" in health_calls[0]

    def test_health_check_failure_raises(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.set_mcp_server(_fake_server())

        def execute_router(cmd, *args, **kwargs):
            if "/healthz" in cmd:
                return {"output": "curl: (7) Failed to connect", "returncode": 7}
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"):
            with pytest.raises(RuntimeError, match="MCP health check failed"):
                agent._prepare_session()

    def test_no_health_check_without_mcp(self, tmp_path):
        agent = _make_agent(tmp_path)
        with patch("revenge_bench.agents.codex_agent.create_file_in_container"):
            agent._prepare_session()
        health_calls = [c for c in _executions(agent.environment) if "/healthz" in c]
        assert len(health_calls) == 0


class TestHelperInvocation:
    def test_uses_helper_when_mcp_configured(self, tmp_path):
        agent = _make_agent(tmp_path)
        agent.set_mcp_server(_fake_server(token="abc-123"))

        # Simulate a successful round end-to-end (health check OK,
        # codex exec OK, no marker, output captured).
        def execute_router(cmd, *args, **kwargs):
            if "/healthz" in cmd:
                return {"output": "OK", "returncode": 0}
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}  # no marker
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run()

        codex_lines = [
            c for c in _executions(agent.environment)
            if HELPER_SCRIPT_PATH in c
        ]
        assert len(codex_lines) == 1
        line = codex_lines[0]
        # Helper-driven invocation — codex binary itself dropped in
        # favour of the wrapper.
        assert HELPER_SCRIPT_PATH in line
        # MCP env vars exported on the same shell line.
        assert "INVERSE_CODEX_MCP_URL=" in line
        assert "INVERSE_CODEX_MCP_TOKEN=" in line
        assert "abc-123" in line  # token is exported
        assert "INVERSE_CODEX_MAX_SECS=240" in line  # from codex_cfg
        assert "INVERSE_CODEX_MARKER=" in line
        # CODEX_HOME is still exported alongside the helper env.
        assert f"CODEX_HOME={CODEX_HOME_PATH}" in line
        # subcommand `exec ...` follows the helper path.
        assert " exec " in line

    def test_falls_back_to_direct_codex_without_mcp(self, tmp_path):
        agent = _make_agent(tmp_path)
        # No set_mcp_server.

        def execute_router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run()

        all_execs = _executions(agent.environment)
        assert not any(HELPER_SCRIPT_PATH in c for c in all_execs)
        # We do see direct codex exec.
        codex_lines = [c for c in all_execs if "codex" in c and "exec" in c]
        assert len(codex_lines) == 1
        # And no INVERSE_CODEX_MCP_URL / TOKEN env vars.
        assert "INVERSE_CODEX_MCP_URL" not in codex_lines[0]
        assert "INVERSE_CODEX_MCP_TOKEN" not in codex_lines[0]


class TestProbeCountFromMcp:
    def test_probe_count_pulled_from_mcp_end_round(self, tmp_path):
        """When an MCP server is wired up, the agent's trajectory and
        agent_stats must reflect the server's per-round probes_used,
        not the legacy ``self._probe_count`` field (which stays 0 for
        codex because run_probe goes through the MCP tool, not the
        ClashAgent in-prompt PROBE_SUBMIT path)."""
        agent = _make_agent(tmp_path)
        server = _fake_server()
        server.end_round.return_value = {
            "round_num": 1,
            "submitted": True,
            "probes_used": 3,
            "max_probes": 5,
        }
        agent.set_mcp_server(server)

        def execute_router(cmd, *args, **kwargs):
            if "/healthz" in cmd:
                return {"output": "OK", "returncode": 0}
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run()

        traj = json.loads(
            (tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json").read_text()
        )
        assert traj["probe_count"] == 3
        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["probe_count"] == 3
        history = agent.get_metadata()["inverse_strategy"]["evaluation_history"]
        assert history[-1]["probe_count"] == 3

    def test_probe_count_falls_back_to_zero_without_mcp(self, tmp_path):
        """No MCP server means we have no authoritative count; the
        agent's legacy ``_probe_count`` stays 0 and the trajectory
        reflects that rather than crashing on the missing server."""
        agent = _make_agent(tmp_path)

        def execute_router(cmd, *args, **kwargs):
            if cmd.startswith("test -f"):
                return {"output": "", "returncode": 1}
            return {"output": "", "returncode": 0}

        agent.environment.execute.side_effect = execute_router

        with patch("revenge_bench.agents.codex_agent.create_file_in_container"), \
             patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent.run()

        traj = json.loads(
            (tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json").read_text()
        )
        assert traj["probe_count"] == 0
