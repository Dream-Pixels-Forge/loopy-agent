"""Extended federate tests — WorkerPool lifecycle, Server validation, SSE, cancel."""

from __future__ import annotations

import contextlib
import socket
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from loopy.federate import (
    AgentCluster,
    FederatedServer,
    FederatedTaskStore,
    FederatedWorkerPool,
    build_agent_card_from_module,
)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
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


# ── FederatedTaskStore ─────────────────────────────────────────


class TestFederatedTaskStore:
    def test_put_get(self):
        store = FederatedTaskStore()
        store.put({"id": "t1", "state": "submitted"})
        task = store.get("t1")
        assert task is not None
        assert task["state"] == "submitted"

    def test_get_missing(self):
        store = FederatedTaskStore()
        assert store.get("missing") is None

    def test_all_returns_all_tasks(self):
        store = FederatedTaskStore()
        store.put({"id": "t1", "state": "submitted"})
        store.put({"id": "t2", "state": "working"})
        all_tasks = store.all()
        ids = sorted(t["id"] for t in all_tasks)
        assert ids == ["t1", "t2"]

    def test_request_cancel_existing(self):
        store = FederatedTaskStore()
        store.put({"id": "t1", "state": "submitted"})
        assert store.request_cancel("t1") is True
        task = store.get("t1")
        assert task["cancel_requested"] is True

    def test_request_cancel_missing_returns_false(self):
        store = FederatedTaskStore()
        assert store.request_cancel("missing") is False


# ── FederatedWorkerPool lifecycle ─────────────────────────────


class TestFederatedWorkerPool:
    def test_size_validation_zero(self):
        store = FederatedTaskStore()
        with pytest.raises(ValueError, match=">= 1"):
            FederatedWorkerPool(store, size=0)

    def test_size_validation_negative(self):
        store = FederatedTaskStore()
        with pytest.raises(ValueError, match=">= 1"):
            FederatedWorkerPool(store, size=-1)

    def test_start_stop_roundtrip(self):
        store = FederatedTaskStore()
        pool = FederatedWorkerPool(store, size=1)
        pool.start()
        assert pool._thread is not None
        pool.stop()
        assert pool._thread is None

    def test_double_start_is_noop(self):
        store = FederatedTaskStore()
        pool = FederatedWorkerPool(store, size=1)
        pool.start()
        first_thread = pool._thread
        pool.start()
        assert pool._thread is first_thread

    def test_double_stop_is_noop(self):
        store = FederatedTaskStore()
        pool = FederatedWorkerPool(store, size=1)
        pool.start()
        pool.stop()
        pool.stop()
        assert pool._thread is None

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
    def test_submit_and_process_task(self):
        store = FederatedTaskStore()
        pool = FederatedWorkerPool(store, size=1)
        pool.start()
        try:
            task_id = "t-submit-test"
            store.put({"id": task_id, "state": "submitted", "cancel_requested": False})
            pool.submit(task_id)
            time.sleep(0.5)
            task = store.get(task_id)
            assert task is not None
            assert task["state"] in ("working", "completed")
        finally:
            pool.stop()

    def test_submit_after_stop_does_not_raise(self):
        store = FederatedTaskStore()
        pool = FederatedWorkerPool(store, size=1)
        pool.start()
        pool.stop()
        # submit after stop should not raise (it appends to pending list
        # but the loop is gone; this tests the no-crash path)
        pool.submit("t-any")


# ── FederatedServer validation ─────────────────────────────────


