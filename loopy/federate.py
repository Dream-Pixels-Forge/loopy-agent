"""v1.0.0 — Federated Runtime.

Expose an :class:`AgentLoop` over HTTP so other agents can call
it via the A2A v1.0 protocol, and connect to N peers via
:class:`AgentCluster` for peer-to-peer handoff.

The HTTP server is built on Python's stdlib ``http.server`` so
``loopy-agent`` stays zero-deps-core. Tests can drive the
endpoints with ``httpx`` (already a core dep).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import logging
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from loopy.a2a import AgentCard

logger = logging.getLogger("loopy.federate")


# ── FederatedServer ──────────────────────────────────────────

# Default per-task simulated work (the test agent sleeps this
# long). Real agents should subclass or wire a custom processor.
# v1.2 — kept short so the test suite can exercise the
# concurrent path without the simulated work dominating the
# wall-clock time.
_DEFAULT_TASK_SLEEP_SECONDS = 0.005
_TASK_LOCK = threading.Lock()


# ── Task store (v1.2 service-mode) ───────────────────────────


class FederatedTaskStore:
    """Thread-safe in-memory store for federated tasks.

    Tasks transition through:
    ``submitted`` → ``working`` → (``completed`` | ``failed`` |
    ``canceled``). A flag-based ``cancel_requested`` lets
    in-flight handlers stop early without aborting the
    underlying process.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, task: dict[str, Any]) -> None:
        with self._lock:
            self._tasks[task["id"]] = task

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tasks.get(task_id)

    def request_cancel(self, task_id: str) -> bool:
        """Mark a task as cancel-requested. Returns True if the
        task existed and was marked; False if it did not exist."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task["cancel_requested"] = True
            return True

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._tasks.values())


class FederatedWorkerPool:
    """v1.2 — pool of N async workers that consume tasks from a
    queue. Each worker simulates a ~50ms agent call. The pool
    uses an :mod:`asyncio` event loop running on a daemon thread
    so the synchronous ``ThreadingHTTPServer`` request loop is
    never blocked.
    """

    def __init__(
        self,
        store: FederatedTaskStore,
        *,
        size: int = 1,
    ) -> None:
        if size < 1:
            raise ValueError("FederatedWorkerPool size must be >= 1")
        self._store = store
        self._size = size
        # v1.2 — ``_queue`` is created lazily inside ``_run`` on
        # the worker's own event loop (an ``asyncio.Queue`` is
        # bound to a specific loop and must not be created from
        # a different thread). ``submit`` schedules the put via
        # ``call_soon_threadsafe`` which is loop-safe.
        # v1.2 — ``_cancel`` is a ``threading.Event`` so it can
        # be set from any thread (it's used as a cross-thread
        # wakeup flag). The worker coroutine polls it via
        # ``await asyncio.sleep(0)`` and ``is_set()`` rather than
        # ``await wait()`` because ``threading.Event.wait()`` is
        # not awaitable.
        self._cancel = threading.Event()
        # v1.2 — a lock-free handoff slot. The HTTP handler
        # writes here synchronously; the worker picks it up
        # in ``_run`` before opening the event loop. This avoids
        # the race where ``submit()`` is called before
        # ``_loop`` is set.
        self._pending_until_loop_ready: list[str] = []
        self._loop_ready = threading.Event()
        # Initialized after the loop starts (the queue is bound
        # to the worker's event loop, not a no-op initial value).
        self._queue: asyncio.Queue[str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._worker_tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._thread is not None:
            return
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="federated-workers"
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        # Schedule a clean shutdown coroutine on the worker's
        # own loop. This is the canonical asyncio shutdown
        # pattern — the coroutine runs in the worker thread
        # (where the loop is alive), so it can `await
        # self._cancel.wait()` safely, then cancel the worker
        # tasks, gather them, and finally call `loop.stop()`
        # which makes `run_until_complete` return.
        #
        # The deadlock we hit previously came from calling
        # ``loop.call_soon_threadsafe(loop.stop)`` directly: when
        # the loop is parked in ``await self._cancel.wait()``,
        # the wakeup queued by ``Event.set()`` and the
        # ``call_soon`` callback are both pending — the loop
        # can't process the callback until it processes the
        # wakeup, but the wakeup doesn't fire until the callback
        # runs. Using ``run_coroutine_threadsafe`` avoids this
        # because the scheduled coroutine itself is the thing
        # that runs ``await`` + ``cancel`` + ``gather`` + ``stop``
        # in one continuous pass on the event loop thread.
        async def _drain() -> None:
            # 1. The cancel event is already set (stop() set it
            #    before scheduling us). Yield once so the loop
            #    observes the flag's wakeup.
            while not self._cancel.is_set():
                await asyncio.sleep(0.01)
            # 2. Cancel any in-flight worker tasks.
            for w in self._worker_tasks:
                w.cancel()
            # 3. Wait for them to finish (or raise) so the
            #    main ``_consume_forever`` coroutine can
            #    complete its finally block.
            await asyncio.gather(
                *self._worker_tasks, return_exceptions=True
            )
            self._worker_tasks = []
            # 4. Stop the loop. ``run_until_complete`` will
            #    return on the next iteration.
            self._loop.stop()

        if self._loop is None:
            # Loop never started. Just join the thread.
            self._thread.join(timeout=2)
            self._thread = None
            return

        # Set the cancel flag NOW so the await in _drain wakes
        # up immediately. The flag's wakeup is queued and will
        # be delivered to ``_drain`` once the loop is processing
        # the coroutine (the very next thing on the loop's
        # ready queue).
        self._cancel.set()

        # Schedule the drain coroutine on the worker's loop.
        future = asyncio.run_coroutine_threadsafe(_drain(), self._loop)
        try:
            # Block the calling thread until the drain completes
            # (which is when ``loop.stop()`` has been called and
            # the loop is winding down). Add a timeout for
            # safety.
            future.result(timeout=3)
        except Exception as exc:
            logger.warning("federated worker pool drain failed: %s", exc)
        finally:
            # The loop should have wound down by now. Wait for
            # the thread to finish.
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                logger.warning(
                    "federated worker pool thread did not exit; "
                    "possible asyncio event loop shutdown bug"
                )
            self._thread = None
            self._loop = None

    def submit(self, task_id: str) -> None:
        """Enqueue a task id for a worker to process.

        Safe to call from any thread. Uses a lock-free handoff:
        if the worker's event loop is already up, we use
        ``call_soon_threadsafe`` to enqueue directly. If the
        worker hasn't reached its event loop yet, we drop the
        id into a thread-safe list and the worker drains it
        on startup. This eliminates the race where ``submit()``
        is called before ``_run`` has assigned ``_loop``.
        """
        loop = self._loop
        if loop is not None and self._queue is not None:
            loop.call_soon_threadsafe(self._queue.put_nowait, task_id)
            return
        # Worker not ready yet. Use the pending list + event
        # so we don't block. The worker drains _pending_*
        # before starting its event loop.
        self._pending_until_loop_ready.append(task_id)
        self._loop_ready.set()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        # Queue is created here, on the worker's own loop, so
        # ``asyncio.Queue`` is bound to that loop.
        self._queue = asyncio.Queue()
        # Drain any task_ids submitted before _run was called.
        # The HTTP handler put them into _pending_until_loop_ready
        # under the lock-free handoff in submit().
        if self._pending_until_loop_ready:
            for tid in self._pending_until_loop_ready:
                self._queue.put_nowait(tid)
            self._pending_until_loop_ready.clear()
        self._loop_ready.set()
        try:
            self._loop.run_until_complete(self._consume_forever())
        finally:
            self._loop.close()

    async def _consume_forever(self) -> None:
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self._size)
        ]
        try:
            # v1.2 — ``_cancel`` is a ``threading.Event`` (not an
            # ``asyncio.Event``) so we can set it from any thread
            # without an event loop. To wait on it from a
            # coroutine, we yield to the loop periodically and
            # re-check. This is the recommended pattern for
            # cross-thread cancel signals per the asyncio docs.
            while not self._cancel.is_set():
                await asyncio.sleep(0.01)
        finally:
            for w in self._worker_tasks:
                w.cancel()
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks = []

    async def _worker_loop(self, worker_id: int) -> None:
        assert self._queue is not None
        while True:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if self._cancel.is_set():
                    return
                continue
            await self._process_task(task_id, worker_id)

    async def _process_task(self, task_id: str, worker_id: int) -> None:
        task = self._store.get(task_id)
        if task is None:
            return
        # submitted → working
        task["state"] = "working"
        task["worker_id"] = worker_id
        self._store.put(task)
        # v1.2 — always re-read the latest task from the store
        # before checking cancel, so a request_cancel that
        # arrived between the initial fetch and the work loop
        # is observed.
        def _cancelled() -> bool:
            latest = self._store.get(task_id)
            return bool(latest and latest.get("cancel_requested"))

        if _cancelled():
            task["state"] = "canceled"
        else:
            cancelled = False
            for _ in range(int(_DEFAULT_TASK_SLEEP_SECONDS * 1000) // 5):
                await asyncio.sleep(0.005)
                if _cancelled():
                    task = self._store.get(task_id) or task
                    cancelled = True
                    break
            if cancelled:
                task["state"] = "canceled"
            else:
                task["state"] = "completed"
                task["artifacts"] = [{"type": "text", "value": f"echo: {task_id}"}]
        self._store.put(task)


# Backward-compat module-level shim for tests that imported
# the original _TASK_STORE helpers. New code should use
# FederatedTaskStore directly.
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
    v1.2 (service-mode): reads from the server's
    :class:`FederatedTaskStore`; when ``workers > 1`` the
    handler returns ``202 Accepted`` immediately and lets the
    worker pool process the task asynchronously.
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
            rest = parsed.path.split("/tasks/", 1)[1]
            # `/tasks/{id}/stream` -> SSE
            if rest.endswith("/stream"):
                task_id = rest[: -len("/stream")]
                self._serve_sse_stream(task_id)
                return
            task_id = rest
            task_store = self.server.task_store  # type: ignore[attr-defined]
            task = task_store.get(task_id)
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
                "cancel_requested": False,
                "skill_id": payload.get("skill_id", ""),
                "inputs": payload.get("inputs", {}),
                "artifacts": [],
            }
            task_store = self.server.task_store  # type: ignore[attr-defined]
            pool = self.server.worker_pool  # type: ignore[attr-defined]
            assert task_store is not None
            assert pool is not None
            task_store.put(task)
            # v1.2 — return 202 only when the pool has more than
            # one worker (i.e. actual async work). workers=1 keeps
            # the v1.0/v1.1 synchronous-200 contract.
            if pool is not None and pool._size > 1 and pool._thread is not None:
                pool.submit(task_id)
                self._send_json(202, task)
            else:
                self._send_json(200, task)
            return
        if parsed.path.startswith("/tasks/") and parsed.path.endswith("/cancel"):
            task_id = parsed.path.split("/tasks/", 1)[1][: -len("/cancel")]
            task_store = self.server.task_store  # type: ignore[attr-defined]
            if task_store.request_cancel(task_id):
                task = task_store.get(task_id) or {}
                self._send_json(200, task)
            else:
                self._send_json(404, {"error": f"task {task_id!r} not found"})
            return
        self._send_json(404, {"error": f"unknown path {parsed.path}"})

    def _serve_sse_stream(self, task_id: str) -> None:
        """v1.2 — Server-Sent Events for /tasks/{id}/stream.

        Sends a snapshot of the current state as the first
        event, then if the task is not yet terminal, polls
        the store every 100ms for state changes and writes
        additional events until the task reaches a terminal
        state or the client disconnects. The handler is
        fully synchronous and runs on a ``ThreadingHTTPServer``
        thread.
        """
        task_store = self.server.task_store  # type: ignore[attr-defined]
        task = task_store.get(task_id)
        if task is None:
            self._send_json(404, {"error": f"task {task_id!r} not found"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def _send_event(data: dict[str, Any]) -> None:
            line = f"data: {json.dumps(data)}\n\n".encode()
            try:
                self.wfile.write(line)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        if not _send_event(task):
            return
        TERMINAL = {"completed", "failed", "canceled"}
        if task["state"] in TERMINAL:
            return
        last_state = task["state"]
        # Poll until terminal. Bounded by the client's HTTP
        # timeout (typically 2-5s in test code).
        for _ in range(60):
            time.sleep(0.05)
            current = task_store.get(task_id)
            if current is None:
                return
            if current["state"] in TERMINAL:
                _send_event(current)
                return
            if current["state"] != last_state:
                if not _send_event(current):
                    return
                last_state = current["state"]

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
        workers: int = 1,
    ) -> None:
        # v1.1 — fail fast on a malformed port rather than letting
        # ThreadingHTTPServer raise a confusing socket error later.
        if not isinstance(port, int):
            raise TypeError(
                f"port must be an int, got {type(port).__name__} "
                "(use 0 for OS-assigned; see "
                "https://loopy.dev/docs/federate#federated-server)"
            )
        if not (0 <= port <= 65535):
            raise ValueError(
                f"port must be in [0, 65535], got {port} "
                "(see https://loopy.dev/docs/federate#federated-server)"
            )
        # v1.2 — workers >= 1 (zero or negative is a config error
        # the user can fix; the default of 1 preserves the v1.0/v1.1
        # synchronous behavior).
        if not isinstance(workers, int):
            raise TypeError(
                f"workers must be an int, got {type(workers).__name__} "
                "(see https://loopy.dev/docs/federate#federated-server)"
            )
        if workers < 1:
            raise ValueError(
                f"workers >= 1 required, got {workers} "
                "(see https://loopy.dev/docs/federate#federated-server)"
            )
        self.agent_card = agent_card
        self.host = host
        self.port = port
        self.workers = workers
        # v1.2 — task store + worker pool are created at start();
        # keep them None before that so unit tests that don't call
        # start() (or that use the synchronous default path) don't
        # have to deal with a half-initialized pool.
        self.task_store: FederatedTaskStore | None = None
        self.worker_pool: FederatedWorkerPool | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> FederatedServer:
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.shutdown()

    def start(self) -> None:
        # v1.2 — start the worker pool BEFORE the HTTP server so
        # that POST /tasks can immediately enqueue a task and
        # have a worker pick it up. When workers == 1 we still
        # start a single worker for parity with the v1.0/v1.1
        # handler (the pool's work is ~50ms simulated sleep, so
        # the handler returns 200 with state=submitted and the
        # pool drives the state to "completed" asynchronously).
        if self.task_store is None:
            self.task_store = FederatedTaskStore()
        if self.worker_pool is None:
            self.worker_pool = FederatedWorkerPool(
                self.task_store, size=self.workers
            )
            self.worker_pool.start()

        httpd = ThreadingHTTPServer((self.host, self.port), _FederatedHandler)
        httpd.agent_card = self.agent_card  # type: ignore[attr-defined]
        # v1.2 — the handler reads task_store + worker_pool from
        # the HTTPServer instance, not module globals.
        httpd.task_store = self.task_store  # type: ignore[attr-defined]
        httpd.worker_pool = self.worker_pool  # type: ignore[attr-defined]
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
        # v1.2 — stop the worker pool first so any in-flight
        # ``asyncio`` tasks settle before the HTTP listener closes.
        if self.worker_pool is not None:
            self.worker_pool.stop()
            self.worker_pool = None
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
        raise ValueError(
            f"Could not load module spec for {path} (see https://loopy.dev/docs/federate#errors)"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr in ("CARD", "card", "AGENT_CARD", "agent_card"):
        candidate = getattr(module, attr, None)
        if isinstance(candidate, AgentCard):
            return candidate

    raise ValueError(
        f"Module {path} has no AgentCard attribute (looked for CARD, card, "
        "AGENT_CARD, agent_card) "
        "(see https://loopy.dev/docs/federate#errors)"
    )
