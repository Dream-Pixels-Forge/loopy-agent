"""
A2A — Agent-to-Agent Protocol.

Standard protocol for agents to discover and communicate with each other.
Critical gap: 2031 agents must collaborate across organizations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from loopy.netutil import validate_outbound_url

logger = logging.getLogger("loopy.a2a")


_TASK_STATES = frozenset(
    {
        "submitted",
        "working",
        "input-required",
        "completed",
        "failed",
        "canceled",
        "rejected",
    }
)


class A2AError(Exception):
    """Raised when an A2A protocol operation fails.

    v0.9.0 — used for malformed Agent Cards, unknown task
    lifecycle states, and invalid task IDs.
    """


class AgentCapability(str, Enum):
    """Agent capabilities for discovery."""

    TEXT_GENERATION = "text_generation"
    CODE_GENERATION = "code_generation"
    DATA_ANALYSIS = "data_analysis"
    IMAGE_GENERATION = "image_generation"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    RESEARCH = "research"
    CUSTOM = "custom"


_ALLOWED_AUTHENTICATION = frozenset({"none", "api_key", "oauth2", "openIdConnect"})


@dataclass
class AgentCard:
    """Agent identity card for discovery.

    Two shapes live in this dataclass:

    * **legacy** — used by :class:`AgentRegistry` and the
      :class:`A2AClient` ``call`` / ``broadcast`` paths. The card
      carries ``capabilities`` (list[AgentCapability]) and an
      ``endpoint`` URL.
    * **A2A v1.0** — used by :meth:`A2AClient.fetch_agent_card` and
      :meth:`A2AClient.from_agent_card`. The card carries
      ``skills`` (list[dict]) and a top-level ``url``.

    The fields are unioned here so one dataclass satisfies both
    consumers; the :class:`A2AClient` chooses the right shape per
    use. Default factories keep both shapes constructible.
    """

    name: str
    description: str = ""
    version: str = "0.0.0"
    capabilities: list[AgentCapability] = field(default_factory=list)
    endpoint: str = "local"
    # A2A v1.0 fields:
    url: str = ""
    skills: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    authentication: str = "none"  # none, api_key, oauth2, openIdConnect
    pricing: str = "free"  # free, per_token, per_request
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (legacy shape)."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "endpoint": self.endpoint,
            "authentication": self.authentication,
            "pricing": self.pricing,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCard:
        """Deserialize from a legacy dict created by :meth:`to_dict`."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            version=data["version"],
            capabilities=[AgentCapability(c) for c in data.get("capabilities", [])],
            endpoint=data.get("endpoint", "local"),
            authentication=data.get("authentication", "none"),
            pricing=data.get("pricing", "free"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentRequest:
    """Request from one agent to another."""

    task: str
    context: dict[str, Any] = field(default_factory=dict)
    sender: str = ""
    request_id: str = ""
    max_tokens: int = 1000
    timeout_seconds: int = 30

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "task": self.task,
            "context": self.context,
            "sender": self.sender,
            "request_id": self.request_id,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class AgentResponse:
    """Response from an agent."""

    result: str
    success: bool = True
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "tokens_used": self.tokens_used,
        }


