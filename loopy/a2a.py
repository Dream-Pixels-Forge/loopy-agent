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
        logger.info(f"Registered agent: {card.name}")

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
        return [
            card for card in self._agents.values()
            if capability in card.capabilities
        ]

    def find_by_pricing(self, pricing: str) -> list[AgentCard]:
        """Find agents by pricing model."""
        return [
            card for card in self._agents.values()
            if card.pricing == pricing
        ]

    def to_dict(self) -> dict[str, Any]:
        """Export registry."""
        return {name: card.to_dict() for name, card in self._agents.items()}


class A2AClient:
    """
    Client for agent-to-agent communication.

    Example:
        client = A2AClient(registry)
        response = await client.call("code-assistant", "Write a hello world in Python")
        print(response.result)
    """

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._handlers: dict[str, Callable[[AgentRequest], Awaitable[AgentResponse]]] = {}

    def register_handler(
        self,
        agent_name: str,
        handler: Callable[[AgentRequest], Awaitable[AgentResponse]],
    ) -> None:
        """Register a handler for incoming requests."""
        self._handlers[agent_name] = handler

    async def call(
        self,
        agent_name: str,
        task: str,
        context: dict[str, Any] | None = None,
        sender: str = "",
    ) -> AgentResponse:
        """Call another agent."""
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

        # Default: return placeholder
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
    ) -> list[AgentResponse]:
        """Broadcast request to all agents with a capability."""
        agents = self.registry.find_by_capability(capability)
        responses: list[AgentResponse] = []

        for agent in agents:
            response = await self.call(agent.name, task, sender=sender)
            responses.append(response)

        return responses