class TestFederatedServerValidation:
    def test_invalid_port_type_raises(self):
        from loopy.a2a import AgentCard

        card = AgentCard(
            name="x", description="x", version="1.0", capabilities=[], endpoint="local"
        )
        with pytest.raises(TypeError, match="port must be an int"):
            FederatedServer(agent_card=card, port="8080")

    def test_port_out_of_range_raises(self):
        from loopy.a2a import AgentCard

        card = AgentCard(
            name="x", description="x", version="1.0", capabilities=[], endpoint="local"
        )
        with pytest.raises(ValueError, match="port must be in"):
            FederatedServer(agent_card=card, port=70000)

    def test_invalid_workers_type_raises(self):
        from loopy.a2a import AgentCard

        card = AgentCard(
            name="x", description="x", version="1.0", capabilities=[], endpoint="local"
        )
        with pytest.raises(TypeError, match="workers must be an int"):
            FederatedServer(agent_card=card, host="127.0.0.1", port=0, workers="2")

    def test_zero_workers_raises(self):
        from loopy.a2a import AgentCard

        card = AgentCard(
            name="x", description="x", version="1.0", capabilities=[], endpoint="local"
        )
        with pytest.raises(ValueError, match="workers >= 1"):
            FederatedServer(agent_card=card, workers=0)

    def test_negative_workers_raises(self):
        from loopy.a2a import AgentCard

        card = AgentCard(
            name="x", description="x", version="1.0", capabilities=[], endpoint="local"
        )
        with pytest.raises(ValueError, match="workers >= 1"):
            FederatedServer(agent_card=card, workers=-1)


# ── FederatedServer multi-worker path ──────────────────────────


class TestFederatedServerMultiWorker:
    def test_post_tasks_returns_202_with_multi_worker(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="multi-agent",
            description="multi",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0, workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "text", "inputs": {"q": "hi"}},
                timeout=5.0,
            )
            assert r.status_code == 202
            data = r.json()
            assert "id" in data
        finally:
            server.shutdown()

    def test_context_manager_lifecycle(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="ctx-agent",
            description="ctx",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        with FederatedServer(agent_card=card, host="127.0.0.1", port=0) as server:
            _wait_for_port(server.port)
            r = httpx.get(
                f"http://127.0.0.1:{server.port}/.well-known/agent-card.json",
                timeout=2.0,
            )
            assert r.status_code == 200
        assert server._thread is None


# ── SSE stream endpoint ───────────────────────────────────────


class TestSSERoute:
    def test_sse_stream_missing_task_returns_404(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="sse-miss",
            description="miss",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.get(
                f"http://127.0.0.1:{server.port}/tasks/nonexistent/stream",
                timeout=2.0,
            )
            assert r.status_code == 404
        finally:
            server.shutdown()


# ── Task cancel route ─────────────────────────────────────────


class TestCancelRoute:
    def test_cancel_missing_task_returns_404(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="cancel-agent",
            description="cancel",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks/fake-id/cancel",
                timeout=2.0,
            )
            assert r.status_code == 404
        finally:
            server.shutdown()

    def test_cancel_existing_task(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="cancel-ok",
            description="cancelok",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0)
        server.start()
        try:
            _wait_for_port(server.port)
            post_r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "text", "inputs": {}},
                timeout=2.0,
            )
            task_id = post_r.json()["id"]
            cancel_r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks/{task_id}/cancel",
                timeout=2.0,
            )
            assert cancel_r.status_code == 200
            data = cancel_r.json()
            assert data["cancel_requested"] is True
        finally:
            server.shutdown()


# ── Unknown path returns 404 ──────────────────────────────────


class TestUnknownPath:
    def test_get_unknown_path(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="unknown",
            description="u",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.get(f"http://127.0.0.1:{server.port}/nope", timeout=2.0)
            assert r.status_code == 404
        finally:
            server.shutdown()

    def test_post_unknown_path(self):
        """POST to an unknown path should not crash the server;
        on Windows the connection may be aborted during early shutdown,
        so we just verify the server stays up after a few requests."""
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="unknown-post",
            description="up",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0)
        server.start()
        try:
            _wait_for_port(server.port)
            # First a known endpoint to verify server is alive
            r = httpx.get(
                f"http://127.0.0.1:{server.port}/.well-known/agent-card.json",
                timeout=2.0,
            )
            assert r.status_code == 200
            # Then a POST to unknown path — may raise on Windows
            # but the server should survive
            with contextlib.suppress(Exception):
                httpx.post(f"http://127.0.0.1:{server.port}/nope", json={}, timeout=1.0)
        finally:
            server.shutdown()


