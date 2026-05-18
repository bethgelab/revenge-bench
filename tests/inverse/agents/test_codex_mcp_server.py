"""End-to-end tests for the Codex MCP server.

Starts the server in a background thread, drives MCP tool calls over
HTTP using a real MCP client, and verifies:
- bearer auth gates every endpoint except /healthz,
- begin_round() resets per-round state and clears the submit marker,
- submit() writes the marker into the (mocked) learner container,
- run_probe() delegates to the probe callback and enforces the budget,
- get_probe_budget / get_round_budget return current state.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import httpx
import pytest

from revenge_bench.agents.codex_mcp import (
    SUBMIT_MARKER_PATH,
    CodexMCPServer,
)


@pytest.fixture
def mock_env():
    env = MagicMock()
    env.execute.return_value = {"output": "", "returncode": 0}
    return env


@pytest.fixture
def server(mock_env):
    """Start a server, yield it, stop it. One per test for clean state."""
    s = CodexMCPServer(learner_environment=mock_env, host="127.0.0.1")
    s.start()
    try:
        yield s
    finally:
        s.stop()


class TestLifecycle:
    def test_start_idempotent_within_lifetime(self, server, mock_env):
        # Already started by fixture; second start() must be a no-op
        # (re-start after stop is not supported — see MCP SDK constraint
        # that StreamableHTTPSessionManager.run() can only run once).
        server.start()
        server.start()

    def test_healthz_unauthenticated(self, server):
        r = httpx.get(f"{server.base_url}/healthz", timeout=5.0)
        assert r.status_code == 200
        assert r.json()["service"] == "inverse-codex-mcp"

    def test_unauthenticated_request_rejected(self, server):
        # No Authorization header → 401, even for /mcp.
        r = httpx.post(
            f"{server.base_url}{server.mcp_path}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            timeout=5.0,
        )
        assert r.status_code == 401

    def test_wrong_token_rejected(self, server):
        r = httpx.post(
            f"{server.base_url}{server.mcp_path}",
            headers={"Authorization": "Bearer wrong-token"},
            timeout=5.0,
        )
        assert r.status_code == 401


# ---------- MCP client helper ----------


async def _call_tool(server: CodexMCPServer, name: str, args: dict | None = None) -> dict:
    """Call a tool via the real MCP streamable-HTTP client."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {server.token}"}
    url = f"{server.base_url}{server.mcp_path}"
    # New mcp client API takes an httpx.AsyncClient instead of headers
    # kwarg; pre-build one with the auth header set.
    async with httpx.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, args or {})
    # FastMCP returns the tool's dict serialized as JSON in a TextContent
    # block. Extract and decode.
    if result.content and result.content[0].type == "text":
        try:
            return json.loads(result.content[0].text)
        except json.JSONDecodeError:
            return {"_raw": result.content[0].text}
    return {}


def _run(coro):
    return asyncio.run(coro)


class TestSubmitTool:
    def test_submit_without_active_round_returns_error(self, server):
        result = _run(_call_tool(server, "submit"))
        assert "error" in result

    def test_submit_writes_marker_and_flips_state(self, server, mock_env):
        # Capture create_file_in_container calls (we patch it where it's
        # used, which is inside the codex_mcp module).
        from unittest.mock import patch

        server.begin_round(
            round_num=1, max_round_seconds=300,
            max_probes=5, probe_callback=None,
        )
        with patch("revenge_bench.agents.codex_mcp.create_file_in_container") as mock_create:
            result = _run(_call_tool(server, "submit"))

        assert result["accepted"] is True
        assert "Stop editing" in result["instructions"]
        # Marker was written into the container at the canonical path.
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["dest_path"] == SUBMIT_MARKER_PATH
        # Round-state flipped to submitted=True.
        summary = server.end_round()
        assert summary["submitted"] is True


class TestProbeTool:
    def test_run_probe_without_callback(self, server):
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=5, probe_callback=None,
        )
        result = _run(_call_tool(server, "run_probe"))
        assert "error" in result
        assert "probing not enabled" in result["error"]

    def test_run_probe_delegates_to_callback(self, server):
        callback = MagicMock(return_value=json.dumps({"hello": "world"}))
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=3, probe_callback=callback,
        )
        result = _run(_call_tool(server, "run_probe"))
        callback.assert_called_once()
        assert result["probe_index"] == 1
        assert result["max_probes"] == 3
        assert result["result"] == {"hello": "world"}

    def test_run_probe_enforces_budget(self, server):
        callback = MagicMock(return_value="{}")
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=2, probe_callback=callback,
        )
        # Two successful probes...
        r1 = _run(_call_tool(server, "run_probe"))
        r2 = _run(_call_tool(server, "run_probe"))
        # ...third should fail with budget error.
        r3 = _run(_call_tool(server, "run_probe"))
        assert r1["probe_index"] == 1
        assert r2["probe_index"] == 2
        assert "error" in r3
        assert "budget exhausted" in r3["error"]
        assert callback.call_count == 2  # third call never made

    def test_run_probe_returns_raw_when_callback_string_not_json(self, server):
        callback = MagicMock(return_value="not-json output")
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=3, probe_callback=callback,
        )
        result = _run(_call_tool(server, "run_probe"))
        assert result["result"] == "not-json output"

    def test_run_probe_callback_exception_returns_error(self, server):
        callback = MagicMock(side_effect=RuntimeError("probe blew up"))
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=3, probe_callback=callback,
        )
        result = _run(_call_tool(server, "run_probe"))
        assert "error" in result
        assert "probe blew up" in result["error"]


class TestBudgetTools:
    def test_get_probe_budget(self, server):
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=5,
            probe_callback=MagicMock(return_value="{}"),
        )
        # Use one probe.
        _run(_call_tool(server, "run_probe"))
        result = _run(_call_tool(server, "get_probe_budget"))
        assert result == {"used": 1, "max": 5, "remaining": 4}

    def test_get_round_budget_with_cap(self, server):
        server.begin_round(
            round_num=2, max_round_seconds=120,
            max_probes=5, probe_callback=None,
        )
        result = _run(_call_tool(server, "get_round_budget"))
        assert result["round_num"] == 2
        assert result["max_round_seconds"] == 120
        # elapsed is small; remaining ~120
        assert 0 <= result["elapsed_seconds"] < 5
        assert 115 <= result["remaining_seconds"] <= 120
        assert result["max_probes"] == 5

    def test_get_round_budget_without_cap(self, server):
        server.begin_round(
            round_num=1, max_round_seconds=None,
            max_probes=5, probe_callback=None,
        )
        result = _run(_call_tool(server, "get_round_budget"))
        assert result["max_round_seconds"] is None
        assert result["remaining_seconds"] is None


class TestBeginRoundResetsMarker:
    def test_begin_round_clears_stale_marker(self, server, mock_env):
        # After begin_round we expect an `rm -f` of the marker.
        mock_env.execute.reset_mock()
        server.begin_round(
            round_num=3, max_round_seconds=None,
            max_probes=5, probe_callback=None,
        )
        rm_calls = [
            c for c in mock_env.execute.call_args_list
            if c.args and "rm -f" in c.args[0] and SUBMIT_MARKER_PATH in c.args[0]
        ]
        assert len(rm_calls) == 1
