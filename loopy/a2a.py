"""
A2A — Agent-to-Agent Protocol.

Standard protocol for agents to discover and communicate with each other.
Critical gap: 2031 agents must collaborate across organizations.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from loopy.netutil import validate_outbound_url

logger = logging.getLogger("loopy.a2a")


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


@dataclass
class AgentCard:
    """Agent identity card for discovery."""

    name: str
    description: str
    version: str
    capabilities: list[AgentCapability]
    endpoint: str  # URL or local reference
    authentication: str = "none"  # none, api_key, oauth
    pricing: str = "free"  # free, per_token, per_request
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
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
        """Deserialize from a dict created by :meth:`to_dict`."""
        return cls(
            name=data["name"],
            description=data["description"],
            version=data["version"],
            capabilities=[AgentCapability(c) for c in data["capabilities"]],
            endpoint=data["endpoint"],
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
    ):
        """Args:
        registry: The agent registry to route through.
        allow_private: Permit loopback/private/link-local agent
            endpoints. Keep True for operator-registered endpoints (local
            A2A meshes are normal). Set False when endpoints can be
            influenced by untrusted content — the SSRF guard then
            rejects internal destinations.
        """
        self.registry = registry
        self._allow_private = allow_private
        self._handlers: dict[str, Callable[[AgentRequest], Awaitable[AgentResponse]]] = {}

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
