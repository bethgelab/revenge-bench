"""
Tournament-scoped HTTP MCP server for the Codex inverse learner.

One server per tournament run. The tournament starts it before the first
`codex exec` (so Codex can register the URL via `codex mcp add` under
the per-tournament `CODEX_HOME`), reuses it across rounds, and tears it
down in cleanup.

Exposed tools (intentionally narrow):

- ``submit()``: write the submit marker into the learner container,
  signalling the round is intentionally complete. The image-baked
  watchdog (`revenge-codex-exec`) sees the marker and gracefully
  terminates Codex.
- ``run_probe()``: delegate to the tournament's probe callback (which
  is the existing ``_run_inline_probe`` method on
  ``InverseStrategyInterventionistTournament``). Probe execution lives
  there so we don't duplicate game-specific code.
- ``get_probe_budget()``: used/max probes for the current round.
- ``get_round_budget()``: elapsed seconds, remaining seconds (if a
  wall-clock cap is set), and probe usage.

Auth is a per-run bearer token; the agent passes ``MCP_URL`` and
``MCP_TOKEN`` to Codex via env vars so the CLI can forward them on each
tool call. The server binds on ``0.0.0.0`` so containers can reach the
host via ``host.docker.internal`` (Linux requires
``--add-host=host.docker.internal:host-gateway`` on docker run; that's
plumbed in a separate stage).
"""

from __future__ import annotations

import asyncio
import json
import secrets
import shlex
import socket
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from revenge_bench.utils.environment import (
    ContainerEnvironment,
    create_file_in_container,
)
from revenge_bench.utils.log import get_logger

# Marker path inside the learner container — kept identical to the
# constant in `codex_agent.py` so the two modules stay in sync.
SUBMIT_MARKER_PATH = "/workspace/.revenge_bench/submitted.json"

# Type alias for the tournament's probe callback. The existing
# `_run_inline_probe` returns a string (typically JSON); we wrap it.
ProbeCallback = Callable[[], str]


def _free_port() -> int:
    """Ask the OS for a free TCP port we can bind to.

    There's a tiny TOCTOU window between this call and uvicorn binding,
    but for the smoke test path it's more than acceptable.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests missing the per-run bearer token.

    Skips auth on a single ``/healthz`` GET so the agent's connectivity
    preflight from the learner container can confirm reachability before
    Codex runs (and before Codex has the token plumbed).
    """

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._expected = f"Bearer {token}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        if request.headers.get("authorization") != self._expected:
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
            )
        return await call_next(request)