@dataclass
class A2ATask:
    """A2A v1.0 task lifecycle record.

    States: ``submitted`` → ``working`` → (``completed`` | ``failed`` |
    ``canceled`` | ``rejected``), with ``input-required`` as an
    asynchronous pause that carries a question artifact for the
    human to answer.
    """

    id: str
    state: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in _TASK_STATES:
            raise ValueError(
                f"A2ATask.state must be one of {sorted(_TASK_STATES)}; got {self.state!r} (see https://loopy.dev/docs/a2a#errors)"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "artifacts": list(self.artifacts),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> A2ATask:
        return cls(
            id=data["id"],
            state=data["state"],
            artifacts=list(data.get("artifacts", [])),
            metadata=dict(data.get("metadata", {})),
        )


class AgentRegistry:
    """
    Registry of available agents for discovery.

    Example:
        registry = AgentRegistry()
        registry.register(my_agent_card)
        agents = registry.find_by_capability(AgentCapability.CODE_GENERATION)
    """

    def __init__(self):
        self._agents: dict[str, AgentCard] = {}

    def register(self, card: AgentCard) -> None:
        """Register an agent."""
        self._agents[card.name] = card
        logger.info("Registered agent: %s", card.name)

    def unregister(self, name: str) -> None:
        """Unregister an agent."""
        self._agents.pop(name, None)

    def get(self, name: str) -> AgentCard | None:
        """Get agent by name."""
        return self._agents.get(name)

    def list_all(self) -> list[AgentCard]:
        """List all registered agents."""
        return list(self._agents.values())

    def find_by_capability(self, capability: AgentCapability) -> list[AgentCard]:
        """Find agents with a specific capability."""
        return [card for card in self._agents.values() if capability in card.capabilities]

    def find_by_pricing(self, pricing: str) -> list[AgentCard]:
        """Find agents by pricing model."""
        return [card for card in self._agents.values() if card.pricing == pricing]

    def to_dict(self) -> dict[str, Any]:
        """Export registry."""
        return {name: card.to_dict() for name, card in self._agents.items()}


class A2AClient:
    """
    Client for agent-to-agent communication.

    Supports both local (registered handler) and remote (HTTP)
    dispatch. When a remote *endpoint* is set on the agent's
    :class:`AgentCard`, the client sends an HTTP POST with the
    request payload. Otherwise it falls back to a local handler
    registered via :meth:`register_handler`.

    Example:
        client = A2AClient(registry)
        response = await client.call("code-assistant", "Write hello world")
        print(response.result)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        allow_private: bool = True,
        card_ttl: float = 3600.0,
    ):
        """Args:
        registry: The agent registry to route through.
        allow_private: Permit loopback/private/link-local agent
            endpoints. Keep True for operator-registered endpoints (local
            A2A meshes are normal). Set False when endpoints can be
            influenced by untrusted content — the SSRF guard then
            rejects internal destinations.
        card_ttl: Seconds a fetched :class:`AgentCard` is cached before
            the next call to :meth:`fetch_agent_card` will re-fetch
            (v0.9.0). Default 3600 (1 hour).
        """
        self.registry = registry
        self._allow_private = allow_private
        self.card_ttl = card_ttl
        self._handlers: dict[str, Callable[[AgentRequest], Awaitable[AgentResponse]]] = {}
        # v0.9.0 — when the client was built from a single Agent Card
        # (see :meth:`from_agent_card`), the source card lives here so
        # callers can re-read it without rebuilding.
        self._agent_card: AgentCard | None = None
        # v0.9.0 — URL -> (AgentCard, fetched_at_monotonic) cache.
        self._card_cache: dict[str, tuple[AgentCard, float]] = {}

    def register_handler(
        self,
        agent_name: str,
        handler: Callable[[AgentRequest], Awaitable[AgentResponse]],
    ) -> None:
        """Register a local handler for incoming requests.

        Args:
            agent_name: Name of the agent this handler serves.
            handler: Async callable receiving an AgentRequest
                     and returning an AgentResponse.
        """
        self._handlers[agent_name] = handler

    # ── v0.9.0 — Agent Card discovery ────────────────────────────

    @property
    def agent_card(self) -> AgentCard:
        """The :class:`AgentCard` this client was built from.

        Always returns a card; if the client was constructed directly
        via :class:`A2AClient(registry)`, a synthetic placeholder
        card derived from the registry name is returned so callers
        can rely on a non-None value.
        """
        if self._agent_card is not None:
            return self._agent_card
        return AgentCard(name=self.registry.__class__.__name__)

    @classmethod
    def from_agent_card(
        cls,
        card: AgentCard,
        *,
        allow_private: bool = True,
        card_ttl: float = 3600.0,
    ) -> A2AClient:
        """Build an :class:`A2AClient` from a single :class:`AgentCard`.

        The registry is auto-populated with the card so the legacy
        ``call`` / ``broadcast`` paths keep working. The card is
        also retained on the client so ``client.agent_card`` returns
        the source.

        Raises:
            ValueError: if ``card.authentication`` is not in the
                A2A v1.0 allowed set (``none``, ``api_key``,
                ``oauth2``, ``openIdConnect``).
        """
        if card.authentication not in _ALLOWED_AUTHENTICATION:
            raise ValueError(
                f"Authentication method {card.authentication!r} is not allowed;  (see https://loopy.dev/docs/a2a#errors)"
                f"must be one of {sorted(_ALLOWED_AUTHENTICATION)}"
            )
        registry = AgentRegistry()
        registry.register(card)
        client = cls(
            registry,
            allow_private=allow_private,
            card_ttl=card_ttl,
        )
        client._agent_card = card
        return client

    async def fetch_agent_card(self, url: str) -> AgentCard:
        """Fetch and parse an A2A v1.0 Agent Card from a URL.

        Args:
            url: HTTPS URL of a ``/.well-known/agent-card.json``
                document.

        Returns:
            The parsed :class:`AgentCard`.

        Raises:
            A2AError: if the document is missing required fields
                (e.g. ``name``) or cannot be decoded.
            ValueError: if the URL scheme is not allowed (re-raised
                from :func:`loopy.netutil.validate_outbound_url`).
        """
        # Cache hit?
        cached = self._card_cache.get(url)
        if cached is not None:
            card, fetched_at = cached
            if (time.monotonic() - fetched_at) < self.card_ttl:
                return card

        # SSRF guard: only http(s) are allowed.
        validate_outbound_url(url, allow_private=self._allow_private)

        try:
            data = await self._fetch_json(url)
        except A2AError:
            raise
        except Exception as exc:
            raise A2AError(
                f"Could not load Agent Card from {url}: {exc} "
                "(see https://loopy.dev/docs/a2a#errors)"
            ) from exc

        return self._parse_agent_card(data, url)

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        """GET a URL and return the parsed JSON body.

        Wrapped in its own method so tests can patch it with
        ``AsyncMock(return_value=payload)`` without touching
        :mod:`httpx` directly.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    def _parse_agent_card(self, data: dict[str, Any], url: str) -> AgentCard:
        if "name" not in data:
            raise A2AError(
                f"Agent Card at {url} is missing required field 'name' (see https://loopy.dev/docs/a2a#errors)"
            )

        auth = data.get("authentication") or {}
        schemes = auth.get("schemes") if isinstance(auth, dict) else None
        authentication = schemes[0] if schemes else "none (see https://loopy.dev/docs/a2a#errors)"

        provider_field = data.get("provider") or {}
        if isinstance(provider_field, dict):
            provider = provider_field.get("name", "")
        else:
            provider = str(provider_field)

        card = AgentCard(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.0.0"),
            capabilities=[],
            endpoint=data.get("url", url),
            url=data.get("url", ""),
            skills=list(data.get("skills", [])),
            provider=provider,
            authentication=authentication,
        )
        self._card_cache[url] = (card, time.monotonic())
        return card

    # ── v0.9.0 — Task lifecycle + streaming ──────────────────────

    async def create_task(
        self,
        skill_id: str,
        inputs: dict[str, Any],
        *,
        callback_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> A2ATask:
        """Submit a task to a remote agent by skill id.

        Args:
            skill_id: Must match one of the ``skills`` entries on the
                client's :attr:`agent_card`. Unknown ids raise
                :class:`A2AError` without making a network call.
            inputs: Skill-specific input payload.
            callback_url: Optional webhook URL. When set, the remote
                agent will POST status updates here; the receiving
                side must verify the HMAC via :meth:`verify_webhook`.
            idempotency_key: Re-submitting with the same key yields
                the same task id from the server.

        Returns:
            The initial :class:`A2ATask` (typically ``state="submitted"``).
        """
        skill_ids = {s.get("id") for s in self.agent_card.skills if isinstance(s, dict)}
        if skill_id not in skill_ids:
            raise A2AError(
                f"Unknown skill {skill_id!r}; available: {sorted(x for x in skill_ids if x)} (see https://loopy.dev/docs/a2a#errors)"
            )

        body: dict[str, Any] = {
            "skill_id": skill_id,
            "inputs": inputs,
        }
        if callback_url is not None:
            body["callback_url"] = callback_url
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key

        url = self._endpoint()
        data = await self._post_json(url, json=body)
        return A2ATask.from_dict(data)

    def _endpoint(self) -> str:
        """The base URL of the remote agent, with no trailing slash."""
        return (self.agent_card.url or self.agent_card.endpoint).rstrip("/")

    async def get_task(self, task_id: str) -> A2ATask:
        """Fetch the current state of a task by id."""
        data = await self._get_json(f"{self._endpoint()}/tasks/{task_id}")
        return A2ATask.from_dict(data)

    async def cancel_task(self, task_id: str) -> A2ATask:
        """Request cancellation of a running task.

        Returns the updated task; the server transitions the state
        to ``"canceled"`` (idempotent: cancelling a canceled task
        is a no-op).
        """
        data = await self._post_json(
            f"{self._endpoint()}/tasks/{task_id}/cancel",
            json={},
        )
        return A2ATask.from_dict(data)

    async def stream_task(self, task_id: str) -> AsyncIterator[A2ATask]:
        """Yield :class:`A2ATask` updates as they stream in via SSE.

        The iterator terminates naturally when the server sends a
        terminal state (``completed``, ``failed``, ``canceled``, or
        ``rejected``).
        """
        url = f"{self._endpoint()}/tasks/{task_id}/stream"
        async for event in self._sse_events(url):
            yield A2ATask.from_dict(event)

    def verify_webhook(
        self,
        body: bytes,
        signature: str,
        secret: bytes,
    ) -> bool:
        """Verify the HMAC-SHA256 signature of an incoming webhook.

        Returns ``True`` if the signature is valid, ``False`` otherwise.
        Uses :func:`hmac.compare_digest` for constant-time comparison.
        Never raises; callers should treat ``False`` as a 400.
        """
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        # ``hmac.compare_digest`` raises TypeError on length mismatch in
        # Python <3.10; safe across versions when both args are str.
        if not isinstance(signature, str) or len(signature) != len(expected):
            return False
        return hmac.compare_digest(expected, signature)

    # ── HTTP helpers (monkey-patchable for tests) ───────────────

    async def _post_json(self, url: str, *, json: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=json)
            resp.raise_for_status()
            return resp.json()

    async def _get_json(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def _sse_events(self, url: str) -> AsyncIterator[dict[str, Any]]:
        """Default SSE transport. Parses ``data: <json>`` lines.

        Tests may monkey-patch this to a small async generator that
        yields pre-canned dicts.
        """
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream("GET", url) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    payload = line[len("data:") :].strip()
                    if payload:
                        yield json.loads(payload)

    async def call(
        self,
        agent_name: str,
        task: str,
        context: dict[str, Any] | None = None,
        sender: str = "",
    ) -> AgentResponse:
        """
        Call another agent by name.

        Dispatch order:
        1. Local registered handler (if any).
        2. HTTP POST to ``AgentCard.endpoint`` (if set).
        3. Placeholder response (if neither handler nor endpoint).

        Args:
            agent_name: Registered agent name.
            task: Task description for the remote agent.
            context: Optional shared context dict.
            sender: Sender identity string.

        Returns:
            An AgentResponse with the result.
        """
        card = self.registry.get(agent_name)
        if not card:
            return AgentResponse(
                result="",
                success=False,
                error=f"Agent not found: {agent_name}",
            )

        request = AgentRequest(
            task=task,
            context=context or {},
            sender=sender,
        )

        # 1. Local handler
        handler = self._handlers.get(agent_name)
        if handler:
            try:
                return await handler(request)
            except Exception as e:
                return AgentResponse(
                    result="",
                    success=False,
                    error=str(e),
                )

        # 2. HTTP dispatch via AgentCard.endpoint
        if card.endpoint and card.endpoint != "local":
            try:
                validate_outbound_url(
                    card.endpoint,
                    allow_private=self._allow_private,
                )
                async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                    resp = await client.post(
                        card.endpoint,
                        json=request.to_dict(),
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return AgentResponse(
                        result=data.get("result", ""),
                        success=data.get("success", True),
                        error=data.get("error", ""),
                        metadata=data.get("metadata", {}),
                        tokens_used=data.get("tokens_used", 0),
                    )
            except Exception as e:
                return AgentResponse(
                    result="",
                    success=False,
                    error=f"HTTP call to {card.endpoint} failed: {e}",
                )

        # 3. Placeholder
        return AgentResponse(
            result=f"[Agent {agent_name} would process: {task}]",
            success=True,
            metadata={"placeholder": True},
        )

    async def broadcast(
        self,
        capability: AgentCapability,
        task: str,
        sender: str = "",
        *,
        max_depth: int = 3,
        _visited: set[str] | None = None,
        _depth: int = 0,
    ) -> list[AgentResponse]:
        """Broadcast request to all agents with a capability.

        Includes cycle detection (skips agents already visited) and a
        configurable depth limit to prevent amplification when agents
        re-broadcast back.

        Args:
            capability: Filter agents by this capability.
            task: Task description for each agent.
            sender: Sender identity string.
            max_depth: Maximum broadcast depth (default 3).
        """
        if _depth >= max_depth:
            logger.warning("Broadcast depth limit (%d) reached", max_depth)
            return []

        agents = self.registry.find_by_capability(capability)
        visited = _visited if _visited is not None else set()
        responses: list[AgentResponse] = []

        for agent in agents:
            if agent.name in visited:
                continue
            visited.add(agent.name)

            response = await self.call(agent.name, task, sender=sender)
            responses.append(response)

        return responses
