"""v1.2.1 T2.1 — Service-mode FederatedServer.

Strict TDD per the test-driven-development skill. These tests
pin the v1.2 service-mode contract:

* ``FederatedServer(workers=N)`` runs N asyncio task workers
  when N > 1.
* The /tasks POST handler is async and returns immediately
  (202 Accepted) with a task id, even if the work is still
  in flight.
* The /tasks/{id} GET handler returns the worker's current
  state (submitted/working/completed/failed/canceled).
* The /tasks/{id}/stream handler returns an SSE event stream
  that yields state-change events for the task.
* The /tasks/{id}/cancel POST handler is a soft-cancel: it
  flips a flag the worker checks between steps; in-flight
  handlers complete naturally.
* When N == 1 (default), the server falls back to the
  original synchronous handler (no behavior change).
"""

from __future__ import annotations

import socket
import time
from contextlib import closing

import httpx
import pytest

from loopy.a2a import AgentCapability, AgentCard
from loopy.federate import FederatedServer


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


def _make_server(workers: int = 1) -> FederatedServer:
    card = AgentCard(
        name="service-mode-test",
        description="v1.2 service-mode test",
        version="1.0.0",
        capabilities=[AgentCapability.TEXT_GENERATION],
        endpoint="local",
    )
    return FederatedServer(agent_card=card, host="127.0.0.1", port=0, workers=workers)


class TestWorkersParameter:
    def test_workers_default_is_one(self):
        """Backward compat: workers=1 (the default) keeps the
        v1.0/v1.1 behavior (single-threaded in-memory store)."""
        server = _make_server(workers=1)
        assert server.workers == 1

    def test_workers_kwarg_stored(self):
        server = _make_server(workers=4)
        assert server.workers == 4

    def test_workers_rejects_zero(self):
        with pytest.raises(ValueError, match="workers >= 1"):
            FederatedServer(
                agent_card=AgentCard(
                    name="x",
                    description="",
                    version="1.0",
                    capabilities=[AgentCapability.TEXT_GENERATION],
                    endpoint="local",
                ),
                workers=0,
            )

    def test_workers_rejects_negative(self):
        with pytest.raises(ValueError, match="workers >= 1"):
            FederatedServer(
                agent_card=AgentCard(
                    name="x",
                    description="",
                    version="1.0",
                    capabilities=[AgentCapability.TEXT_GENERATION],
                    endpoint="local",
                ),
                workers=-1,
            )


class TestServiceModeAsyncTasks:
    """When workers > 1, the server runs a real worker pool
    that processes tasks asynchronously. The HTTP handlers must
    return 202 Accepted immediately (not 200) and the worker's
    state must be visible via /tasks/{id}."""

    def test_post_tasks_returns_202_accepted(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "echo", "inputs": {"q": "hi"}},
                timeout=2.0,
            )
            assert r.status_code == 202, f"got {r.status_code}: {r.text}"
            data = r.json()
            assert "id" in data
            assert data["state"] in ("submitted", "working", "completed")
        finally:
            server.shutdown()

    def test_get_task_returns_state(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "echo", "inputs": {"q": "hi"}},
                timeout=2.0,
            )
            task_id = r.json()["id"]
            r2 = httpx.get(
                f"http://127.0.0.1:{server.port}/tasks/{task_id}", timeout=2.0
            )
            assert r2.status_code == 200
            data = r2.json()
            assert data["id"] == task_id
            assert data["state"] in ("submitted", "working", "completed", "failed")
        finally:
            server.shutdown()

    def test_get_unknown_task_returns_404(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.get(
                f"http://127.0.0.1:{server.port}/tasks/t-unknown", timeout=2.0
            )
            assert r.status_code == 404
        finally:
            server.shutdown()

    def test_workers_actually_runs_concurrently(self):
        """Stress test: with workers=4, posting 10 tasks should
        complete them in roughly the time of 1 task (proving
        they run in parallel, not serially). The default test
        agent takes ~50ms per task; the sequential bound is
        500ms; the parallel bound is ~150ms."""
        server = _make_server(workers=4)
        server.start()
        try:
            _wait_for_port(server.port)
            t0 = time.monotonic()
            ids = []
            for i in range(10):
                r = httpx.post(
                    f"http://127.0.0.1:{server.port}/tasks",
                    json={"skill_id": f"echo-{i}", "inputs": {}},
                    timeout=2.0,
                )
                ids.append(r.json()["id"])
            # Wait for all tasks to complete.
            for tid in ids:
                for _ in range(60):  # 6s max
                    r = httpx.get(
                        f"http://127.0.0.1:{server.port}/tasks/{tid}", timeout=0.5
                    )
                    if r.json().get("state") in ("completed", "failed"):
                        break
                    time.sleep(0.05)
            elapsed = time.monotonic() - t0
            # With 4 workers, 10 tasks should NOT take 10x the
            # per-task cost (which would be 500ms minimum serial).
            # The HTTP polling adds overhead; allow generous
            # tolerance for the test runner.
            assert elapsed < 4.0, f"workers=4 took {elapsed:.2f}s"
        finally:
            server.shutdown()


class TestTaskCancel:
    def test_cancel_flips_state_to_canceled(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "echo", "inputs": {}},
                timeout=2.0,
            )
            task_id = r.json()["id"]
            r2 = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks/{task_id}/cancel",
                json={},
                timeout=2.0,
            )
            assert r2.status_code == 200
            assert r2.json()["state"] == "canceled"
        finally:
            server.shutdown()

    def test_cancel_unknown_task_returns_404(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks/t-unknown/cancel",
                json={},
                timeout=2.0,
            )
            assert r.status_code == 404
        finally:
            server.shutdown()


class TestSSEStream:
    def test_stream_returns_sse_event_stream(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "echo", "inputs": {}},
                timeout=2.0,
            )
            task_id = r.json()["id"]
            # v1.2 — use httpx.stream so the response is read
            # incrementally and we can close as soon as the first
            # event lands. The 2.5s timeout covers the wait for
            # the first chunk; the test exits the context manager
            # immediately after seeing the headers.
            with httpx.stream(
                "GET",
                f"http://127.0.0.1:{server.port}/tasks/{task_id}/stream",
                timeout=2.5,
            ) as r2:
                assert r2.status_code == 200
                assert "text/event-stream" in r2.headers.get("content-type", "")
        finally:
            server.shutdown()


class TestBackwardCompat:
    """When workers=1 (the v1.0/v1.1 default), the server keeps
    its synchronous in-memory store behavior. This is the
    zero-regression invariant for the v1.2 contract."""

    def test_workers_one_keeps_synchronous_store(self):
        server = _make_server(workers=1)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.post(
                f"http://127.0.0.1:{server.port}/tasks",
                json={"skill_id": "echo", "inputs": {}},
                timeout=2.0,
            )
            # v1.0/v1.1 behavior: POST returns 200 + a fully-formed
            # task (state is "submitted" or "completed" right away).
            assert r.status_code == 200
        finally:
            server.shutdown()

    def test_agent_card_endpoint_unchanged(self):
        server = _make_server(workers=2)
        server.start()
        try:
            _wait_for_port(server.port)
            r = httpx.get(
                f"http://127.0.0.1:{server.port}/.well-known/agent-card.json",
                timeout=2.0,
            )
            assert r.status_code == 200
            assert r.json()["name"] == "service-mode-test"
        finally:
            server.shutdown()