class CodexMCPServer:
    """Tournament-scoped HTTP MCP server.

    Lifecycle:
        server = CodexMCPServer(learner_environment=env)
        server.start()
        try:
            for round_num in rounds:
                server.begin_round(
                    round_num=round_num,
                    max_round_seconds=300,
                    max_probes=5,
                    probe_callback=tournament._run_inline_probe,
                )
                # ... codex exec runs, tools may be called ...
                summary = server.end_round()
        finally:
            server.stop()

    Note: start/stop is one-shot — the MCP SDK's session manager refuses
    a second `run()` on the same instance. Recreate the server if you
    need a fresh one.
    """

    def __init__(
        self,
        *,
        learner_environment: ContainerEnvironment,
        host: str = "0.0.0.0",
        port: int = 0,
    ) -> None:
        self._env = learner_environment
        self._host = host
        # Resolve port up front so callers can build the URL before
        # `start()` returns. uvicorn will rebind to this port; if it's
        # taken in the brief window between _free_port() and bind, we
        # fail loudly rather than silently picking a different one.
        self._port = port if port else _free_port()
        self._token = secrets.token_urlsafe(32)
        self.logger = get_logger("codex-mcp", emoji="🛰")

        # Per-round state. Mutated by `begin_round` and read by tools.
        # Using a single dict so future tournaments could swap state
        # without re-creating the server.
        self._round_state: dict[str, Any] = {
            "round_num": None,
            "started_at": None,
            "max_round_seconds": None,
            "max_probes": 0,
            "probes_used": 0,
            "submitted": False,
            "probe_callback": None,
        }

        self._mcp = FastMCP("revenge-codex", host=host, port=self._port)
        self._register_tools()

        self._uvicorn_server: uvicorn.Server | None = None
        self._uvicorn_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ #
    # Connection details for the agent
    # ------------------------------------------------------------------ #

    @property
    def token(self) -> str:
        return self._token

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        """URL to reach this server *from the host*. Containers should
        substitute the host portion with `host.docker.internal`.
        """
        # 0.0.0.0 means "any interface"; from the host's own perspective
        # localhost works.
        host = "127.0.0.1" if self._host == "0.0.0.0" else self._host
        return f"http://{host}:{self._port}"

    @property
    def container_base_url(self) -> str:
        """URL Codex should hit *from inside a Docker container*."""
        return f"http://host.docker.internal:{self._port}"

    @property
    def mcp_path(self) -> str:
        return self._mcp.settings.streamable_http_path

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the HTTP server in a background thread.

        Returns when uvicorn has bound the port (or raises if it failed
        to start within a short timeout).
        """
        if self._uvicorn_thread is not None:
            return

        app = self._mcp.streamable_http_app()
        # Add bearer auth and a /healthz route in front of the MCP app.
        app.add_middleware(_BearerAuthMiddleware, token=self._token)

        async def healthz(request):
            return JSONResponse({"ok": True, "service": "revenge-codex-mcp"})

        app.add_route("/healthz", healthz, methods=["GET"])

        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
            lifespan="on",
        )
        self._uvicorn_server = uvicorn.Server(config)

        ready = threading.Event()

        def run_in_thread() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                # Mark ready once uvicorn flips its `started` flag.
                async def _serve() -> None:
                    serve_task = asyncio.ensure_future(self._uvicorn_server.serve())
                    while not self._uvicorn_server.started:
                        await asyncio.sleep(0.05)
                    ready.set()
                    await serve_task

                self._loop.run_until_complete(_serve())
            finally:
                self._loop.close()

        self._uvicorn_thread = threading.Thread(
            target=run_in_thread,
            name="codex-mcp-uvicorn",
            daemon=True,
        )
        self._uvicorn_thread.start()
        if not ready.wait(timeout=10.0):
            raise RuntimeError(
                f"CodexMCPServer failed to bind {self._host}:{self._port} within 10s"
            )
        self.logger.info(
            f"MCP server up at {self.base_url}{self.mcp_path} "
            f"(container-side: {self.container_base_url}{self.mcp_path})"
        )

    def stop(self) -> None:
        """Signal uvicorn to exit and join the thread."""
        if self._uvicorn_server is None:
            return
        self._uvicorn_server.should_exit = True
        if self._uvicorn_thread is not None:
            self._uvicorn_thread.join(timeout=5.0)
            if self._uvicorn_thread.is_alive():
                self.logger.warning("MCP server thread did not exit within 5s")
        self._uvicorn_server = None
        self._uvicorn_thread = None
        self._loop = None
        self.logger.info("MCP server stopped")

    # ------------------------------------------------------------------ #
    # Per-round configuration (called by tournament before each round)
    # ------------------------------------------------------------------ #

    def begin_round(
        self,
        *,
        round_num: int,
        max_round_seconds: float | None,
        max_probes: int,
        probe_callback: ProbeCallback | None,
    ) -> None:
        """Reset round state and clear any stale submit marker."""
        self._round_state.update(
            round_num=round_num,
            started_at=time.monotonic(),
            max_round_seconds=max_round_seconds,
            max_probes=max_probes,
            probes_used=0,
            submitted=False,
            probe_callback=probe_callback,
        )
        # Fresh start: no stale marker from previous rounds.
        self._env.execute(f"rm -f {shlex.quote(SUBMIT_MARKER_PATH)}")

    def end_round(self) -> dict[str, Any]:
        """Return per-round summary; called after `codex exec` returns."""
        return {
            "round_num": self._round_state["round_num"],
            "submitted": self._round_state["submitted"],
            "probes_used": self._round_state["probes_used"],
            "max_probes": self._round_state["max_probes"],
        }

    # ------------------------------------------------------------------ #
    # Tool registration
    # ------------------------------------------------------------------ #

    def _register_tools(self) -> None:
        mcp = self._mcp
        state = self._round_state

        @mcp.tool(
            name="submit",
            description=(
                "Mark the current round as intentionally complete. After "
                "calling this, finish whatever you're doing and stop "
                "editing — the tournament will evaluate /workspace as-is."
            ),
        )
        async def submit() -> dict[str, Any]:
            if state["round_num"] is None:
                return {"error": "no active round"}
            # Build a small JSON marker so debug tooling can tell which
            # round produced it. Synchronously write through the
            # container env (this method is async but the container
            # exec is sync; call directly — it's fast enough).
            payload = json.dumps(
                {
                    "round": state["round_num"],
                    "submitted_at": time.time(),
                }
            )
            create_file_in_container(
                self._env,
                content=payload,
                dest_path=SUBMIT_MARKER_PATH,
            )
            state["submitted"] = True
            return {
                "accepted": True,
                "instructions": (
                    "Submission accepted. Stop editing immediately; the "
                    "tournament will evaluate the current state of "
                    "/workspace."
                ),
            }

        @mcp.tool(
            name="run_probe",
            description=(
                "Run a probe simulation: your current probe.py vs the "
                "target. Returns mismatch data showing how the target "
                "behaves in the scenarios your probe creates. Edit "
                "probe.py to test specific hypotheses about the target's "
                "decision rules. Limited to max_probes_per_round per round."
            ),
        )
        async def run_probe() -> dict[str, Any]:
            cb = state["probe_callback"]
            if cb is None:
                return {"error": "probing not enabled in this tournament"}
            if state["probes_used"] >= state["max_probes"]:
                return {
                    "error": "probe budget exhausted",
                    "used": state["probes_used"],
                    "max": state["max_probes"],
                }
            # Probe callbacks are sync; offload so we don't block the
            # event loop while game-specific code runs.
            try:
                raw = await asyncio.to_thread(cb)
            except Exception as e:  # noqa: BLE001 — surface to the model
                return {"error": f"probe failed: {e}"}
            state["probes_used"] += 1
            # Try to decode as JSON for nicer agent UX; fall back to raw
            # string if the callback returned plain text.
            parsed: Any
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, json.JSONDecodeError):
                parsed = raw
            return {
                "probe_index": state["probes_used"],
                "max_probes": state["max_probes"],
                "result": parsed,
            }

        @mcp.tool(
            name="get_probe_budget",
            description="Return how many probes you've used and your maximum for this round.",
        )
        async def get_probe_budget() -> dict[str, Any]:
            return {
                "used": state["probes_used"],
                "max": state["max_probes"],
                "remaining": max(0, state["max_probes"] - state["probes_used"]),
            }

        @mcp.tool(
            name="get_round_budget",
            description=(
                "Return the round's wall-clock + probe budget status: "
                "elapsed seconds since the round started, remaining "
                "seconds (if a cap is set), and probe usage."
            ),
        )
        async def get_round_budget() -> dict[str, Any]:
            started = state["started_at"]
            elapsed = (time.monotonic() - started) if started else 0.0
            max_secs = state["max_round_seconds"]
            remaining = (max_secs - elapsed) if max_secs is not None else None
            return {
                "round_num": state["round_num"],
                "elapsed_seconds": round(elapsed, 2),
                "remaining_seconds": (
                    round(remaining, 2) if remaining is not None else None
                ),
                "max_round_seconds": max_secs,
                "probes_used": state["probes_used"],
                "max_probes": state["max_probes"],
            }
