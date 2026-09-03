"""v1.0.0 — Federated Runtime.

Expose an :class:`AgentLoop` over HTTP so other agents can call
it via the A2A v1.0 protocol, and connect to N peers via
:class:`AgentCluster` for peer-to-peer handoff.

The HTTP server is built on Python's stdlib ``http.server`` so
``loopy-agent`` stays zero-deps-core. Tests can drive the
endpoints with ``httpx`` (already a core dep).
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from loopy.a2a import AgentCard

logger = logging.getLogger("loopy.federate")


# ── FederatedServer ──────────────────────────────────────────


# In-process task store keyed by task id. Simple, in-memory; the
# federation protocol is intentionally minimal.
_TASK_STORE: dict[str, dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()


def _register_task(task: dict[str, Any]) -> None:
    with _TASK_LOCK:
        _TASK_STORE[task["id"]] = task


def _get_task(task_id: str) -> dict[str, Any] | None:
    with _TASK_LOCK:
        return _TASK_STORE.get(task_id)


class _FederatedHandler(BaseHTTPRequestHandler):
    """HTTP handler that exposes the A2A card + task endpoints.

    The handler is configured per-server via :class:`FederatedServer`
    attributes (BaseHTTPRequestHandler uses class-level config).
    """

    server_version = "loopy-federate/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — stdlib signature
        logger.debug(format, *args)

    def do_GET(self) -> None:  # noqa: N802 — stdlib signature
        parsed = urlparse(self.path)
        if parsed.path == "/.well-known/agent-card.json":
            self._send_json(200, self.server.agent_card.to_dict())  # type: ignore[attr-defined]
            return
        if parsed.path.startswith("/tasks/"):
            task_id = parsed.path.split("/tasks/", 1)[1]
            task = _get_task(task_id)
            if task is None:
                self._send_json(404, {"error": f"task {task_id!r} not found"})
                return
            self._send_json(200, task)
            return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    def do_POST(self) -> None:  # noqa: N802 — stdlib signature
        parsed = urlparse(self.path)
        if parsed.path == "/tasks":
            try:
                payload = self._read_json()
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return

            task_id = f"t-{uuid.uuid4().hex[:12]}"
            task = {
                "id": task_id,
                "state": "submitted",
                "skill_id": payload.get("skill_id", ""),
                "inputs": payload.get("inputs", {}),
                "artifacts": [],
            }
            _register_task(task)
            self._send_json(200, task)
            return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    # ── helpers ────────────────────────────────────────────

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FederatedServer:
    """v1.0.0 — minimal HTTP server exposing an :class:`AgentCard`
    plus ``POST /tasks`` and ``GET /tasks/{id}``.

    Built on :class:`ThreadingHTTPServer` so requests are
    served on a background thread. ``port=0`` lets the OS pick a
    free port (tests use this).
    """

    def __init__(
        self,
        agent_card: AgentCard,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.agent_card = agent_card
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> FederatedServer:
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.shutdown()

    def start(self) -> None:
        httpd = ThreadingHTTPServer((self.host, self.port), _FederatedHandler)
        httpd.agent_card = self.agent_card  # type: ignore[attr-defined]
        self._httpd = httpd

        def _serve() -> None:
            try:
                httpd.serve_forever()
            except OSError as exc:
                # Late-shutdown errors on Windows (WinError 10038
                # "not a socket") arrive here when the listener has
                # already been closed. Treat as a clean thread exit.
                logger.debug("federated server thread exiting: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("federated server thread crashed: %s", exc)

        self._thread = threading.Thread(target=_serve, daemon=True, name="federated-server")
        self._thread.start()
        # Capture the actually-bound port (when the caller passed 0).
        if self.port == 0:
            self.port = httpd.server_address[1]

    def serve_forever(self) -> None:
        """Block until :meth:`shutdown` is called."""
        if self._httpd is None:
            self.start()
        assert self._httpd is not None
        try:
            self._httpd.serve_forever()
        except OSError as exc:
            # Late shutdown errors on Windows (WinError 10038
            # "not a socket") arrive here when the listener has
            # already been closed. Treat as a clean exit.
            logger.debug("federated server thread exiting: %s", exc)
        except Exception as exc:  # noqa: BLE001
            # Re-raise after logging so genuine failures aren't
            # silently swallowed.
            logger.debug("federated server thread crashed: %s", exc)
            raise

    def shutdown(self) -> None:
        if self._httpd is not None:
            # Force the listening socket closed FIRST so the
            # selector in serve_forever() wakes up immediately on
            # both Linux and Windows. (On Windows, calling
            # ThreadingHTTPServer.shutdown() with the socket still
            # open can race with selector.select() and raise
            # WinError 10038.)
            with contextlib.suppress(Exception):
                self._httpd.socket.close()
            self._httpd.shutdown()
            with contextlib.suppress(Exception):
                self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def server_close(self) -> None:
        # Backwards-compat alias used by tests.
        self.shutdown()


# ── AgentCluster ────────────────────────────────────────────


class AgentCluster:
    """v1.0.0 — federation client. Connects to N peers, discovers
    their Agent Cards, and hands off tasks peer-to-peer.

    Args:
        peers: List of base URLs (e.g.
            ``["http://agent-a:8080", "http://agent-b:8081"]``).
    """

    def __init__(self, peers: list[str]) -> None:
        self.peers = list(peers)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AgentCluster:
        self._client = httpx.AsyncClient(timeout=10.0)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def discover(self) -> list[AgentCard]:
        """GET ``/.well-known/agent-card.json`` on every peer.

        Returns the parsed cards in arbitrary order. A peer that
        returns 404 or is unreachable is silently skipped.
        """
        client = self._get_client()
        cards: list[AgentCard] = []
        for peer in self.peers:
            url = peer.rstrip("/") + "/.well-known/agent-card.json"
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                logger.warning("Cluster peer %s unreachable: %s", peer, exc)
                continue
            if resp.status_code != 200:
                continue
            try:
                cards.append(AgentCard.from_dict(resp.json()))
            except (ValueError, TypeError) as exc:
                logger.warning("Cluster peer %s returned bad card: %s", peer, exc)
        return cards

    async def handoff(
        self,
        peer_url: str,
        skill_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """POST a task to ``peer_url`` and return the JSON response."""
        client = self._get_client()
        url = peer_url.rstrip("/") + "/tasks"
        resp = await client.post(
            url,
            json={"skill_id": skill_id, "inputs": inputs},
        )
        resp.raise_for_status()
        return resp.json()


# ── CLI helper: build a card from a user module ──────────────


def build_agent_card_from_module(path: str | Path) -> AgentCard:
    """Load a Python module from ``path`` and return the
    :class:`AgentCard` it exposes as ``CARD`` (uppercase) or
    ``agent_card`` (lowercase).

    Raises:
        ValueError: when the module has neither attribute.
    """
    file_path = Path(path)
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr in ("CARD", "card", "AGENT_CARD", "agent_card"):
        candidate = getattr(module, attr, None)
        if isinstance(candidate, AgentCard):
            return candidate

    raise ValueError(
        f"Module {path} has no AgentCard attribute (looked for CARD, card, AGENT_CARD, agent_card)"
    )
