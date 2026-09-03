"""T3.3.1 — Federated Runtime (v1.0.0).

Covers:
  * ``python -m loopy serve --port N`` exposes an HTTP server
  * ``GET /.well-known/agent-card.json`` returns a valid Agent Card
  * ``POST /tasks`` with valid input returns a task id
  * ``GET /tasks/{id}`` returns the task state
  * ``AgentCluster(peers)`` connects to N peers and hands off
    tasks peer-to-peer
  * Peer A and peer B can hand off tasks to each other
"""

from __future__ import annotations

import socket
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from loopy.a2a import AgentCapability, AgentCard
from loopy.federate import (
    AgentCluster,
    FederatedServer,
    build_agent_card_from_module,
)

# ── Server lifecycle helpers ─────────────────────────────────


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    """Block until something is listening on ``port``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(0.2)
                s.connect(("127.0.0.1", port))
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"port {port} never opened")


# ── Server endpoints ─────────────────────────────────────────


class TestServerEndpoints:
    def _make_server(self, card: AgentCard | None = None) -> FederatedServer:
        card = card or AgentCard(
            name="test-agent",
            description="test",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        return FederatedServer(agent_card=card, host="127.0.0.1", port=0)

    def test_agent_card_endpoint_returns_valid_json(self):
        server = self._make_server()
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.get(
                f"http://127.0.0.1:{server.port}/.well-known/agent-card.json",
                timeout=2.0,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["name"] == "test-agent"
            assert data["version"] == "1.0"
        finally:
            server.shutdown()

    def test_post_tasks_returns_task_id(self):
        server = self._make_server()
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "text", "inputs": {"q": "hi"}},
                timeout=2.0,
            )
            assert r.status_code == 200
            data = r.json()
            assert "id" in data
            assert "state" in data
        finally:
            server.shutdown()

    def test_get_task_returns_state(self):
        server = self._make_server()
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "text", "inputs": {"q": "hi"}},
                timeout=2.0,
            )
            task_id = r.json()["id"]
            r2 = httpx.get(f"http://127.0.0.1:{server.port}/tasks/{task_id}", timeout=2.0)
            assert r2.status_code == 200
            data = r2.json()
            assert data["id"] == task_id
        finally:
            server.shutdown()


# ── AgentCluster (peer-to-peer handoff) ──────────────────────


class TestAgentCluster:
    @pytest.mark.asyncio
    async def test_cluster_discovers_peers_via_agent_card(self):
        card_a = AgentCard(
            name="peer-a",
            description="a",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        card_b = AgentCard(
            name="peer-b",
            description="b",
            version="1.0",
            capabilities=[AgentCapability.RESEARCH],
            endpoint="local",
        )
        with (
            FederatedServer(agent_card=card_a, host="127.0.0.1", port=0) as sa,
            FederatedServer(agent_card=card_b, host="127.0.0.1", port=0) as sb,
        ):
            _wait_for_port(sa.port)
            _wait_for_port(sb.port)

            cluster = AgentCluster(
                peers=[f"http://127.0.0.1:{sa.port}", f"http://127.0.0.1:{sb.port}"]
            )
            cards = await cluster.discover()
            names = sorted(c.name for c in cards)
            assert names == ["peer-a", "peer-b"]

    @pytest.mark.asyncio
    async def test_handoff_between_two_peers(self):
        card_a = AgentCard(
            name="peer-a",
            description="a",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        with FederatedServer(agent_card=card_a, host="127.0.0.1", port=0) as sa:
            _wait_for_port(sa.port)
            cluster = AgentCluster(peers=[f"http://127.0.0.1:{sa.port}"])
            task = await cluster.handoff(
                peer_url=f"http://127.0.0.1:{sa.port}",
                skill_id="text",
                inputs={"q": "hello"},
            )
            assert task["id"]
            assert task["state"] in ("submitted", "completed")

    @pytest.mark.asyncio
    async def test_empty_cluster_discovers_zero_cards(self):
        cluster = AgentCluster(peers=[])
        cards = await cluster.discover()
        assert cards == []

    @pytest.mark.asyncio
    async def test_unreachable_peer_is_silently_skipped(self):
        """A peer that can't be reached is logged + skipped, not
        raised — so a partial network does not break the cluster."""
        cluster = AgentCluster(
            peers=[
                "http://127.0.0.1:1",  # nothing listens on port 1
                "http://127.0.0.1:2",  # nothing on port 2 either
            ]
        )
        cards = await cluster.discover()
        assert cards == []

    @pytest.mark.asyncio
    async def test_handoff_raises_on_http_error(self):
        """``handoff`` propagates HTTPError when the peer returns
        a non-2xx status or the connection fails."""
        import httpx as _httpx

        cluster = AgentCluster(peers=[])
        with pytest.raises(_httpx.HTTPError):
            await cluster.handoff(
                peer_url="http://127.0.0.1:1",  # no listener
                skill_id="text",
                inputs={"q": "x"},
            )


# ── CLI: `loopy serve` ───────────────────────────────────────


class TestServeCLI:
    def test_serve_parser_registers(self):
        from loopy.cli import create_parser

        parser = create_parser()
        # The subcommand must exist even if we don't actually serve
        # (the parser just registers the args).
        args = parser.parse_args(["serve", "--port", "0"])
        assert args.command == "serve"
        assert args.port == 0

    def test_serve_parser_accepts_agent_path(self, tmp_path: Path):
        from loopy.cli import create_parser

        agent_path = tmp_path / "agent.py"
        agent_path.write_text("# stub agent")
        parser = create_parser()
        args = parser.parse_args(["serve", "--port", "8080", "--agent", str(agent_path)])
        assert args.agent == str(agent_path)


# ── AgentCard from a Python module ───────────────────────────


class TestBuildAgentCardFromModule:
    def test_build_from_module_with_agent_card_attr(self, tmp_path: Path):
        agent_path = tmp_path / "my_agent.py"
        agent_path.write_text(
            "from loopy.a2a import AgentCard, AgentCapability\n"
            "CARD = AgentCard(\n"
            "    name='my-agent',\n"
            "    description='hi',\n"
            "    version='1.0',\n"
            "    capabilities=[AgentCapability.TEXT_GENERATION],\n"
            "    endpoint='local',\n"
            ")\n"
        )
        card = build_agent_card_from_module(agent_path)
        assert card.name == "my-agent"
        assert card.version == "1.0"

    def test_module_without_card_raises(self, tmp_path: Path):
        agent_path = tmp_path / "empty.py"
        agent_path.write_text("# nothing here\n")
        with pytest.raises(ValueError, match="[Cc]ard"):
            build_agent_card_from_module(agent_path)
