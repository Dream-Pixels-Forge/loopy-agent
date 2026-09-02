"""T2.0.1 — A2A characterization tests.

Pin the current behavior of ``A2AClient.call`` and ``A2AClient.broadcast``
so the v0.9.0 T2.1 changes (Agent Card discovery, task lifecycle,
streaming) do not regress them. Every test here documents an
observable contract that is true *today* and must remain true
*after* the T2.1 work lands.
"""

from __future__ import annotations

import pytest

from loopy.a2a import (
    A2AClient,
    AgentCapability,
    AgentCard,
    AgentRegistry,
    AgentRequest,
    AgentResponse,
)

# ── A2AClient.call ────────────────────────────────────────────


class TestACallContract:
    """Pin A2AClient.call dispatch order and failure modes."""

    @pytest.mark.asyncio
    async def test_call_unknown_agent_returns_failure_response(self):
        client = A2AClient(AgentRegistry())
        response = await client.call("ghost", "do thing")
        assert response.success is False
        assert "Agent not found" in response.error
        assert response.result == ""

    @pytest.mark.asyncio
    async def test_call_local_handler_receives_request(self):
        registry = AgentRegistry()
        registry.register(
            AgentCard(
                name="echo",
                description="Echoes back",
                version="1.0",
                capabilities=[AgentCapability.TEXT_GENERATION],
                endpoint="local",
            )
        )
        seen: list[AgentRequest] = []

        async def echo_handler(req: AgentRequest) -> AgentResponse:
            seen.append(req)
            return AgentResponse(result=f"echo:{req.task}")

        client = A2AClient(registry)
        client.register_handler("echo", echo_handler)
        response = await client.call("echo", "hello")

        assert response.success is True
        assert response.result == "echo:hello"
        assert len(seen) == 1
        assert seen[0].task == "hello"
        assert seen[0].sender == ""

    @pytest.mark.asyncio
    async def test_call_handler_exception_becomes_failure_response(self):
        registry = AgentRegistry()
        registry.register(
            AgentCard(
                name="boom",
                description="Throws",
                version="1.0",
                capabilities=[AgentCapability.CODE_GENERATION],
                endpoint="local",
            )
        )

        async def boom_handler(req: AgentRequest) -> AgentResponse:
            raise RuntimeError("kaboom")

        client = A2AClient(registry)
        client.register_handler("boom", boom_handler)
        response = await client.call("boom", "x")

        assert response.success is False
        assert "kaboom" in response.error

    @pytest.mark.asyncio
    async def test_call_placeholder_when_no_handler_no_endpoint(self):
        registry = AgentRegistry()
        registry.register(
            AgentCard(
                name="nop",
                description="No handler, no endpoint",
                version="1.0",
                capabilities=[AgentCapability.CUSTOM],
                endpoint="local",
            )
        )
        client = A2AClient(registry)
        response = await client.call("nop", "anything")

        assert response.success is True
        assert "would process" in response.result
        assert response.metadata.get("placeholder") is True

    @pytest.mark.asyncio
    async def test_call_passes_context_and_sender_to_handler(self):
        registry = AgentRegistry()
        registry.register(
            AgentCard(
                name="k",
                description="",
                version="1.0",
                capabilities=[AgentCapability.CUSTOM],
                endpoint="local",
            )
        )
        seen: list[AgentRequest] = []

        async def capture(req: AgentRequest) -> AgentResponse:
            seen.append(req)
            return AgentResponse(result="ok")

        client = A2AClient(registry)
        client.register_handler("k", capture)
        await client.call("k", "task-x", context={"k": "v"}, sender="alice")

        assert seen[0].context == {"k": "v"}
        assert seen[0].sender == "alice"


# ── A2AClient.broadcast ───────────────────────────────────────


class TestBroadcastContract:
    """Pin A2AClient.broadcast routing, cycle detection, and depth cap."""

    @pytest.mark.asyncio
    async def test_broadcast_returns_one_response_per_matching_agent(self):
        registry = AgentRegistry()
        for i in range(3):
            registry.register(
                AgentCard(
                    name=f"agent-{i}",
                    description="",
                    version="1.0",
                    capabilities=[AgentCapability.RESEARCH],
                    endpoint="local",
                )
            )
        client = A2AClient(registry)
        responses = await client.broadcast(AgentCapability.RESEARCH, "research X")

        assert len(responses) == 3
        # Each call lands in the placeholder path.
        for r, card in zip(responses, registry.list_all(), strict=True):
            assert r.success is True
            assert card.name in r.result

    @pytest.mark.asyncio
    async def test_broadcast_filters_by_capability(self):
        registry = AgentRegistry()
        registry.register(
            AgentCard(
                name="a",
                description="",
                version="1.0",
                capabilities=[AgentCapability.RESEARCH],
                endpoint="local",
            )
        )
        registry.register(
            AgentCard(
                name="b",
                description="",
                version="1.0",
                capabilities=[AgentCapability.SUMMARIZATION],
                endpoint="local",
            )
        )
        client = A2AClient(registry)
        responses = await client.broadcast(AgentCapability.SUMMARIZATION, "summarize")
        assert len(responses) == 1
        assert "Agent b would process" in responses[0].result

    @pytest.mark.asyncio
    async def test_broadcast_visited_set_prevents_duplicate_routes(self):
        """If two agents share a name (rare, but the visited set tracks
        names), the second occurrence is skipped."""
        registry = AgentRegistry()
        registry.register(
            AgentCard(
                name="dup",
                description="",
                version="1.0",
                capabilities=[AgentCapability.RESEARCH],
                endpoint="local",
            )
        )
        client = A2AClient(registry)

        # Manually invoke broadcast with a visited set that already
        # contains "dup" — the only matching agent should be skipped.
        responses = await client.broadcast(
            AgentCapability.RESEARCH,
            "task",
            _visited={"dup"},
        )
        assert responses == []


# ── AgentCard serialization round-trip ────────────────────────


class TestAgentCardRoundTrip:
    @pytest.mark.asyncio
    async def test_card_to_from_dict_roundtrip(self):
        original = AgentCard(
            name="rc",
            description="round-trip",
            version="2.5",
            capabilities=[AgentCapability.RESEARCH, AgentCapability.CODE_GENERATION],
            endpoint="http://example.com/agent",
            authentication="api_key",
            pricing="per_token",
            metadata={"k": "v"},
        )
        roundtripped = AgentCard.from_dict(original.to_dict())

        assert roundtripped.name == original.name
        assert roundtripped.description == original.description
        assert roundtripped.version == original.version
        assert roundtripped.endpoint == original.endpoint
        assert roundtripped.authentication == original.authentication
        assert roundtripped.pricing == original.pricing
        assert roundtripped.metadata == original.metadata
        assert roundtripped.capabilities == original.capabilities