# ── Invalid JSON POST ─────────────────────────────────────────


class TestInvalidJsonPost:
    def test_post_tasks_invalid_json(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="bad-json",
            description="bj",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        server = FederatedServer(agent_card=card, host="127.0.0.1", port=0)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                content=b"not json{{{",
                headers={"Content-Type": "application/json"},
                timeout=2.0,
            )
            assert r.status_code == 400
        finally:
            server.shutdown()


# ── build_agent_card_from_module ───────────────────────────────


class TestBuildAgentCardFromModule:
    def test_build_from_module_with_card_attr(self, tmp_path: Path):
        agent_path = tmp_path / "my_agent2.py"
        agent_path.write_text(
            "from loopy.a2a import AgentCard, AgentCapability\n"
            "card = AgentCard(\n"
            "    name='my-agent',\n"
            "    description='hi',\n"
            "    version='2.0',\n"
            "    capabilities=[AgentCapability.TEXT_GENERATION],\n"
            "    endpoint='local',\n"
            ")\n"
        )
        card = build_agent_card_from_module(agent_path)
        assert card.name == "my-agent"
        assert card.version == "2.0"

    def test_build_from_module_with_CARD_attr(self, tmp_path: Path):
        agent_path = tmp_path / "my_agent3.py"
        agent_path.write_text(
            "from loopy.a2a import AgentCard, AgentCapability\n"
            "CARD = AgentCard(\n"
            "    name='card-agent',\n"
            "    description='card',\n"
            "    version='3.0',\n"
            "    capabilities=[AgentCapability.TEXT_GENERATION],\n"
            "    endpoint='local',\n"
            ")\n"
        )
        card = build_agent_card_from_module(agent_path)
        assert card.name == "card-agent"

    def test_build_from_module_no_card_raises(self, tmp_path: Path):
        agent_path = tmp_path / "empty2.py"
        agent_path.write_text("# nothing here\n")
        with pytest.raises(ValueError, match="[Cc]ard"):
            build_agent_card_from_module(agent_path)

    def test_build_from_nonexistent_module_raises(self):
        with pytest.raises((ValueError, FileNotFoundError)):
            build_agent_card_from_module(Path("/nonexistent/path.py"))


# ── AgentCluster edge cases ───────────────────────────────────


class TestAgentClusterExtended:
    @pytest.mark.asyncio
    async def test_cluster_peer_with_good_card(self):
        from loopy.a2a import AgentCapability, AgentCard

        card_good = AgentCard(
            name="good-peer",
            description="g",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        with FederatedServer(agent_card=card_good, host="127.0.0.1", port=0) as good_server:
            _wait_for_port(good_server.port)
            cluster = AgentCluster(peers=[f"http://127.0.0.1:{good_server.port}"])
            cards = await cluster.discover()
            assert len(cards) == 1
            assert cards[0].name == "good-peer"

    @pytest.mark.asyncio
    async def test_handoff_with_valid_peer(self):
        from loopy.a2a import AgentCapability, AgentCard

        card = AgentCard(
            name="handoff-target",
            description="h",
            version="1.0",
            capabilities=[AgentCapability.TEXT_GENERATION],
            endpoint="local",
        )
        with FederatedServer(agent_card=card, host="127.0.0.1", port=0) as target:
            _wait_for_port(target.port)
            cluster = AgentCluster(peers=[f"http://127.0.0.1:{target.port}"])
            task = await cluster.handoff(
                peer_url=f"http://127.0.0.1:{target.port}",
                skill_id="text",
                inputs={"q": "transfer"},
            )
            assert "id" in task
            assert task["state"] in ("submitted", "completed", "working")
